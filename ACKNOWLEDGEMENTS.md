# Acknowledgements

## AI assistance

This project was built with AI assistance. The participant set the requirements, made the design decisions,
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

Built for TinyVerse, organised by ThiliAI, November 2026.

**Problem statement:** Privacy-Aware Document Redaction and Summary Tool.

## License

Released under the MIT License. See [LICENSE](LICENSE) for details.
MIT License

Copyright (c) 2026 Varsha N Swamy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

