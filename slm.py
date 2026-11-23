"""Small-model assistance for detection (local Ollama). Two jobs, both optional:

  verify   low-confidence NAME candidates -> model says person / not a person; the confidence moves
           up or down and the reason says why. Nothing is silently dropped: the reviewer decides.
  discover capitalised phrases the rules did NOT flag -> model picks the ones that are real people;
           those are added as low-confidence NAME candidates.

Calls are batched (a handful of prompts per document, not one per phrase). If Ollama is not running
this does nothing and the pipeline continues with rules only."""
from __future__ import annotations
import os, re, time
from detect import Cand, STOP, NONNAME, CITIES
from summarize import ollama_model, _http

SYSTEM = ("You classify short phrases taken from a document. Answer with ONLY the numbers of the phrases "
          "that match, separated by commas, or the word NONE. No explanations.")
CAP = re.compile(r"(?<![\w'])[A-Z][a-z]{2,}(?:[ \t]+[A-Z][a-z]{2,}){1,2}(?![\w'])")
MAX_DISCOVER = int(os.environ.get("REDACTOR_SLM_MAX", "40"))
BATCH = 20


def _ctx(text, s, e, n=45):
    return text[max(0, s - n):e + n].replace("\n", " ")


_CACHE: dict = {}          # identical question+items -> answer; makes rescans and re-uploads instant


def _ask(model, question, items, timeout=90):
    """items: [(phrase, context)] -> set of 0-based indices the model selects."""
    key = (model, question, tuple(items))
    if key in _CACHE:
        return set(_CACHE[key])
    ans = _ask_uncached(model, question, items, timeout)
    _CACHE[key] = frozenset(ans)
    return ans


def _ask_uncached(model, question, items, timeout=90):
    lines = [f"{i + 1}. {p} | ...{c}..." for i, (p, c) in enumerate(items)]
    prompt = f"{question}\n\n" + "\n".join(lines) + "\n\nAnswer (numbers separated by commas, or NONE):"
    r = _http("/api/generate", {"model": model, "system": SYSTEM, "prompt": prompt, "stream": False,
                                "options": {"temperature": 0, "num_predict": 40}}, timeout=timeout)
    ans = r["response"].strip()
    if ans.upper().startswith("NONE"):
        return set()
    return {int(n) - 1 for n in re.findall(r"\d+", ans.split("\n")[0]) if 0 < int(n) <= len(items)}


def assist(text: str, cands: list[Cand], fb=None, enabled: bool = True):
    info = {"used": False, "model": None, "calls": 0, "seconds": 0.0, "verified": 0, "downgraded": 0,
            "discovered": 0, "note": ""}
    if not enabled or os.environ.get("REDACTOR_SLM") == "0":
        info["note"] = "small model assist is off"
        return cands, info
    model = ollama_model()
    if not model:
        info["note"] = "Ollama not running: rules only"
        return cands, info
    t0 = time.time()
    info.update(used=True, model=model)
    out = list(cands)
    try:
        # 1. verify low-confidence names
        low = [c for c in out if c.label == "NAME" and c.conf < 0.7 and c.source != "user"]
        for i in range(0, len(low), BATCH):
            chunk = low[i:i + BATCH]
            yes = _ask(model, "Which of these phrases are the names of real people (not companies, places, "
                       "products, job titles or headings)?", [(c.text, _ctx(text, c.start, c.end)) for c in chunk])
            info["calls"] += 1
            for j, c in enumerate(chunk):
                if j in yes:
                    c.conf, c.reason = max(c.conf, 0.8), "confirmed by small model: " + (c.reason or c.source)
                    info["verified"] += 1
                else:
                    c.conf, c.reason = min(c.conf, 0.4), "small model doubts this is a person: " + (c.reason or c.source)
                    info["downgraded"] += 1
        # 2. discover capitalised phrases the rules missed
        claimed = [(c.start, c.end) for c in out]
        seen, found = set(), []
        for m in CAP.finditer(text):
            ph = m.group(0)
            ws = [w.lower() for w in re.findall(r"[A-Za-z]+", ph)]
            if ph.lower() in seen or any(w in STOP or w in NONNAME for w in ws) or CITIES.search(ph):
                continue
            if any(m.start() < b and m.end() > a for a, b in claimed):
                continue
            if fb and fb.is_rejected(ph):
                continue
            seen.add(ph.lower()); found.append(m)
            if len(found) >= MAX_DISCOVER:
                break
        for i in range(0, len(found), BATCH):
            chunk = found[i:i + BATCH]
            yes = _ask(model, "Which of these phrases are the full names of real people (not companies, "
                       "places, products, job titles, courses or headings)?",
                       [(m.group(0), _ctx(text, m.start(), m.end())) for m in chunk])
            info["calls"] += 1
            for j, m in enumerate(chunk):
                if j in yes:
                    for mm in re.finditer(re.escape(m.group(0)), text):     # every occurrence of that name
                        if not any(mm.start() < b and mm.end() > a for a, b in claimed):
                            out.append(Cand(mm.start(), mm.end(), mm.group(0), "NAME", 0.6, "slm",
                                            "found by small model (no rule matched)"))
                            claimed.append((mm.start(), mm.end()))
                    info["discovered"] += 1
    except Exception as e:                                  # model slow/unavailable: keep rule results
        info["note"] = f"small model stopped early ({type(e).__name__}); rule results kept"
    info["seconds"] = round(time.time() - t0, 1)
    out.sort(key=lambda c: c.start)
    return out, info
