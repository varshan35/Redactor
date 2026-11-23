"""Leak-free summary.

Order of operations (the summarizer never sees the original text):
  1. build the redacted text from the user's APPROVED redactions
  2. summarize it: local Ollama model if running, otherwise a rule-based
     extractive summary (no model, no network)
  3. check the summary: (a) exact + fuzzy search for every removed string and
     its parts, (b) re-run the PII detector on the summary, (c) placeholder
     consistency, (d) quasi-identifier combinations across the whole summary
  4. scrub / generalise what was found, re-check, and fall back to the rule
     based summary if an Ollama summary still fails
"""
from __future__ import annotations
import difflib, json, os, re, urllib.request
from collections import Counter
from detect import detect, CITIES
from redact import placeholders, _merge
from link import HON

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
PREFERRED = ["qwen2.5:1.5b", "qwen2.5:3b", "llama3.2:1b", "llama3.2:3b", "qwen2.5:0.5b",
             "gemma2:2b", "phi3:mini"]
PH_RE = re.compile(r"\[(?:NAME|EMAIL|PHONE|ADDRESS|ID)_\d+\]")

SYSTEM = ("You are a privacy-safe summarizer. The text contains placeholders such as [NAME_1] or "
          "[EMAIL_2] where personal data was removed. Rules: keep placeholders exactly as written; "
          "never guess, infer or invent who a person is, their employer, age, city or any detail that is "
          "not stated; do not add information that is not in the text; do not mention that text was "
          "removed. Write a neutral summary of 3 to 5 sentences.")


# ------------------------------------------------------------------ helpers
def redacted_text(doc, approved):
    ph = placeholders(approved)
    spans = _merge([(c.start, c.end, ph[i]) for i, c in enumerate(approved)])
    t = doc.text
    for s, e, p in reversed(spans):
        t = t[:s] + p + t[e:]
    return t, ph


