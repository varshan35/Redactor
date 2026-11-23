"""Forensic inspector: look inside the EXPORTED file, not the original.

It re-reads the exported PDF the same ways verify_pdf does (four text extractors, raw + decoded content
streams, document metadata) and lets the reviewer type any string to see how many times each source still
contains it. It also reports a SHA-256 of the exported file and what the file structurally contains.

Honest scope: a SHA-256 only shows the file has not changed since export; it does not prove redaction.
The redaction claim rests on the searches below plus the construction of the file (page = image, the only
text is an invisible layer made from the redacted words, no original fonts/text objects/annotations).
"""
from __future__ import annotations
import hashlib, os, re
from redact import collect_sources

_CACHE = {}          # path -> (mtime, size, sources, facts); one export at a time, so this stays tiny


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _load(path: str):
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    hit = _CACHE.get(path)
    if hit and hit[0] == key:
        return hit[1], hit[2]
    if path.lower().endswith(".pdf"):
        sources, facts = collect_sources(path)
    else:
        sources = {"text file": open(path, encoding="utf-8", errors="ignore").read()}
        facts = {"pages": 1, "images": 0, "decoded_streams": 0, "fonts": [], "annotations_present": False,
                 "has_xmp": False, "docinfo_fields": {}}
    _CACHE[path] = (key, sources, facts)
    return sources, facts


def _norm(s): return re.sub(r"\s+", " ", s).casefold().strip()
def _compact(s): return re.sub(r"\W", "", s).casefold()


def overview(path: str) -> dict:
    """Panel contents that need no query: checksum + structure. Never contains document text."""
    sources, facts = _load(path)
    fields = facts["docinfo_fields"]
    return {"file": os.path.basename(path), "bytes": os.path.getsize(path), "sha256": sha256(path),
            "kind": "pdf" if path.lower().endswith(".pdf") else "txt",
            "sources": list(sources), "pages": facts["pages"], "images": facts["images"],
            "fonts": facts["fonts"], "annotations_present": facts["annotations_present"],
            "metadata_fields": {k: ("(empty)" if not v.strip() else v) for k, v in fields.items()},
            "xmp_present": facts["has_xmp"]}


def search(path: str, query: str) -> dict:
    """Occurrences of `query` per source in the exported file (case-insensitive; whitespace-insensitive;
    a second 'compact' pass ignores punctuation/spacing so '9876 5432 1098' also finds '987654321098')."""
    q = query.strip()
    if len(q) < 2:
        return {"query": q, "error": "type at least 2 characters"}
    sources, _ = _load(path)
    qn, qc = _norm(q), _compact(q)
    rows, total = [], 0
    for name, blob in sources.items():
        exact = _norm(blob).count(qn)
        loose = _compact(blob).count(qc) if len(qc) >= 3 else 0
        hits = max(exact, loose)
        rows.append({"source": name, "hits": hits, "length": len(blob)})
        total += hits
    return {"query": q, "found": total > 0, "total": total, "rows": rows, "sha256": sha256(path)}
