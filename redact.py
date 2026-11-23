"""Irreversible export + verification.

TXT: replace spans with placeholders.
PDF: PyMuPDF isn't available here, so the page is RASTERISED (pypdfium2), the
approved boxes are burned into the pixels, and a fresh PDF is built whose only
text is an invisible layer made from the *redacted* words. The original text
objects, fonts, metadata and annotations never reach the output file.
"""
from __future__ import annotations
import io, re, subprocess
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pdfminer.high_level import extract_text as _pm_text
import pikepdf
from ingest import Doc, boxes_for_span, word_indices


def placeholders(cands) -> dict[int, str]:
    """index in cands -> '[LABEL_n]'; one number per linked entity/group."""
    counters, seen, out = {}, OrderedDict(), {}
    for i, c in enumerate(cands):
        key = (c.label, c.group)
        if key not in seen:
            counters[c.label] = counters.get(c.label, 0) + 1
            seen[key] = f"[{c.label}_{counters[c.label]}]"
        out[i] = seen[key]
    return out


def _merge(spans):
    spans = sorted(spans)
    out = []
    for s, e, ph in spans:
        if out and s < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e), out[-1][2])
        else:
            out.append((s, e, ph))
    return out


def redact_txt(doc: Doc, approved, out_path: str) -> str:
    ph = placeholders(approved)
    spans = _merge([(c.start, c.end, ph[i]) for i, c in enumerate(approved)])
    text = doc.text
    for s, e, p in reversed(spans):
        text = text[:s] + p + text[e:]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def redact_pdf(doc: Doc, approved, out_path: str, dpi: int = 150):
    ph = placeholders(approved)
    spans = _merge([(c.start, c.end, ph[i]) for i, c in enumerate(approved)])
    boxes = {p: [] for p in range(len(doc.pages))}
    red_words, first_word_ph = set(), {}
    for s, e, p in spans:
        idx = word_indices(doc, s, e)
        red_words.update(idx)
        if idx:
            first_word_ph[idx[0]] = p
        for b in boxes_for_span(doc, s, e):
            boxes[b[0]].append(b[1:])

    src = pdfium.PdfDocument(doc.path)
    scale = dpi / 72.0
    out = canvas.Canvas(out_path, pageCompression=1)
    out.setTitle("Redacted document"); out.setAuthor(""); out.setSubject(""); out.setCreator("")
    try:
        font = ImageFont.load_default(size=max(8, int(9 * scale)))
    except TypeError:
        font = ImageFont.load_default()
    for pi, (w, h) in enumerate(doc.pages):
        img = src[pi].render(scale=scale).to_pil().convert("RGB")
        d = ImageDraw.Draw(img)
        for x0, t, x1, b in boxes[pi]:
            d.rectangle([x0 * scale, t * scale, x1 * scale, b * scale], fill=(0, 0, 0))
        out.setPageSize((w, h))
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=82, optimize=True); buf.seek(0)   # boxes are burned in first
        out.drawImage(ImageReader(buf), 0, 0, w, h)
        # invisible text layer built only from the redacted words
        t = out.beginText(); t.setTextRenderMode(3)
        for i, wd in enumerate(doc.words):
            if wd.page != pi:
                continue
            if i in red_words:
                txt = first_word_ph.get(i)
                if not txt:
                    continue
            else:
                txt = wd.text
            txt = txt.encode("latin-1", "replace").decode("latin-1")
            size = max(4.0, (wd.bottom - wd.top) * 0.8)
            width = out.stringWidth(txt, "Helvetica", size) or 1
            t.setFont("Helvetica", size)
            t.setHorizScale(max(20, min(300, 100 * (wd.x1 - wd.x0) / width)))
            t.setTextOrigin(wd.x0, h - wd.bottom + size * 0.2)
            t.textOut(txt)
        out.drawText(t)
        out.showPage()
    out.save()
    return out_path


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).casefold().strip()


def collect_sources(path: str) -> tuple[dict, dict]:
    """Every way we know to read text back out of an exported PDF -> ({source name: text}, structure facts).
    Shared by verify_pdf (automatic check) and the forensic inspector (live search)."""
    sources = {}
    try:                                   # poppler's pdftotext: extra check where installed (not on Windows)
        sources["pdftotext"] = subprocess.run(["pdftotext", "-layout", path, "-"],
                                              capture_output=True, text=True).stdout
    except (FileNotFoundError, OSError):
        pass
    sources["pdfminer"] = _pm_text(path)
    try:                                   # pypdfium2: a different extraction engine, works everywhere
        _pdf = pdfium.PdfDocument(path)
        sources["pdfium"] = "\n".join(_pdf[i].get_textpage().get_text_range() for i in range(len(_pdf)))
    except Exception:
        pass
    try:                                   # pdfplumber
        import pdfplumber
        with pdfplumber.open(path) as _pl:
            sources["pdfplumber"] = "\n".join((p.extract_text() or "") for p in _pl.pages)
    except Exception:
        pass
    pk = pikepdf.open(path)
    raw = bytearray(open(path, "rb").read())
    n_images = n_streams = 0
    for obj in pk.objects:
        if isinstance(obj, pikepdf.Stream):
            try:
                if obj.get("/Subtype") == "/Image":
                    n_images += 1
                    continue                # pixels cannot hold searchable text; decoding them costs ~7 MB/page
                raw += obj.read_bytes(); n_streams += 1
            except Exception:
                pass
    meta = " ".join(str(v) for v in (pk.docinfo or {}).values())
    try:
        meta += " " + (pk.open_metadata().__str__() if pk.Root.get("/Metadata") else "")
    except Exception:
        pass
    sources["raw+decoded streams"] = raw.decode("latin-1", "ignore")
    sources["metadata"] = meta
    fonts = set()
    for pg in pk.pages:
        try:
            for _, f in (pg.Resources.get("/Font") or {}).items():
                fonts.add(str(f.get("/BaseFont", "?")).lstrip("/"))
        except Exception:
            pass
    facts = {"pages": len(pk.pages), "images": n_images, "decoded_streams": n_streams,
             "fonts": sorted(fonts), "annotations_present": any("/Annots" in p for p in pk.pages),
             "has_xmp": "/Metadata" in pk.Root,
             "docinfo_fields": {str(k).lstrip("/"): str(v) for k, v in (pk.docinfo or {}).items()}}
    return sources, facts


def verify_pdf(path: str, removed: list[str]) -> dict:
    """Try hard to recover every removed string from the exported PDF."""
    removed = sorted({r for r in removed if len(r.strip()) >= 3}, key=len, reverse=True)
    sources, facts = collect_sources(path)
    has_annots = facts["annotations_present"]
    leaks = []
    prepared = {name: (_norm(blob), re.sub(r"\W", "", blob).casefold())    # normalise each source ONCE
                for name, blob in sources.items()}
    for r in removed:
        rn, rc = _norm(r), re.sub(r"\W", "", r).casefold()
        for name, (nb, cb) in prepared.items():
            if rn in nb or (rc and rc in cb):
                leaks.append((r, name))
    context = {}
    compact = lambda s: re.sub(r"\W", "", s).casefold()
    lines = (sources.get("pdfplumber") or sources.get("pdfminer") or "").splitlines()
    for r in {l[0] for l in leaks}:
        for ln in lines:
            if compact(r) and compact(r) in compact(ln):
                context[r] = ln.strip()[:120]; break
    return {"checked": len(removed), "leaks": leaks, "annotations_present": has_annots,
            "ok": not leaks and not has_annots, "context": context, "engines": list(sources)}
