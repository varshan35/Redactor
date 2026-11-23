# Architecture & decision log

Living document. Rule of thumb (just-in-time architecture): define the sprint you are in fully, the next one
slightly, the one after that only by purpose. Update the **Sprint log** and **Lessons** *before* designing the next sprint.

## Purpose
Local, human-in-the-loop redaction of `.txt` / text-based `.pdf`: detect personal data, let a reviewer decide,
export a file where the text is truly gone, and show evidence of what was done.

## Code map
| Module | Job | Uses |
|---|---|---|
| `ingest.py` | Load txt/pdf; words with page positions; map a text span to boxes | – |
| `detect.py` | Rules, checksum validators (Verhoeff, Luhn), name heuristics -> candidates with confidence + reason | – |
| `link.py` | Link name variants into one entity; flag ambiguous ones; "similar" matching | detect |
| `slm.py` | Optional local-model check/discovery of names; falls back silently | detect, summarize |
| `feedback.py` | Remembered accepts (global) and rejects (per document hash) | – |
| `pipeline.py` | `analyze()` and `export()` orchestration | ingest, detect, link, slm, feedback, redact |
| `redact.py` | Irreversible export (rasterise + invisible placeholder layer); `collect_sources()` + `verify_pdf()` | ingest |
| `forensic.py` | Live search of the *exported* file, structure facts, SHA-256 | redact |
| `summarize.py` | Summary from redacted text, leak checks, risk heuristic, generalisation | detect, redact, link |
| `report.py` | Audit report (counts and checks, no removed text) | redact |
| `app.py` + `templates/index.html` | Flask API and review UI | all of the above |

Rule: modules talk through plain data (candidates, dicts). A new feature should add a module or a function, not change a contract.

## Sprint log
*(Sprints 1-2 were recorded after the fact; from Sprint 3 on, write the entry before building.)*

### Sprint 1 - Forensic inspector
- **Purpose:** let anyone check the exported file themselves instead of trusting our claim.
- **Decided:** move "read text out of a PDF every way we can" into one shared function (`collect_sources`) so the automatic check and the live search cannot disagree. Cache sources per export. Search is case-, spacing- and punctuation-insensitive.
- **Dropped on purpose:** "cryptographic proof", "font glyph table erased", "tamper-evident". We do not check or prove those.
- **Learned:** the demo's Order ID has the same digits as the phone number, so a digit search legitimately hits it. Opening a new document must clear the old export, or the inspector shows stale results.

### Sprint 2 - Re-identification risk (trimmed)
- **Purpose:** show that removing names is not enough, using the "CFO of a Pune-based firm" case.
- **Decided:** rule-based Low/Medium/High, labelled heuristic; attacker query built from words actually found; generalisation records every change. No k-anonymity or candidate counts (no population data, would be invented).
- **Learned:** generalising to "Western India-based" re-triggered the "-based" location rule, so broad regions must not count as locations. The summary is generalised but the document body is not, so the UI now warns when the same combination is still in a sentence of the document.

## Decision log
| Decision | Why | Revisit when |
|---|---|---|
| Everything local; model optional | Documents are sensitive; no dependency on a cloud service | Never for data; model choice can change |
| Reviewer approves every redaction | No detector is perfect | If a trusted auto-mode is ever needed |
| Rasterise pages on export | Only way to be sure original text objects are gone without relying on one library | If OCR/searchable output matters more |
| Rejects scoped per document hash | A reject in one file must not hide PII in another | If cross-document policies are wanted |
| Risk = keyword heuristic, no counts | Honest about missing population data | If real reference data becomes available |
| Checksum labelled "of the exported file" | It shows "unchanged since export", not "redacted" | – |

## Lessons (carry into the next sprint)
1. Check the demo data against every new feature; collisions show up in front of judges.
2. Anything shown to the user must be cleared when the document changes.
3. Claims in the UI should match exactly what the code checks. Cut the claim, not the honesty.
4. Generalising output without a way to apply it to the document leaves a visible gap; say so in the UI.

## Next sprints
**Sprint 3 - Apply quasi-identifier fixes to the document (defined in detail).**
Purpose: close the gap above. When risk is High, propose the matched words (role, place, year/age) as *candidates* the reviewer can approve, so the exported file loses them too.
- Input: `risk_in_document()` terms plus their positions in `doc.text`.
- Output: ordinary candidates (new label or reuse `ID`/`ADDRESS`?) so `export()` needs no change.
- Open questions: label name and colour; one candidate per occurrence or per term; how to avoid redacting every "2019" in the file (suggest per-sentence, not global).
- Done when: demo document goes High -> Low in both summary and exported file, and `test_risk.py` covers it.

**Sprint 4 - Working-file hygiene (purpose only).** The uploaded original sits in `work/`; give the user a clear way to remove it.

**Sprint 5 - Scanned PDFs (purpose only).** OCR so image-only documents are supported.
