# Acknowledgements

## AI assistance

This project was built with AI assistance. The team set the requirements, made the design decisions,
reviewed and tested the output, and is responsible for the final result.

| Tool | Provider | Used for |
|---|---|---|
| Claude (claude.ai) | Anthropic | Feature planning, code and test generation, documentation, debugging |
| Claude Code | Anthropic | Implementation work in the repository |
| Ollama + a small local language model (optional, e.g. `qwen2.5:1.5b`) | Ollama; model by Alibaba Cloud (Qwen) | Optional runtime assistance for name detection and summaries. Runs locally; no data leaves the machine |

<Edit this table so it matches exactly what you used. Remove any row that does not apply.>

## Data

- **No external datasets are used.**
- All demo and test documents are **synthetic**, written for this project. They contain no real people's data.
- The first-name list in `names_data.py` is a small hand-compiled list of common names, used only as weak evidence.
  A human reviewer or the optional model makes the final decision.

## Open-source libraries

| Library | Used for | License* |
|---|---|---|
| [Flask](https://flask.palletsprojects.com/) | Local web application | BSD-3-Clause |
| [Pillow](https://python-pillow.org/) | Image handling | HPND |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) / PDFium | PDF page rendering, text extraction | Apache-2.0 / BSD-3-Clause |
| [ReportLab](https://www.reportlab.com/opensource/) | Building the redacted PDF | BSD-3-Clause |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | Text extraction (verification) | MIT |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Word positions, text extraction | MIT |
| [pikepdf](https://github.com/pikepdf/pikepdf) / qpdf | PDF structure, streams and metadata checks | MPL-2.0 |

Optional external tools (not bundled): Poppler `pdftotext` (extra verification where installed),
[Ollama](https://ollama.com) (local model runtime).

\*Licenses as understood by the team; check each project's current license before redistribution
(for example with `pip install pip-licenses && pip-licenses`).

## Algorithms and references

- **Verhoeff checksum** — validating Aadhaar-style numbers.
- **Luhn algorithm** — validating card-style numbers.
- **Quasi-identifier re-identification** — the idea that combinations such as role + place + year can identify a person
  even after names are removed.

## Problem statement and inspiration

<Name of the hackathon / course / organiser and the problem statement title, if applicable.>

## Licence of this project

<Choose one and add a LICENSE file, e.g. MIT. Until a licence file exists, the code is "all rights reserved" by default.>
