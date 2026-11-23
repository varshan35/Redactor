"""Layered PII detection: rules + checksum validators + context, then name
heuristics. Optional SLM verification hook (Ollama) at the bottom.

Labels: NAME, EMAIL, PHONE, ADDRESS, ID
"""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class Cand:
    start: int
    end: int
    text: str
    label: str
    conf: float
    source: str
    reason: str = ""
    entity: int = -1
    group: str = ""
    ambiguous: bool = False


# ---------------------------------------------------------------- validators
_d = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
      [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
      [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
      [9,8,7,6,5,4,3,2,1,0]]
_p = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
      [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
      [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
_inv = [0,4,3,2,1,5,6,7,8,9]


def verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _d[c][_p[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(num: str) -> int:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _d[c][_p[(i + 1) % 8][int(ch)]]
    return _inv[c]


def luhn_ok(num: str) -> bool:
    s, alt = 0, False
    for ch in reversed(num):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        s += n
        alt = not alt
    return s % 10 == 0


# ------------------------------------------------------------------ patterns
LOCAL = r"[A-Za-z0-9][A-Za-z0-9._%+-]*"
LAB = r"[A-Za-z0-9][A-Za-z0-9-]*"
AT_B = r"\s*[\[\(\{<]\s*(?:at|@)\s*[\]\)\}>]\s*"
DOT_B = r"\s*[\[\(\{<]\s*(?:dot|\.)\s*[\]\)\}>]\s*"
DOT_W = r"\s+dot\s+"
EMAIL = re.compile(r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
OBF1 = re.compile(rf"(?<![A-Za-z0-9._%+-]){LOCAL}{AT_B}{LAB}(?:(?:{DOT_B}|{DOT_W}|\.){LAB})+", re.I)
OBF2 = re.compile(rf"(?<![A-Za-z0-9._%+-]){LOCAL}\s+at\s+{LAB}(?:{DOT_W}|{DOT_B}){LAB}(?:(?:{DOT_B}|{DOT_W}|\.){LAB})*", re.I)

UPI = re.compile(r"(?<![\w.%+-])[A-Za-z0-9._-]{2,}@(?:ok(?:hdfc(?:bank)?|icici|axis|sbi)|ybl|ibl|axl|paytm|apl|upi|"
                 r"oksbi|sbi|hdfcbank|icici|axisbank|barodampay|fbl|pthdfc|ptyes|ptsbi)(?![\w.])", re.I)
AADHAAR = re.compile(r"(?<!\d)(?<!\d[ -])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)(?![ -]\d)")
PAN = re.compile(r"(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PREFIX_ID = re.compile(r"\b(?:EMP|EID|STU|STD|ACC|ACCT|CUST|MEM|UID)[-/ ]?\d{3,}\b")
CTX_ID = re.compile(
    r"(?i:\b(?:employee|emp|staff|student|account|a/c|acct|customer|member|passport|"
    r"licen[cs]e|voter|policy|roll)\b[ \t]*(?:id|no\.?|number|num|#)?[ \t]*[:#-]?[ \t]*)"
    r"([A-Za-z0-9][A-Za-z0-9/-]{4,24})")

MOBILE = re.compile(r"(?<![\w-])(?:\+91[ -]?|91[ -]|0)?[6-9]\d{4}[ -]?\d{5}(?!\w)")
LAND = re.compile(r"(?<![\w-])\(?0\d{2,4}\)?[ -]?\d{3,4}[ -]?\d{3,4}(?!\w)")
INTL = re.compile(r"(?<![\w-])\+\d{1,3}[ .-]?\(?\d{1,4}\)?(?:[ .-]?\d{2,5}){2,4}(?!\w)")
NEG_CTX = re.compile(r"(?i)\b(?:inv(?:oice)?|order|ord|ref(?:erence)?|sku|serial|s/n|sn|ticket|"
                     r"case|po|tracking|awb|txn|transaction|batch|lot|model)\b[\s.#:-]*(?:id|no|number|num)?[\s.#:-]*$")

MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*"
PROTECTED = [
    ("date", re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("date", re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}\.?,?\s+\d{{2,4}}\b")),
    ("date", re.compile(rf"\b{MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b")),
    ("product/reference code", re.compile(
        r"\b(?:PROD|SKU|SN|INV|PO|ORD|REF|TKT|ITEM|MODEL|BATCH|LOT)[-#]?\s?[A-Z0-9][A-Z0-9-]{1,}\b")),
]

STREET = re.compile(r"(?i)\b(road|rd\.?|street|st\.|lane|ln\.?|nagar|colony|apartments?|apt\.?|"
                    r"flat|floor|sector|block|marg|avenue|ave\.?|layout|society|tower|towers|"
                    r"cross|phase|plot|villa|enclave|chowk)\b")
CITIES = re.compile(r"(?i)\b(mumbai|delhi|new delhi|bengaluru|bangalore|pune|chennai|hyderabad|"
                    r"kolkata|ahmedabad|jaipur|lucknow|noida|gurgaon|gurugram|kochi|indore)\b")
PIN = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")
ADDR_LABEL = re.compile(r"(?i)^[ \t]*(?:(?:permanent|current|residential|home|office|mailing|postal)[ \t]+)?"
                        r"address[ \t]*[:\-][ \t]*(.+)$")

# ------------------------------------------------------------------- names
TOK = r"[A-Z][a-z]{1,}(?:['-][A-Z]?[a-z]+)?"
NAME = rf"((?:[A-Z]\.[ \t]*)*{TOK}(?:[ \t]+(?:[A-Z]\.|{TOK})){{0,3}})"
HON = r"(?:Mr|Mrs|Ms|Miss|Dr|Prof|Shri|Smt|Sri|Mx)"
HON_RE = re.compile(rf"\b({HON})\b\.?[ \t]+{NAME}")
STRONG = (r"name|full name|employee name|candidate|applicant|customer name|patient|prepared by|"
          r"approved by|reviewed by|submitted by|signed by|signed|signature|regards|sincerely|"
          r"thanks|thank you|dear|attn|attention|author|nominee|beneficiary|witness|"
          r"reporting manager|best regards|warm regards|kind regards")
WEAK = r"from|to|cc|contact|contact person|manager|customer|client|spouse|father|mother|guardian"
LABEL_STRONG = re.compile(rf"(?i:\b(?:{STRONG})\b[ \t]*[:,\-]?[ \t]*\n?[ \t]*){NAME}")
LABEL_WEAK = re.compile(rf"(?i:\b(?:{WEAK})\b[ \t]*:[ \t]*){NAME}")

STOP = set("""phone mobile email e-mail address date name manager director pvt ltd inc llp corp
company limited office department team sincerely regards thanks thank dear contact id no number
monday tuesday wednesday thursday friday saturday sunday january february march april may june
july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec
the and for with from summary report review quarterly annual employee customer client invoice
order product serial aadhaar pan account bank landline alt alternate signature""".split())

from names_data import FIRST_NAMES, SURNAMES
GAZ_RE = re.compile(rf"(?<![\w.])({'|'.join(sorted((n.capitalize() for n in FIRST_NAMES), key=len, reverse=True))})"
                    rf"[ \t]+({TOK})\b")
SUR_RE = re.compile(rf"(?<![\w.])({TOK})[ \t]+({'|'.join(sorted((n.capitalize() for n in SURNAMES), key=len, reverse=True))})\b")
# broader context cues (lower-case so a sentence-initial capital is not mistaken for a cue); needs >= 2 name tokens
CUE_RE = re.compile(rf"\b(?i:contact|contacted|by|with|and|to|cc|ask|call|email|thanks to|chaired by|attended by|"
                    rf"approved by|signed by|met|from)[ \t]+((?:{TOK})[ \t]+(?:{TOK}))\b")
LIST_LABEL = re.compile(r"(?im)^[ \t]*(?:present|attendees?|participants?|attended|invitees?|speakers?|members?|"
                        r"panel(?:lists)?|cc|signatories|authors?)[ \t]*:[ \t]*(.+)$")
NAME_IN_LIST = re.compile(rf"(?<![\w'])({TOK}(?:[ \t]+{TOK}){{1,2}})(?![\w'])")
NONNAME = set("""project programme program budget meeting quarter office team group unit division board council
committee company limited corporation university institute college school hospital bank department ministry
agency system platform service services solutions technologies technology analytics software hardware network
review report plan policy process version release update annual quarterly monthly weekly daily north south east
west central new old first second third final draft general senior junior chief head""".split())


def _trim_name(raw: str, base: int):
    """Cut a captured name at the first stop-word; return (start,end) offsets or None."""
    end = None
    count = 0
    for m in re.finditer(r"[A-Z]\.|[A-Za-z][A-Za-z'-]*", raw):
        if m.group().rstrip(".").lower() in STOP:
            break
        end = m.end()
        count += 1
    if not end:
        return None
    return base, base + end


def detect(text: str, fb=None):
    cands: list[Cand] = []
    suppressed: list[dict] = []
    claimed: list[tuple[int, int]] = []
    prot: list[tuple[int, int, str]] = []
    for kind, rx in PROTECTED:
        for m in rx.finditer(text):
            prot.append((m.start(), m.end(), kind))
            suppressed.append({"text": m.group(), "reason": f"looks like a {kind}, not personal data"})

    def free(s, e):
        return all(e <= a or s >= b for a, b in claimed)

    def add(s, e, label, conf, source, reason=""):
        if not free(s, e):
            return False
        for a, b, kind in prot:
            if s < b and e > a and label in ("PHONE", "ID"):
                suppressed.append({"text": text[s:e], "reason": f"overlaps {kind}"})
                return False
        cands.append(Cand(s, e, text[s:e], label, conf, source, reason))
        claimed.append((s, e))
        return True

    def before(s, n=30):
        return text[max(0, s - n):s]

    # 0. user-taught strings (active learning) take priority
    if fb:
        for t, label in fb.accepted.items():
            for m in re.finditer(rf"(?<!\w){re.escape(t)}(?!\w)", text):
                add(m.start(), m.end(), label, 0.95, "user", "added from your earlier correction")

    # 1. emails
    for m in EMAIL.finditer(text):
        add(m.start(), m.end(), "EMAIL", 0.98, "regex", "email")
    for rx in (OBF1, OBF2):
        for m in rx.finditer(text):
            add(m.start(), m.end(), "EMAIL", 0.85, "regex", "obfuscated email")
    for m in UPI.finditer(text):
        add(m.start(), m.end(), "ID", 0.85, "regex", "UPI ID")

    # 2. government / financial IDs with checksum validation
    for m in AADHAAR.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if before(m.start(), 1) == "+":
            continue
        if verhoeff_ok(digits):
            add(m.start(), m.end(), "ID", 0.95, "validator", "Aadhaar (Verhoeff checksum valid)")
        elif re.search(r"(?i)aadhaa?r|uidai|\buid\b", before(m.start())):
            add(m.start(), m.end(), "ID", 0.7, "context", "labelled Aadhaar, checksum failed")
        else:
            suppressed.append({"text": m.group(), "reason": "12-digit number, Aadhaar checksum failed, no ID label"})
    for m in PAN.finditer(text):
        add(m.start(), m.end(), "ID", 0.9 if m.group()[3] in "PCHFATBLJG" else 0.6, "regex", "PAN format")
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            add(m.start(), m.end(), "ID", 0.9, "validator", "card number (Luhn valid)")
    for m in PREFIX_ID.finditer(text):
        add(m.start(), m.end(), "ID", 0.9, "regex", "prefixed ID")
    for m in CTX_ID.finditer(text):
        v = m.group(1)
        if any(ch.isdigit() for ch in v):
            add(m.start(1), m.end(1), "ID", 0.85, "context", "value after an ID label")

    # 3. phones
    for rx, conf, kind in ((MOBILE, 0.92, "mobile"), (LAND, 0.8, "landline"), (INTL, 0.8, "international")):
        for m in rx.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            ok = {"mobile": len(digits) in (10, 12, 11),
                  "landline": len(digits) in (10, 11),
                  "international": 8 <= len(digits) <= 15}[kind]
            if not ok:
                continue
            if NEG_CTX.search(before(m.start(), 20)):
                suppressed.append({"text": m.group(), "reason": "number after a reference/order/serial label"})
                continue
            add(m.start(), m.end(), "PHONE", conf, "regex", f"{kind} phone")

    # 4. addresses (line based)
    pos = 0
    lines = text.split("\n")
    offs = []
    for ln in lines:
        offs.append(pos)
        pos += len(ln) + 1
    spans = []
    for i, ln in enumerate(lines):
        s0, e0 = offs[i], offs[i] + len(ln)
        conf = None
        am = ADDR_LABEL.match(ln)
        if am:
            s0 = offs[i] + am.start(1)
            conf = 0.85
        has_pin = bool(PIN.search(ln))
        has_street = bool(STREET.search(ln))
        if conf is None:
            if has_pin and (has_street or CITIES.search(ln)):
                conf = 0.85
            elif has_street and re.search(r"\d", ln) and ln.count(",") >= 2 \
                    and not re.search(r"(?i)\b(room|version|v\d)", ln):
                conf = 0.65            # weak rule needs address-like comma structure, not just 'Block'
        if conf is None:
            continue
        if i + 1 < len(lines) and not has_pin and PIN.search(lines[i + 1]) \
                and not ADDR_LABEL.match(lines[i + 1]):
            e0 = offs[i + 1] + len(lines[i + 1])
            conf = max(conf, 0.8)
        spans.append((s0, e0, conf))
    for s0, e0, conf in spans:
        pieces = [(s0, e0)]
        for a, b in sorted(claimed):
            nxt = []
            for ps, pe in pieces:
                if b <= ps or a >= pe:
                    nxt.append((ps, pe))
                else:
                    if a > ps: nxt.append((ps, a))
                    if b < pe: nxt.append((b, pe))
            pieces = nxt
        pieces = [(a, b) for a, b in pieces if len(text[a:b].strip()) >= 8]
        if pieces:
            a, b = max(pieces, key=lambda p: p[1] - p[0])
            seg = text[a:b]
            a += len(seg) - len(seg.lstrip(" \t,;|"))
            b -= len(seg) - len(seg.rstrip(" \t,;|"))
            add(a, b, "ADDRESS", conf, "regex", "street/pincode pattern")

    # 5. names (seeds; linking expands them)
    hints = []
    for m in HON_RE.finditer(text):
        r = _trim_name(m.group(2), m.start(2))
        if r:
            add(m.start(), r[1], "NAME", 0.9, "rule", "honorific + name")
    for rx in (LABEL_STRONG, LABEL_WEAK):
        for m in rx.finditer(text):
            r = _trim_name(m.group(1), m.start(1))
            if r:
                add(r[0], r[1], "NAME", 0.85, "rule", "name after a label/greeting")
    for m in GAZ_RE.finditer(text):
        r = _trim_name(m.group(0), m.start())
        if r and len(text[r[0]:r[1]].split()) >= 2:
            add(r[0], r[1], "NAME", 0.65, "gazetteer", "common first name + surname")

    def plausible(s):
        ws = [w.lower() for w in re.findall(r"[A-Za-z]+", s)]
        return len(ws) >= 2 and not any(w in STOP or w in NONNAME for w in ws) and not CITIES.search(s)
    for m in SUR_RE.finditer(text):
        if plausible(m.group(0)):
            add(m.start(), m.end(), "NAME", 0.6, "gazetteer", "capitalised word + common surname")
    for lm in LIST_LABEL.finditer(text):                      # "Present: A B, C D and E F"
        for m in NAME_IN_LIST.finditer(lm.group(1)):
            if plausible(m.group(1)):
                s0 = lm.start(1) + m.start(1)
                add(s0, s0 + len(m.group(1)), "NAME", 0.75, "rule", "name in an attendee/participant list")
    for m in CUE_RE.finditer(text):
        if plausible(m.group(1)):
            add(m.start(1), m.end(1), "NAME", 0.5, "rule", "two capitalised words after a cue word (low confidence)")
    for c in cands:
        if c.label == "EMAIL" and "@" in c.text:
            parts = re.split(r"[._-]", c.text.split("@")[0])
            parts = [p for p in parts if p.isalpha()]
            if 2 <= len(parts) <= 3:
                hints.append(" ".join(p.capitalize() if len(p) > 1 else p.upper() + "." for p in parts))

    if fb:
        kept = []
        for c in cands:
            if fb.is_rejected(c.text):
                suppressed.append({"text": c.text, "reason": "rejected by you earlier"})
            else:
                kept.append(c)
        cands = kept
    cands.sort(key=lambda c: c.start)
    return cands, suppressed, hints


# ------------------------------------------------------------ optional SLM
def slm_verify(text: str, cand: Cand, model: str = "qwen2.5:1.5b", host: str = "http://localhost:11434"):
    """Ask a local Ollama model whether a low-confidence span is personal data.
    Returns True/False, or None when Ollama is unreachable (rules decide)."""
    import json, urllib.request
    ctx = text[max(0, cand.start - 80):cand.end + 80]
    prompt = (f"Context: ...{ctx}...\nIs the exact string \"{cand.text}\" personal data of type "
              f"{cand.label} (a real person's name/contact/ID/address, not a product code, company or date)? "
              f"Answer only YES or NO.")
    try:
        req = urllib.request.Request(f"{host}/api/generate", method="POST",
                                     data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                                                      "options": {"temperature": 0}}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)["response"].strip().upper().startswith("YES")
    except Exception:
        return None
