"""Local review UI. Run:  python3 app.py   then open http://127.0.0.1:5000
Everything stays on this machine; there are no outbound calls."""
from __future__ import annotations
import io, os
from flask import Flask, request, jsonify, send_file, render_template
from PIL import Image, ImageDraw
import pypdfium2 as pdfium
from pipeline import analyze, export
from feedback import Feedback, doc_key
from report import build_report, render_report_html
from sample_doc import make_sample_pdf
from link import similar
from detect import Cand
from ingest import boxes_for_span
from summarize import make_summary, ollama_model
import forensic

app = Flask(__name__)
WORK = os.environ.get("REDACTOR_WORK", "work")
os.makedirs(WORK, exist_ok=True)
fb = Feedback(os.path.join(WORK, "feedback.json"))
S = {"a": None, "path": None, "status": {},     # single-user local session
     "slm": os.environ.get("REDACTOR_SLM", "1") != "0"}   # small-model assist on by default; falls back to rules
COLORS = {"NAME": (37, 99, 235), "EMAIL": (22, 163, 74), "PHONE": (234, 88, 12),
          "ADDRESS": (13, 148, 136), "ID": (147, 51, 234)}


def _run(path):
    old = S["status"]
    fb.set_doc(doc_key(path))               # remembered rejects only apply to THIS document
    S["a"] = analyze(path, fb, use_slm=S["slm"])
    S["path"] = path
    keys = {(c.start, c.end) for c in S["a"]["cands"]}
    S["status"] = {k: v for k, v in old.items() if k in keys}


def _cands():
    return S["a"]["cands"]


def _state():
    a = S["a"]
    return {"kind": a["doc"].kind, "text": a["doc"].text, "pages": len(a["doc"].pages),
            "entities": a["entities"], "suppressed": a["suppressed"],
            "slm": dict(a.get("slm") or {}, enabled=S["slm"]),
            "cands": [{"id": i, "start": c.start, "end": c.end, "text": c.text, "label": c.label,
                       "conf": round(c.conf, 2), "group": c.group, "ambiguous": c.ambiguous,
                       "reason": c.reason, "source": c.source,
                       "status": S["status"].get((c.start, c.end), "pending")}
                      for i, c in enumerate(_cands())]}


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/upload")
def upload():
    f = request.files["file"]
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".txt", ".pdf"):
        return jsonify(error="Only .txt and text-based .pdf are supported"), 400
    path = os.path.join(WORK, "input" + ext)
    f.save(path)
    return _open(path, f.filename)


def _open(path, display_name):
    S["status"] = {}; S["verification"] = None; S["export_path"] = None; S["export_sha256"] = None; S["summary_info"] = None; S["name"] = display_name
    try:
        _run(path)
    except Exception as e:
        return jsonify(error=f"Could not read file: {e}"), 400
    if not S["a"]["doc"].text.strip():
        return jsonify(error="No extractable text (scanned/image-only PDFs are out of scope)"), 400
    return jsonify(_state())


@app.post("/api/demo")
def demo():
    """Load the built-in synthetic demo document (no file dialog needed)."""
    return _open(make_sample_pdf(os.path.join(WORK, "input.pdf")), "demo-review.pdf")


@app.get("/api/state")
def state():
    if not S["a"]:
        return jsonify(error="no document"), 404
    return jsonify(_state())


@app.post("/api/decide")
def decide():
    d = request.json
    c = _cands()[d["id"]]
    targets = similar(_cands(), c) if d.get("similar") else [c]
    for t in targets:
        if d["status"] == "pending":
            S["status"].pop((t.start, t.end), None)
        else:
            S["status"][(t.start, t.end)] = d["status"]
    if d["status"] == "rejected":          # active learning: remember false positives
        fb.reject(c.text)
    return jsonify(_state())


@app.post("/api/bulk")
def bulk():
    d = request.json                       # {"min_conf": 0.85}
    for c in _cands():
        if c.conf >= d["min_conf"] and not c.ambiguous and (c.start, c.end) not in S["status"]:
            S["status"][(c.start, c.end)] = "approved"
    return jsonify(_state())


@app.post("/api/add")
def add():
    d = request.json                       # {"start","end","label","similar"}
    text = S["a"]["doc"].text
    s, e = int(d["start"]), int(d["end"])
    seg = text[s:e]
    stripped = seg.strip()
    s += len(seg) - len(seg.lstrip()); e = s + len(stripped)
    if len(stripped) < 2:
        return jsonify(error="selection too short"), 400
    fb.accept(stripped, d["label"])        # active learning: remember missed items
    _run(S["path"])                        # rescan; taught string now found everywhere it occurs
    for c in _cands():
        if c.text == stripped and (d.get("similar") or (c.start, c.end) == (s, e)):
            S["status"][(c.start, c.end)] = "approved"
    return jsonify(_state())


