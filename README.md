# Redactor — local, human-in-the-loop document redaction

Detects personal data in `.txt` and text-based `.pdf` files, lets a reviewer approve every redaction,
exports an **irreversibly** redacted copy, then proves what it did. Everything runs on your machine:
no cloud calls, no telemetry. An optional small local model (Ollama) assists but is never required.

## Features

| Area | What it does |
|---|---|
| **Detection** | Names, e-mails (incl. obfuscated `[at]`/`[dot]`), phones, addresses, IDs. Checksum validators (Aadhaar/Verhoeff, PAN) separate real IDs from look-alikes such as order numbers. |
| **Entity linking** | "Richa Sharma", "R. Sharma", "Ms. Sharma" and "Richa" share one placeholder (`[NAME_1]`). |
| **Review UI** | Confidence-coded highlights, keyboard shortcuts, approve/reject similar, add missed text by selection. Rejects and additions are remembered (per document for rejects). |
| **Irreversible export** | PDF pages are rasterised with the boxes burned into the pixels; the only text left is an invisible layer built from the *redacted* words. Original text objects, fonts, metadata and annotations never reach the output. |
| **Forensic inspector** | Type any string and see its hit count per source in the **exported** file (4 text extractors, raw + decoded streams, metadata). Shows file structure and the SHA-256 of the export. |
| **Privacy-safe summary** | Summarises only the redacted text, then checks for leaks (exact, fuzzy, name parts, detector re-run, placeholder consistency). |
| **Re-identification risk** | Rule-based Low/Medium/High for role + place + year/age combinations (e.g. "CFO of a Pune-based firm"), an attacker-style search query, and one-click generalisation with a list of changed words. |
| **Audit report** | Shareable HTML/JSON: counts, placeholders, check results, export checksum. Contains none of the removed text. |

## Quick start

```bash
pip install -r requirements.txt
python app.py                 # open http://127.0.0.1:5000
```

Click **Load demo document** (synthetic data), then **Approve high-confidence → Export → Inspect export**.

Optional small model: install [Ollama](https://ollama.com), `ollama pull qwen2.5:1.5b`. Without it the tool
falls back to rules automatically. Set `REDACTOR_SLM=0` to disable.

## Tests

```bash
python run_tests.py           # runs everything below, prints PASS/FAIL per suite
```

| Script | Covers |
|---|---|
| `evaluate.py` | Detection recall/precision on synthetic documents (currently 47/47 recall, 0 look-alikes flagged) |
| `evaluate_holdout.py` | Names *not* in the built-in lists; reports what rules alone miss (currently 9/10) |
| `test_report.py` | Export verification, report contains no removed text, learning does not leak across documents |
| `test_forensic.py` | Live search on the exported PDF, checksum matches the file, no stale export after opening a new document |
| `test_risk.py` | Risk levels, attacker query, generalisation, no invented counts |
| `test_summary.py`, `test_slm.py`, `test_app_slm.py` | Summary leak checks and the small-model path (mocked Ollama) |

## How the export is made irreversible

1. Each approved span is mapped to word boxes on the page.
2. The page is rendered to an image and the boxes are painted black **in the pixels**.
3. A new PDF is built from that image plus an invisible text layer containing only placeholders and non-redacted words.
4. The result is re-read with every extractor and searched for each removed string; export reports pass/fail.

## Limitations (by design)

- Only detected or reviewer-added items are redacted. Review remains the safety net.
- Scanned/image-only PDFs are not supported (no OCR).
- Risk level is a **keyword heuristic**, not a probability; there is no population data, so it never states how many people match.
- Generalisation changes the *summary*. The same combination in the document body must be redacted by the reviewer (the UI warns when it is present).
- A SHA-256 shows the file is unchanged since export; it does not by itself prove redaction. The searches and the file construction do.

## Layout

`app.py` Flask UI/API · `detect.py` rules + validators · `link.py` entity linking · `slm.py` optional model assist ·
`redact.py` export + verification · `forensic.py` inspector · `summarize.py` summary + risk · `report.py` audit report
