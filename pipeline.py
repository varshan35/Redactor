"""analyze() -> candidates for review; export() -> irreversible redacted copy."""
from __future__ import annotations
from ingest import load
from detect import detect
from link import link
from slm import assist
from feedback import Feedback
from redact import redact_txt, redact_pdf, verify_pdf


def analyze(path: str, fb: Feedback | None = None, use_slm: bool = False):
    """use_slm defaults to False so tests/evals are deterministic; the app turns it on."""
    doc = load(path)
    cands, suppressed, hints = detect(doc.text, fb)
    cands, slm_info = assist(doc.text, cands, fb, enabled=use_slm)
    cands, entities = link(doc.text, cands, hints, fb)
    return {"doc": doc, "cands": cands, "suppressed": suppressed, "entities": entities, "slm": slm_info}


def export(analysis, approved, out_path: str):
    doc = analysis["doc"]
    if doc.kind == "txt":
        text = redact_txt(doc, approved, out_path)
        return {"path": out_path, "text": text}
    redact_pdf(doc, approved, out_path)
    removed = [c.text for c in approved]
    return {"path": out_path, "verification": verify_pdf(out_path, removed)}