@app.post("/api/slm")
def toggle_slm():
    """Turn the small-model assist on/off and rescan (approvals on unchanged spans are kept)."""
    S["slm"] = bool(request.json.get("enabled"))
    if S["path"]:
        _run(S["path"])
        return jsonify(_state())
    return jsonify(ok=True)


@app.post("/api/reset_learning")
def reset_learning():
    """Forget every remembered accept/reject (they persist across documents and sessions)."""
    fb.clear()
    _run(S["path"]) if S["path"] else None
    return jsonify(_state()) if S["a"] else jsonify(ok=True)


@app.post("/api/rescan")
def rescan():
    _run(S["path"])
    return jsonify(_state())


@app.post("/api/export")
def do_export():
    a = S["a"]
    approved = [c for c in _cands() if S["status"].get((c.start, c.end)) == "approved"]
    pending = sum(1 for c in _cands() if (c.start, c.end) not in S["status"])
    ext = ".pdf" if a["doc"].kind == "pdf" else ".txt"
    out = os.path.join(WORK, "redacted" + ext)
    r = export(a, approved, out)
    S["verification"] = r.get("verification") or {"txt": True}
    S["export_path"] = os.path.abspath(out)
    S["export_sha256"] = forensic.sha256(out)
    S["export_counts"] = {"approved": len(approved), "pending_unreviewed": pending}
    return jsonify({"approved": len(approved), "pending_unreviewed": pending,
                    "verification": r.get("verification"), "preview": r.get("text"),
                    "download": "/download"})


@app.get("/api/forensic")
def forensic_overview():
    """Checksum + structure of the exported file, plus the automatic check result. No document text."""
    p = S.get("export_path")
    if not p or not os.path.exists(p):
        return jsonify(error="Export a redacted copy first"), 404
    o = forensic.overview(p)
    v = S.get("verification") or {}
    o["auto_check"] = None if v.get("txt") else {"ok": bool(v.get("ok")), "strings_checked": v.get("checked"),
                                                  "recoverable": len({l[0] for l in v.get("leaks", [])})}
    return jsonify(o)


@app.post("/api/forensic/search")
def forensic_search():
    """Live search of the EXPORTED file (not the original) for any string the reviewer types."""
    p = S.get("export_path")
    if not p or not os.path.exists(p):
        return jsonify(error="Export a redacted copy first"), 404
    r = forensic.search(p, (request.json or {}).get("query", ""))
    return jsonify(r), (400 if "error" in r else 200)


@app.get("/api/ollama")
def ollama_status():
    m = ollama_model()
    return jsonify(running=bool(m), model=m)


@app.post("/api/summary")
def summary():
    """Always built from the reviewer's CURRENT approvals, so it matches the exported file."""
    approved = [c for c in _cands() if S["status"].get((c.start, c.end)) == "approved"]
    r = make_summary(S["a"]["doc"], approved)
    r["approved"] = len(approved)
    pend = [c for c in _cands() if (c.start, c.end) not in S["status"]]
    r["pending_unreviewed"] = len(pend)
    seen = sorted({c.text for c in pend if c.text.casefold() in r["summary"].casefold()})
    if seen:                       # a detected-but-unreviewed item is visible: never report a pass
        r["ok"] = False
        r["log"].append("Summary still shows unreviewed detections: " + ", ".join(repr(t) for t in seen))
    S["summary_info"] = {k: r[k] for k in ("method", "ok", "log", "qid_findings", "approved", "pending_unreviewed")}
    S["summary_info"]["risk"] = {"before": r["risk"]["before"]["level"], "after": r["risk"]["after"]["level"],
                                 "document": r["risk"]["document"]["level"]}
    return jsonify(r)


def _report():
    return build_report(S, _cands(), fb)


@app.get("/api/report")
def report_json():
    return jsonify(_report())


@app.get("/report")
def report_html():
    return render_report_html(_report())


@app.get("/download")
def download():
    ext = ".pdf" if S["a"]["doc"].kind == "pdf" else ".txt"
    return send_file(os.path.abspath(os.path.join(WORK, "redacted" + ext)), as_attachment=True,
                     download_name="redacted" + ext)


@app.get("/page/<int:n>.png")
def page(n):
    doc = S["a"]["doc"]
    scale = 1.4
    img = pdfium.PdfDocument(doc.path)[n].render(scale=scale).to_pil().convert("RGBA")
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for c in _cands():
        st = S["status"].get((c.start, c.end), "pending")
        if st == "rejected":
            continue
        r, g, b = COLORS.get(c.label, (100, 100, 100))
        for pg, x0, t, x1, bt in boxes_for_span(doc, c.start, c.end):
            if pg != n:
                continue
            box = [x0 * scale, t * scale, x1 * scale, bt * scale]
            if st == "approved":
                d.rectangle(box, fill=(0, 0, 0, 235))
            else:
                d.rectangle(box, fill=(r, g, b, int(60 + 100 * c.conf)), outline=(r, g, b, 255))
    buf = io.BytesIO()
    Image.alpha_composite(img, over).convert("RGB").save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