def _http(path, payload=None, timeout=5):
    req = urllib.request.Request(HOST + path, method="POST" if payload else "GET",
                                 data=json.dumps(payload).encode() if payload else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ollama_model():
    """Name of a usable local model, or None if Ollama isn't running / has no model."""
    try:
        names = [m["name"] for m in _http("/api/tags", timeout=2).get("models", [])]
    except Exception:
        return None
    want = os.environ.get("REDACTOR_MODEL")
    if want:
        return want if any(n.startswith(want) for n in names) else None
    for p in PREFERRED:
        for n in names:
            if n == p or n.startswith(p.split(":")[0] + ":" + p.split(":")[1]):
                return n
    return names[0] if names else None


def _gen(model, prompt, timeout=180):
    r = _http("/api/generate", {"model": model, "system": SYSTEM, "prompt": prompt, "stream": False,
                                "options": {"temperature": 0, "num_predict": 300}}, timeout=timeout)
    return r["response"].strip()


def summarize_ollama(red: str, model: str) -> str:
    if len(red) <= 3500:
        return _gen(model, f"Summarize this document:\n\n{red}")
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", red):          # map-reduce for long documents
        if len(cur) + len(para) > 3000 and cur:
            chunks.append(cur); cur = ""
        cur += para + "\n\n"
    chunks.append(cur)
    parts = [_gen(model, f"Summarize this part of a longer document in at most 3 sentences:\n\n{c}")
             for c in chunks]
    return _gen(model, "Combine these partial summaries into one summary of 3 to 5 sentences:\n\n"
                + "\n".join(f"- {p}" for p in parts))


# ----------------------------------------------------- rule-based fallback
STOPW = set("""a an the and or but if of to in on at for from by with as is are was were be been it its this that
these those he she they we you i his her their our your not no yes do does did has have had will would can could
should may might also than then so such into over under about after before during while who whom which what when
where how all any each more most other some per via""".split())


def summarize_rules(red: str, k: int = 4) -> str:
    sents = []
    paras, cur = [], ""
    for line in red.split("\n"):                  # rejoin lines that PDF layout wrapped mid-sentence
        line = line.strip()
        if not line:
            if cur: paras.append(cur); cur = ""
            continue
        if cur and len(cur) >= 60 and not re.search(r"[.!?:]$", cur) and not re.match(r"^[A-Z][\w ]{1,30}:\s", line):
            cur += " " + line
        else:
            if cur: paras.append(cur)
            cur = line
    if cur: paras.append(cur)
    SENT = r"(?<=[.!?])(?<!\bno\.)(?<!\bMs\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bvs\.)(?<!\betc\.)\s+"
    for line in paras:
        for s in re.split(SENT, line):
            if len(re.findall(r"[A-Za-z]{2,}", PH_RE.sub("", s))) >= 5:
                sents.append(s.strip())
    if not sents:                                    # key/value style forms
        lines = [l.strip() for l in red.split("\n") if l.strip()]
        return " ".join(lines[:3])
    words = [w for s in sents for w in re.findall(r"[a-z]{3,}", PH_RE.sub("", s).lower()) if w not in STOPW]
    freq = Counter(words)
    scored = []
    for i, s in enumerate(sents):
        ws = [w for w in re.findall(r"[a-z]{3,}", PH_RE.sub("", s).lower()) if w not in STOPW]
        if not ws:
            continue
        score = sum(freq[w] for w in ws) / (len(ws) ** 0.7) + (1.0 if i == 0 else 0)
        scored.append((score, i, s))
    top = sorted(sorted(scored, reverse=True)[:k], key=lambda x: x[1])
    return " ".join(s for _, _, s in top)


# ----------------------------------------------------------- leak checking
def _needles(approved, ph, red):
    """(needle regex, source placeholder, kind) for every removed string and its parts."""
    out, red_cf = [], red.casefold()
    for i, c in enumerate(approved):
        t, p = c.text, ph[i]
        pats = [(re.escape(t).replace(r"\ ", r"\s+"), "full string", t)]      # (regex, kind, literal)
        if c.label == "NAME":
            for tok in re.findall(r"[A-Za-z][A-Za-z'-]+", t):
                if tok.lower() not in HON and len(tok) >= 2:
                    pats.append((rf"\b{re.escape(tok)}\b", "name part", tok))
        elif c.label == "EMAIL":
            local, _, dom = t.partition("@")
            if dom:
                pats += [(re.escape(local), "email local part", local), (re.escape(dom), "email domain", dom)]
                label = dom.split(".")[0]
                if len(label) >= 4 and label.lower() not in ("gmail", "yahoo", "outlook", "hotmail", "mail"):
                    pats.append((rf"\b{re.escape(label)}\b", "email domain name", label))
        elif c.label in ("PHONE", "ID"):
            d = re.sub(r"\D", "", t)
            if len(d) >= 6:
                pats.append((r"[\s.-]*".join(d), "digits", d))
        elif c.label == "ADDRESS":
            for pin in re.findall(r"(?<!\d)\d{6}(?!\d)", t):
                pats.append((pin, "pincode", pin))
            for ch in re.split(r"[,\n]", t):
                if len(ch.strip()) >= 8:
                    pats.append((re.escape(ch.strip()), "address part", ch.strip()))
        for rx, kind, lit in pats:
            if len(lit) >= 2 and lit.casefold() not in red_cf:     # still visible in doc => not a leak
                out.append((rx, p, kind, t))
    return out


def find_leaks(summary, approved, ph, red):
    leaks = []
    for rx, p, kind, src in _needles(approved, ph, red):
        for m in re.finditer(rx, summary, re.I):
            leaks.append({"found": m.group(), "span": m.span(), "kind": kind, "placeholder": p, "removed": src})
    # fuzzy: near-misspellings of removed name parts
    toks = {}
    for i, c in enumerate(approved):
        if c.label == "NAME":
            for t in re.findall(r"[A-Za-z]{5,}", c.text):
                if t.lower() not in HON and t.casefold() not in red.casefold():
                    toks[t.lower()] = ph[i]
    for m in re.finditer(r"[A-Za-z]{5,}", summary):
        w = m.group().lower()
        if w in toks:
            continue
        near = difflib.get_close_matches(w, toks.keys(), n=1, cutoff=0.86)
        if near:
            leaks.append({"found": m.group(), "span": m.span(), "kind": "near-match",
                          "placeholder": toks[near[0]], "removed": near[0]})
    seen, uniq = set(), []
    for l in sorted(leaks, key=lambda x: (x["span"][0], -x["span"][1])):
        if not any(l["span"][0] < s[1] and l["span"][1] > s[0] for s in seen):
            seen.add(l["span"]); uniq.append(l)
    return uniq


def scrub(summary, leaks):
    for l in sorted(leaks, key=lambda x: -x["span"][0]):
        a, b = l["span"]
        summary = summary[:a] + l["placeholder"] + summary[b:]
    return summary


def detector_hits(summary, red):
    cands, _, _ = detect(summary)
    return [{"text": c.text, "label": c.label, "conf": round(c.conf, 2)}
            for c in cands if c.text.casefold() not in red.casefold()]


# ----------------------------------------------- quasi-identifier handling
ROLE_HIGH = re.compile(r"\b(ceo|cfo|cto|coo|cio|ciso|chief [a-z]+ officer|founder|co-founder|president|executive|"
                       r"vice[- ]president|vp|managing director|chairman|chairperson|chairwoman|"
                       r"head of [a-z]+|general manager|director|partner|principal|dean|minister|judge)\b", re.I)
ROLE_LOW = re.compile(r"\b(manager|engineer|doctor|surgeon|lawyer|attorney|teacher|professor|analyst|"
                      r"consultant|accountant|nurse|officer|supervisor|developer|architect)\b", re.I)
CITY_NAMES = ("mumbai|delhi|new delhi|bengaluru|bangalore|pune|chennai|hyderabad|kolkata|ahmedabad|jaipur|"
              "lucknow|noida|gurgaon|gurugram|kochi|indore|surat|nagpur|bhopal|chandigarh|london|new york|"
              "san francisco|singapore|dubai|toronto|sydney")
CITY_RX = re.compile(rf"\b(?:{CITY_NAMES})\b", re.I)
BASED_RX = re.compile(r"\b[A-Z][a-z]+(?=-based\b)")
AGE_RX = re.compile(r"\b(\d{2})[- ]year[- ]old\b|\baged?\s+\d{2}\b|\b\d{2}\s*(?:yrs|years)\s+old\b", re.I)
YEAR_RX = re.compile(r"\b(?:19|20)\d{2}\b")
ORGKIND = re.compile(r"\b(startup|fintech|firm|company|bank|hospital|university|school|ministry|agency)\b", re.I)


REGION_WORDS = ("India", "Asia", "Europe", "America", "Australia")


def _loc(s):
    """A specific place (city or 'Xxx-based'); broad regions such as 'Western India-based' don't count."""
    m = CITY_RX.search(s)
    if m:
        return m
    return next((x for x in BASED_RX.finditer(s) if x.group() not in REGION_WORDS), None)


def _cats(s):
    c = set()
    if ROLE_HIGH.search(s): c.add("senior role")
    elif ROLE_LOW.search(s): c.add("role")
    if _loc(s): c.add("location")
    if AGE_RX.search(s): c.add("age")
    if YEAR_RX.search(s): c.add("year")
    return c


def _risky(c):
    return (("senior role" in c and (c & {"location", "age", "year"})) or
            ("role" in c and "location" in c and (c & {"age", "year"})) or
            ("location" in c and "age" in c))


REGION = {"mumbai": "Western India", "pune": "Western India", "ahmedabad": "Western India", "surat": "Western India",
          "delhi": "Northern India", "new delhi": "Northern India", "noida": "Northern India",
          "gurgaon": "Northern India", "gurugram": "Northern India", "lucknow": "Northern India",
          "chandigarh": "Northern India", "jaipur": "Northern India",
          "bengaluru": "Southern India", "bangalore": "Southern India", "chennai": "Southern India",
          "hyderabad": "Southern India", "kochi": "Southern India", "kolkata": "Eastern India",
          "indore": "Central India", "bhopal": "Central India", "nagpur": "Central India",
          "london": "Europe", "new york": "North America", "san francisco": "North America",
          "toronto": "North America", "singapore": "Southeast Asia", "dubai": "the Middle East",
          "sydney": "Australia"}
TECH_DOMAIN = r"robotics|fintech|biotech|healthtech|edtech|ai|saas|software|semiconductor|cybersecurity|deeptech"
OTHER_DOMAIN = r"logistics|e-?commerce|pharma|retail|manufacturing|energy|media|consulting"
ORG_RX = re.compile(rf"\b(?:(?P<tech>{TECH_DOMAIN})|(?P<other>{OTHER_DOMAIN}))\s+(?:startup|firm|company)\b", re.I)
FOUNDED_RX = re.compile(r"[,\s]*\b(?:founded|established|incorporated|started|launched)\s+in\s+(?:19|20)\d{2}\b", re.I)


def _generalise(s, changes=None):
    """Soften quasi-identifiers. If `changes` is a list, every substitution is appended as {from,to,kind}."""
    def sub(rx, repl, text, kind, flags=re.I):
        def f(m):
            new = repl(m) if callable(repl) else repl
            if changes is not None and m.group().strip() and m.group().strip() != new.strip():
                changes.append({"from": m.group().strip(" ,"), "to": new.strip(), "kind": kind})
            return new
        return rx.sub(f, text) if isinstance(rx, re.Pattern) else re.sub(rx, f, text, flags=flags)

    reg = lambda name: REGION.get(re.sub(r"\s+", " ", name.lower()), "a city")
    s = sub(FOUNDED_RX, "", s, "year")
    s = sub(ORG_RX, lambda m: "tech company" if m.group("tech") else "company", s, "organisation")
    s = sub(rf"\b({CITY_NAMES})-based\b", lambda m: reg(m.group(1)) + "-based", s, "location")
    s = sub(BASED_RX.pattern, lambda m: m.group() if m.group() in REGION_WORDS else "city",
            s, "location", flags=0)
    s = sub(rf"\b(?:{CITY_NAMES})\b", lambda m: reg(m.group()), s, "location")
    s = sub(r"[,\s]*\b(?:aged?\s+\d{2}|\d{2}\s*(?:yrs|years)\s+old)\b", "", s, "age")
    s = sub(r"\b\d{2}[- ]year[- ]old\s*", "", s, "age")
    s = sub(r"\b(?:in|since|during|of|from)\s+(?:19|20)\d{2}\b", "in recent years", s, "year")
    s = sub(ROLE_HIGH.pattern, "senior executive", s, "role")
    s = re.sub(r"\b(?:senior )+(senior executive)\b", r"\1", s)
    s = sub(r"\b(?:19|20)\d{2}\b", "a prior year", s, "year")
    return re.sub(r"\s{2,}", " ", s).strip() if changes is not None else re.sub(r"\s{2,}", " ", s)


# --- rule-based re-identification risk. A HEURISTIC on which kinds of detail co-occur; no population data,
# --- so it never claims a count of matching people.
LEVELS = {"Low": 0, "Medium": 1, "High": 2}
SENT_SPLIT = re.compile(r"(?<=[.!?])(?<!\bMs\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)\s+")


def risk_assess(text):
    m_role = ROLE_HIGH.search(text) or ROLE_LOW.search(text)
    senior = bool(ROLE_HIGH.search(text))
    m_loc = _loc(text)
    anchor = (m_role or m_loc).start() if (m_role or m_loc) else 0
    near = lambda rx: min(rx.finditer(text), key=lambda m: abs(m.start() - anchor), default=None)
    m_age = near(AGE_RX)                  # the year/age closest to the role or place, not just the first in the text
    m_year = near(YEAR_RX)
    m_org = ORG_RX.search(text)
    cats = _cats(text)
    if senior and m_loc and (m_age or m_year):
        level = "High"
    elif _risky(cats):
        level = "Medium"
    else:
        level = "Low"
    terms = [x.group() for x in (m_role, m_loc, m_org, m_year, m_age) if x]
    terms = [re.sub(r"-based$", "", t) for t in terms]
    query = None
    if level != "Low":
        query = "site:linkedin.com " + " ".join(f'"{t}"' for t in dict.fromkeys(terms))
    return {"level": level, "categories": sorted(cats), "terms": list(dict.fromkeys(terms)), "query": query}


def risk_in_document(red):
    """Worst sentence of the (redacted) document body, so a reviewer sees the same combination is still in the file."""
    flat = re.sub(r"\s*\n\s*", " ", red)
    best = {"level": "Low", "categories": [], "terms": [], "query": None}
    for sent in SENT_SPLIT.split(flat):
        r = risk_assess(sent)
        if LEVELS[r["level"]] > LEVELS[best["level"]]:
            best = r
    return best


def qid_check(summary):
    """Return (findings, generalised_summary). Sentence level + whole-summary level."""
    sents = re.split(r"(?<=[.!?])\s+", summary.strip())
    findings = []
    allc = _cats(summary)                            # score the WHOLE summary first
    if _risky(allc):
        per = [_cats(s) for s in sents]
        level = "sentence" if any(_risky(c) for c in per) else "summary"
        changes = []
        g = _generalise(summary, changes)
        if g != summary:
            findings.append({"level": level, "categories": sorted(allc),
                             "original": summary, "generalised": g, "changes": changes})
            summary = g
    return findings, summary


# ------------------------------------------------------------------- main
def full_check(summary, approved, ph, red):
    placeholders_in = set(PH_RE.findall(summary))
    return {"leaks": find_leaks(summary, approved, ph, red),
            "unknown_placeholders": sorted(placeholders_in - set(PH_RE.findall(red))),
            "detector_hits": detector_hits(summary, red),
            "qid": [f for f in qid_check(summary)[0]]}


def make_summary(doc, approved):
    red, ph = redacted_text(doc, approved)
    log = []
    model = ollama_model()
    method, summary = "rules", None
    if model:
        try:
            summary, method = summarize_ollama(red, model), f"ollama:{model}"
        except Exception as e:
            log.append(f"Ollama call failed ({type(e).__name__}); used rule-based summary")
    else:
        log.append("Ollama not running or no model installed; used rule-based summary")
    if summary is None:
        summary, method = summarize_rules(red), "rules"

    def clean(s):
        steps = []
        leaks = find_leaks(s, approved, ph, red)
        if leaks:
            steps.append(f"scrubbed {len(leaks)} leaked fragment(s): " + ", ".join(repr(l["found"]) for l in leaks))
            s = scrub(s, leaks)
        bad = set(PH_RE.findall(s)) - set(PH_RE.findall(red))
        for b in bad:
            s = s.replace(b, "[REDACTED]"); steps.append(f"removed unknown placeholder {b}")
        q, s = qid_check(s)
        for f in q:
            steps.append(f"generalised quasi-identifier combination ({', '.join(f['categories'])})")
        return s, steps, q

    summary, steps, qid = clean(summary)
    log += steps
    final = full_check(summary, approved, ph, red)
    if method.startswith("ollama") and (final["leaks"] or final["detector_hits"]):
        log.append("Ollama summary still failed the check; replaced by rule-based summary")
        summary, steps, qid = clean(summarize_rules(red))
        log += steps
        method = "rules (fallback after failed check)"
        final = full_check(summary, approved, ph, red)
    ok = not final["leaks"] and not final["unknown_placeholders"] and not final["detector_hits"]
    raw = qid[0]["original"] if qid else summary          # leak-scrubbed but not yet generalised
    changes = qid[0]["changes"] if qid else []
    risk = {"before": risk_assess(raw), "after": risk_assess(summary), "changes": changes,
            "raw_summary": raw, "document": risk_in_document(red),
            "note": "Heuristic from keyword rules (role, place, year, age). No population data is used, "
                    "so this does not estimate how many people match."}
    return {"summary": summary, "method": method, "ok": ok, "log": log, "risk": risk,
            "qid_findings": qid, "remaining": {k: final[k] for k in ("leaks", "unknown_placeholders", "detector_hits")},
            "redacted_text": red}
