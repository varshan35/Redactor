"""End-to-end demo + mini evaluation on synthetic documents (no real data)."""
import os, re, sys
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from detect import verhoeff_check_digit
from pipeline import analyze, export
from feedback import Feedback
from link import similar

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
os.makedirs(OUT, exist_ok=True)

base = "23456789012"
AADHAAR = f"{base[:4]} {base[4:8]} {base[8:]}{verhoeff_check_digit(base)}"

LINES = [
    "ACME Analytics Pvt Ltd - Quarterly HR Review",
    "Date: 12/03/2024     Invoice No: INV-2024-0412",
    "",
    "Employee Name: Richa Sharma",
    "Employee ID: EMP-9821",
    "Email: richa.sharma@acme-analytics.com",
    "Alt email: r.sharma [at] gmail [dot] com",
    "Phone: +91-98765-43210 | Landline: (022) 2345 6789",
    "Address: Flat 402, Lotus Heights, 14 MG Road, Pune 411001",
    f"Aadhaar: {AADHAAR}",
    "PAN: ABCPE1234F",
    "Bank account number: 123456789012",
    "",
    "Summary",
    "Ms. Sharma joined the Pune office on 2021-04-05. R. Sharma was promoted in March 2023.",
    "Richa led the migration of product PROD-404 (SKU-77821, serial no. SN-0099231).",
    "Order ID: 9876543210 shipped on 5 April 2024. Reference 5521-8890 is unrelated.",
    "",
    "Dear Richa, thank you.",
    "Regards,",
    "Priya Nair",
]
TEXT = "\n".join(LINES)

# expected personal strings (ground truth) and look-alikes that must NOT be flagged
PII = ["Richa Sharma", "EMP-9821", "richa.sharma@acme-analytics.com", "r.sharma [at] gmail [dot] com",
       "+91-98765-43210", "(022) 2345 6789", "Flat 402, Lotus Heights, 14 MG Road, Pune 411001",
       AADHAAR, "ABCPE1234F", "123456789012", "Ms. Sharma", "R. Sharma", "Richa", "Priya Nair"]
NOT_PII = ["12/03/2024", "INV-2024-0412", "2021-04-05", "PROD-404", "SKU-77821", "SN-0099231",
           "9876543210", "5 April 2024", "5521-8890", "March 2023", "ACME Analytics Pvt Ltd"]


def make_pdf(path):
    c = canvas.Canvas(path, pagesize=A4)
    c.setTitle("HR review - Richa Sharma"); c.setAuthor("Priya Nair")
    y = 800
    for ln in LINES:
        c.setFont("Helvetica-Bold" if ln.startswith(("ACME", "Summary")) else "Helvetica", 11)
        c.drawString(56, y, ln); y -= 18
    c.showPage(); c.save()


def spans_of(text, strings):
    out = []
    for s in strings:
        out += [(m.start(), m.end(), s) for m in re.finditer(re.escape(s), text)]
    return out


def evaluate(a):
    text, cands = a["doc"].text, a["cands"]
    gt = spans_of(text, PII)
    bad = spans_of(text, NOT_PII)
    hit = lambda g: any(c.start < g[1] and c.end > g[0] for c in cands)
    missed = [g[2] for g in gt if not hit(g)]
    fp = [(g[2]) for g in bad if hit(g)]
    tp_c = [c for c in cands if any(c.start < g[1] and c.end > g[0] for g in gt)]
    print(f"  recall    {len(gt) - len(missed)}/{len(gt)}   missed: {missed or '-'}")
    print(f"  precision {len(tp_c)}/{len(cands)}   look-alikes wrongly flagged: {fp or '-'}")


# ---------------------------------------------------------------- TXT run
txt = os.path.join(OUT, "sample.txt"); open(txt, "w").write(TEXT)
a = analyze(txt)
print("== TXT ==")
for c in a["cands"]:
    print(f"  {c.label:7} {c.conf:.2f} {c.source:9} g={c.group:28} {c.text!r}")
evaluate(a)
print("  entities:", a["entities"])
r = export(a, a["cands"], os.path.join(OUT, "sample.redacted.txt"))
leaks = [p for p in PII if p in r["text"]]
print("  leaked after redaction:", leaks or "none")

# ------------------------------------------------------------ PDF run
pdf = os.path.join(OUT, "sample.pdf"); make_pdf(pdf)
a = analyze(pdf)
print("== PDF ==")
evaluate(a)
r = export(a, a["cands"], os.path.join(OUT, "sample.redacted.pdf"))
print("  verification:", r["verification"])

# ------------------------------------------------- ambiguity + feedback
amb = os.path.join(OUT, "ambig.txt")
open(amb, "w").write("Employee Name: Richa Sharma\nManager: Rahul Sharma\nMs. Sharma and R. Sharma attended.\n"
                     "Part code ZX-4471 and Mr. Verma were mentioned.\n")
a = analyze(amb)
print("== AMBIGUITY ==")
for c in a["cands"]:
    print(f"  {c.text!r:18} conf={c.conf:.2f} group={c.group:18} ambiguous={c.ambiguous} {c.reason}")

fbp = os.path.join(OUT, "feedback.json")
if os.path.exists(fbp): os.remove(fbp)
fb = Feedback(fbp)
doc_text = "Customer ref ZX-4471 belongs to Vikram Rao. Contact Atlas Corp for ZX-4471.\n"
open(os.path.join(OUT, "fb.txt"), "w").write(doc_text)
before = analyze(os.path.join(OUT, "fb.txt"), fb)
print("== ACTIVE LEARNING ==\n  before:", [(c.text, c.label) for c in before["cands"]])
fb.accept("ZX-4471", "ID"); fb.reject("Vikram Rao")
after = analyze(os.path.join(OUT, "fb.txt"), fb)
print("  after :", [(c.text, c.label) for c in after["cands"]])
print("  'redact all similar' for first cand:", [x.text for x in similar(a["cands"], a["cands"][0])])
