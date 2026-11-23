"""Redaction report: a shareable audit of what the tool did.

It NEVER contains removed text. Items appear as placeholders ([NAME_1]) with counts, confidence and source;
check results appear as pass/fail with counts. Free-text log lines are reduced to safe categories because the
raw lines can quote leaked fragments."""
from __future__ import annotations
import datetime, html, re
from collections import Counter, defaultdict
from flask import Response
from redact import placeholders


def _safe_log(lines):
    out = Counter()
    for l in lines or []:
        m = re.match(r"scrubbed (\d+) leaked", l)
        if m: out[f"{m.group(1)} leaked fragment(s) in the draft summary were replaced by placeholders"] += 1
        elif l.startswith("generalised quasi-identifier"): out["a role/location/age/year combination was generalised"] += 1
        elif l.startswith("removed unknown placeholder"): out["an invented placeholder was removed"] += 1
        elif "replaced by rule-based" in l: out["the model summary failed the check and a rule-based summary was used"] += 1
        elif l.startswith("Summary still shows unreviewed"): out["the summary still showed items you had not reviewed"] += 1
        elif "Ollama" in l and "rule-based" in l: out["the small model was unavailable; a rule-based summary was used"] += 1
    return list(out)


def build_report(S, cands, fb):
    a = S["a"]; doc = a["doc"]
    st = lambda c: S["status"].get((c.start, c.end), "pending")
    approved = [c for c in cands if st(c) == "approved"]
    ph = placeholders(approved)
    by_label = defaultdict(lambda: Counter())
    for c in cands:
        by_label[c.label]["detected"] += 1; by_label[c.label][st(c)] += 1
    groups = defaultdict(list)
    for i, c in enumerate(approved):
        groups[ph[i]].append(c)
    items = [{"placeholder": k, "label": v[0].label, "occurrences": len(v),
              "confidence_range": f"{min(c.conf for c in v):.2f}–{max(c.conf for c in v):.2f}",
              "sources": sorted({c.source for c in v})} for k, v in groups.items()]
    supp = Counter(re.sub(r"^overlaps .*", "overlaps a protected date/code", s["reason"]) for s in a["suppressed"])
    slm = a.get("slm") or {}
    ver = S.get("verification")
    summ = S.get("summary_info")
    return {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "document": {"name": S.get("name") or "document", "type": doc.kind, "pages": max(1, len(doc.pages)),
                     "characters": len(doc.text)},
        "engine": {"rules_and_validators": True, "small_model": slm.get("model") if slm.get("used") else None,
                   "model_note": slm.get("note") or "", "model_confirmed": slm.get("verified", 0),
                   "model_doubted": slm.get("downgraded", 0), "model_found_extra": slm.get("discovered", 0)},
        "totals": {"detected": len(cands), "approved": len(approved),
                   "rejected": sum(st(c) == "rejected" for c in cands),
                   "unreviewed": sum(st(c) == "pending" for c in cands),
                   "ambiguous_flagged": sum(c.ambiguous for c in cands),
                   "added_by_reviewer": sum(c.source == "user" for c in cands)},
        "by_type": {k: dict(v) for k, v in sorted(by_label.items())},
        "removed_items": items,
        "linked_people": {f"NAME_{k}": len(v) for k, v in a["entities"].items()},
        "ignored_lookalikes": dict(supp),
        "export_check": None if not ver else (
            {"format": "txt", "note": "placeholders substituted in the text file"} if ver.get("txt") else
            {"passed": bool(ver.get("ok")), "strings_checked": ver.get("checked"),
             "engines": ver.get("engines", []), "annotations_present": ver.get("annotations_present"),
             "recoverable_strings": len({l[0] for l in ver.get("leaks", [])}),
             "sha256": S.get("export_sha256")}),
        "summary_check": None if not summ else {
            "passed": bool(summ["ok"]), "method": summ["method"], "redactions_used": summ["approved"],
            "unreviewed_when_generated": summ["pending_unreviewed"],
            "quasi_identifier_findings": len(summ["qid_findings"]), "actions": _safe_log(summ["log"]),
            "risk_heuristic": summ.get("risk")},
        "limitations": [
            "Only items that were detected or added by the reviewer are redacted.",
            "Scanned/image-only PDFs are not supported (no OCR).",
            "Quasi-identifier checks use keyword lists (roles, cities, ages, years) and are not exhaustive.",
        ],
    }


