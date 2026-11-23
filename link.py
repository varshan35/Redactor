"""Name-variant linking: 'Richa Sharma', 'R. Sharma', 'Ms. Sharma', 'Richa'
-> one entity. Ambiguous variants (two Sharmas in one document) are NOT merged;
they are flagged low-confidence for the reviewer."""
from __future__ import annotations
import re
from detect import Cand

HON = {"mr", "mrs", "ms", "miss", "dr", "prof", "shri", "smt", "sri", "mx"}


def parse(text: str):
    toks = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    hon = None
    if toks and toks[0].lower() in HON:
        hon, toks = toks[0], toks[1:]
    return hon, toks


def _fc(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    return a == b or (len(a) == 1 and b[0] == a) or (len(b) == 1 and a[0] == b)


def link(text: str, cands: list[Cand], hints=(), fb=None):
    ents: list[dict] = []

    def make(first, last):
        e = {"first": first, "last": last}
        ents.append(e)
        return e

    names = [c for c in cands if c.label == "NAME"]
    parsed = [(c, *parse(c.text)) for c in names]

    # A. full names with a spelled-out first name (and e-mail derived hints)
    seen_hint = []
    for h in hints:
        _, t = parse(h)
        if len(t) >= 2:
            seen_hint.append((t[0], t[-1]))
    for first, last in [(t[0], t[-1]) for c, h, t in parsed if len(t) >= 2 and len(t[0]) > 1] + \
                       [x for x in seen_hint if len(x[0]) > 1]:
        if not any(e["last"].lower() == last.lower() and e["first"].lower() == first.lower() for e in ents):
            make(first, last)
    for c, hon, t in parsed:
        if len(t) >= 2 and len(t[0]) > 1:
            c.entity = next(i for i, e in enumerate(ents)
                            if e["last"].lower() == t[-1].lower() and e["first"].lower() == t[0].lower())

    # B. initial + surname
    def attach_initial(first, last):
        m = [i for i, e in enumerate(ents) if e["last"].lower() == last.lower() and _fc(e["first"], first)]
        if len(m) == 1:
            if len(ents[m[0]]["first"]) == 1 and len(first) > 1:
                ents[m[0]]["first"] = first
            return m[0], False
        if len(m) > 1:
            return -1, True
        ents.append({"first": first, "last": last})
        return len(ents) - 1, False

    for first, last in [x for x in seen_hint if len(x[0]) == 1]:
        attach_initial(first, last)
    for c, hon, t in parsed:
        if len(t) >= 2 and len(t[0]) == 1:
            c.entity, amb = attach_initial(t[0], t[-1])
            if amb:
                c.ambiguous, c.conf = True, min(c.conf, 0.5)
                c.reason = "initial matches more than one person; not merged"

    # C. single tokens: 'Ms. Sharma', 'Dear Richa'
    for c, hon, t in parsed:
        if len(t) == 1:
            tok = t[0].lower()
            m = [i for i, e in enumerate(ents) if e["last"].lower() == tok or e["first"].lower() == tok]
            if len(m) == 1:
                c.entity = m[0]
            elif len(m) > 1:
                c.ambiguous, c.conf = True, min(c.conf, 0.5)
                c.reason = f"'{t[0]}' could be {len(m)} different people; not merged"
            else:
                ents.append({"first": "", "last": t[0]} if hon else {"first": t[0], "last": ""})
                c.entity = len(ents) - 1
        elif len(t) >= 2 and c.entity == -1 and not c.ambiguous:
            ents.append({"first": t[0], "last": t[-1]})
            c.entity = len(ents) - 1

    # D. expand: find further occurrences of each entity's variants
    claimed = [(c.start, c.end) for c in cands]

    def free(s, e):
        return all(e <= a or s >= b for a, b in claimed)

    new = []
    for i, e in enumerate(ents):
        f, l = e["first"], e["last"]
        pats = []
        same_last = [x for x in ents if x["last"].lower() == l.lower()] if l else []
        same_init = [x for x in same_last if x["first"][:1].lower() == f[:1].lower()] if f else []
        if f and l:
            pats.append((rf"(?<!\w){re.escape(f[0])}\.?[ \t]+{re.escape(l)}(?!\w)", 0.7,
                         "initial variant", len(same_init) > 1))
        if l:
            pats.append((rf"(?<!\w){re.escape(l)}(?!\w)", 0.7, "surname only", len(same_last) > 1))
        if len(f) > 2:
            pats.append((rf"(?<!\w){re.escape(f)}(?!\w)", 0.6, "first name only",
                         len([x for x in ents if x["first"].lower() == f.lower()]) > 1))
        if len(f) > 1 and l:
            pats.insert(0, (rf"(?<!\w){re.escape(f)}[ \t]+{re.escape(l)}(?!\w)", 0.8, "full-name variant", False))
        for rx, conf, why, amb in pats:
            for m in re.finditer(rx, text):
                if free(m.start(), m.end()) and not (fb and fb.is_rejected(m.group())):
                    if amb:   # several people fit: flag for review, never merge silently
                        c = Cand(m.start(), m.end(), m.group(), "NAME", 0.5, "link",
                                 f"{why} fits more than one person; not merged", ambiguous=True)
                    else:
                        c = Cand(m.start(), m.end(), m.group(), "NAME", conf, "link",
                                 f"linked: {why}", entity=i)
                    new.append(c)
                    claimed.append((m.start(), m.end()))
    cands = sorted(cands + new, key=lambda c: c.start)

    # renumber entities by first appearance, assign groups
    order = {}
    for c in cands:
        if c.label == "NAME" and c.entity >= 0 and c.entity not in order:
            order[c.entity] = len(order) + 1
    for c in cands:
        if c.label == "NAME":
            if c.entity >= 0:
                c.entity = order[c.entity]
                c.group = f"NAME_{c.entity}"
            else:
                c.group = f"NAME_?{c.text.casefold()}"
        else:
            c.group = f"{c.label}:{re.sub(r'[^A-Za-z0-9]', '', c.text).casefold()}"

    entities = {}
    for old, new_id in order.items():
        forms = sorted({c.text for c in cands if c.entity == new_id}, key=len, reverse=True)
        entities[new_id] = forms
    return cands, entities


def similar(cands: list[Cand], c: Cand) -> list[Cand]:
    """'Redact all similar': same linked entity/group, or identical text."""
    return [x for x in cands if x.group == c.group or x.text.casefold() == c.text.casefold()]
