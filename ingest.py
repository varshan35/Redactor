"""Ingestion: TXT or text-based PDF -> one canonical text string plus a
character-offset -> word-bounding-box map, so every detection can be mapped
back onto the page it came from."""
from __future__ import annotations
import bisect, os
from dataclasses import dataclass, field
import pdfplumber


@dataclass
class Word:
    start: int
    end: int
    page: int
    x0: float
    top: float
    x1: float
    bottom: float
    text: str = ""


@dataclass
class Doc:
    kind: str                      # "txt" | "pdf"
    text: str
    words: list = field(default_factory=list)
    pages: list = field(default_factory=list)   # [(width_pt, height_pt)]
    path: str = ""
    _starts: list = field(default_factory=list, repr=False)


def load(path: str) -> Doc:
    if path.lower().endswith(".pdf"):
        return _load_pdf(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read().replace("\r\n", "\n")
    return Doc("txt", text, path=path)


def _group_lines(words):
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    for w in words:
        h = w["bottom"] - w["top"]
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= max(2.5, 0.5 * h):
            lines[-1].append(w)
        else:
            lines.append([w])
    return lines


def _columns(raw, width):
    """Return [words] for a normal page, or [left_words, right_words] for a two-column page.
    A column gutter is a vertical strip that (almost) no word crosses, with real prose on both sides.
    Label/value forms are NOT split: their sides hold 1-3 word fragments, not running text."""
    if os.environ.get("REDACTOR_COLUMNS") == "0" or len(raw) < 30:
        return [raw]
    n = len(raw)
    ok = []
    for x in range(int(width * 0.28), int(width * 0.72), 2):
        crossing = sum(1 for w in raw if w["x0"] < x < w["x1"])
        if crossing > max(1, 0.02 * n):
            continue
        left = sum(1 for w in raw if w["x1"] <= x); right = sum(1 for w in raw if w["x0"] >= x)
        if left >= 0.2 * n and right >= 0.2 * n:
            ok.append(x)
    if not ok:
        return [raw]
    runs, cur = [], [ok[0]]                                  # widest contiguous empty strip
    for x in ok[1:]:
        if x - cur[-1] <= 2: cur.append(x)
        else: runs.append(cur); cur = [x]
    runs.append(cur)
    best = max(runs, key=len)
    if (best[-1] - best[0]) < 10:                            # gutter narrower than ~12pt: not columns
        return [raw]
    g = (best[0] + best[-1]) / 2
    L = [w for w in raw if (w["x0"] + w["x1"]) / 2 < g]; R = [w for w in raw if (w["x0"] + w["x1"]) / 2 >= g]
    for side in (L, R):
        ls = _group_lines(side)
        if not ls or sum(len(l) for l in ls) / len(ls) < 4.5:   # prose lines have many words; form fields do not
            return [raw]
    return [L, R]


def _load_pdf(path: str) -> Doc:
    buf, words, pages = [], [], []
    pos = 0
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            pages.append((float(page.width), float(page.height)))
            raw = page.extract_words(x_tolerance=1.5, y_tolerance=3,
                                     keep_blank_chars=False, use_text_flow=False)
            lines = []
            for part in _columns(raw, float(page.width)):      # one part per column (or the whole page)
                lines += _group_lines(part)
            for li, line in enumerate(lines):
                line.sort(key=lambda w: w["x0"])
                for wi, w in enumerate(line):
                    if wi:
                        buf.append(" "); pos += 1
                    t = w["text"]
                    words.append(Word(pos, pos + len(t), pi, w["x0"], w["top"],
                                      w["x1"], w["bottom"], t))
                    buf.append(t); pos += len(t)
                buf.append("\n"); pos += 1
            buf.append("\n"); pos += 1          # blank line between pages
    doc = Doc("pdf", "".join(buf), words, pages, path)
    doc._starts = [w.start for w in words]
    return doc


def word_indices(doc: Doc, s: int, e: int) -> list[int]:
    """Indices of words overlapping character span [s, e)."""
    if not doc.words:
        return []
    i = max(0, bisect.bisect_right(doc._starts, s) - 1)
    out = []
    while i < len(doc.words) and doc.words[i].start < e:
        if doc.words[i].end > s:
            out.append(i)
        i += 1
    return out


def boxes_for_span(doc: Doc, s: int, e: int, pad: float = 1.5):
    """Merged (page, x0, top, x1, bottom) boxes covering the span.
    Whole-word boxes are used on purpose: a box that only partly covers a
    glyph could leave part of a character visible."""
    boxes = []
    for i in word_indices(doc, s, e):
        w = doc.words[i]
        b = [w.page, w.x0 - pad, w.top - pad, w.x1 + pad, w.bottom + pad]
        if boxes and boxes[-1][0] == w.page and abs(boxes[-1][2] - b[2]) < 3 \
                and b[1] - boxes[-1][3] < 8:
            boxes[-1][3] = max(boxes[-1][3], b[3])
        else:
            boxes.append(b)
    return [tuple(b) for b in boxes]