def render_report_html(r) -> Response:
    e = html.escape
    def pf(ok): return '<b style="color:#15803d">PASSED</b>' if ok else '<b style="color:#b91c1c">FAILED</b>'
    rows = "".join(f"<tr><td>{e(i['placeholder'])}</td><td>{e(i['label'])}</td><td>{i['occurrences']}</td>"
                   f"<td>{e(i['confidence_range'])}</td><td>{e(', '.join(i['sources']))}</td></tr>" for i in r["removed_items"])
    types = "".join(f"<tr><td>{e(k)}</td><td>{v.get('detected',0)}</td><td>{v.get('approved',0)}</td>"
                    f"<td>{v.get('rejected',0)}</td><td>{v.get('pending',0)}</td></tr>" for k, v in r["by_type"].items())
    ign = "".join(f"<li>{n} × {e(k)}</li>" for k, n in r["ignored_lookalikes"].items()) or "<li>none</li>"
    t, en, d = r["totals"], r["engine"], r["document"]
    eng = "rules + checksum validators" + (f" + small model <b>{e(en['small_model'])}</b> (confirmed {en['model_confirmed']}, "
                                           f"doubted {en['model_doubted']}, found {en['model_found_extra']} extra)" if en["small_model"]
                                           else f" (small model not used{': ' + e(en['model_note']) if en['model_note'] else ''})")
    ec, sc = r["export_check"], r["summary_check"]
    ecs = "<p>Not exported yet.</p>" if not ec else (
        f"<p>{e(ec['note'])}</p>" if "note" in ec else
        f"<p>{pf(ec['passed'])} — {ec['strings_checked']} removed values searched for in the exported file using "
        f"{e(', '.join(ec['engines']) or 'text extraction')}, raw content streams and metadata; "
        f"{ec['recoverable_strings']} recoverable; annotations present: {'yes' if ec['annotations_present'] else 'no'}."
        + (f"<br>Checksum of the exported file (SHA-256): <code>{e(ec['sha256'])}</code></p>" if ec.get("sha256") else "</p>"))
    scs = "<p>Summary not generated yet.</p>" if not sc else (
        f"<p>{pf(sc['passed'])} — method <b>{e(sc['method'])}</b>, built from {sc['redactions_used']} approved redactions "
        f"({sc['unreviewed_when_generated']} unreviewed at the time); {sc['quasi_identifier_findings']} quasi-identifier "
        f"finding(s).<br>Re-identification risk (rule-based heuristic, not a probability): "
        f"summary before generalising <b>{e((sc.get('risk_heuristic') or {}).get('before','n/a'))}</b>, after <b>{e((sc.get('risk_heuristic') or {}).get('after','n/a'))}</b>; "
        f"same-sentence combination still in the document body: <b>{e((sc.get('risk_heuristic') or {}).get('document','n/a'))}</b>.</p><ul>" + "".join(f"<li>{e(a)}</li>" for a in sc["actions"]) + "</ul>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Redaction report</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;max-width:820px;margin:28px auto;padding:0 16px;color:#1b1f24}}
h1{{font-size:20px}}h2{{font-size:15px;margin-top:22px;border-bottom:1px solid #ddd;padding-bottom:3px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:4px 8px;text-align:left}}
.k{{color:#555}}@media print{{body{{margin:0}}}}</style></head><body>
<h1>Redaction report</h1>
<p class="k">{e(d['name'])} · {e(d['type'].upper())}, {d['pages']} page(s) · generated {e(r['generated'])}<br>
This report lists placeholders and counts only. It contains none of the removed text.</p>
<h2>Detection</h2><p>{eng}</p>
<p>{t['detected']} candidates: <b>{t['approved']}</b> approved, {t['rejected']} rejected, <b>{t['unreviewed']}</b> unreviewed;
{t['added_by_reviewer']} added by the reviewer; {t['ambiguous_flagged']} flagged as ambiguous for human decision.</p>
<table><tr><th>Type</th><th>Detected</th><th>Approved</th><th>Rejected</th><th>Unreviewed</th></tr>{types}</table>
<h2>Removed items</h2>
<table><tr><th>Placeholder</th><th>Type</th><th>Occurrences</th><th>Confidence</th><th>Found by</th></tr>{rows}</table>
<h2>Looked like personal data but kept (by reason)</h2><ul>{ign}</ul>
<h2>Exported file check</h2>{ecs}
<h2>Summary check</h2>{scs}
<h2>Limitations</h2><ul>{''.join(f'<li>{e(x)}</li>' for x in r['limitations'])}</ul>
</body></html>"""
    return Response(page, mimetype="text/html")
