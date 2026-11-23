"""Built-in demo document (synthetic data only) so a demo never depends on a file dialog."""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from detect import verhoeff_check_digit

_b = "34567890123"
AADHAAR = f"{_b[:4]} {_b[4:8]} {_b[8:]}{verhoeff_check_digit(_b)}"

LINES = [
    ("Meridian Logistics Pvt Ltd - Annual Performance Review", "b"),
    ("Review date: 14/03/2024        Document ref: DOC-2024-0412", ""),
    ("", ""),
    ("Employee Name: Richa Sharma", ""),
    ("Employee ID: EMP-9821", ""),
    ("Email: richa.sharma@meridian-logistics.com", ""),
    ("Alternate: r.sharma [at] gmail [dot] com", ""),
    ("Mobile: +91-98765-43210     Landline: (022) 2345 6789", ""),
    ("Address: Flat 402, Lotus Heights, 14 MG Road, Pune 411001", ""),
    (f"Aadhaar: {AADHAAR}", ""),
    ("PAN: ABCPE1234F", ""),
    ("", ""),
    ("Summary", "b"),
    ("Ms. Sharma, the CFO of the Pune office, joined in 2019 and led the warehouse migration (PROD-404,", ""),
    ("SKU-77821, serial no. SN-0099231) during 2023. R. Sharma met every quarterly target and the", ""),
    ("finance team reports strong morale. Order ID: 9876543210 shipped on 5 April 2024; reference", ""),
    ("5521-8890 is unrelated. Her manager, Rahul Verma, recommends a promotion and a larger budget.", ""),
    ("", ""),
    ("Dear Richa, congratulations and thank you for a strong year.", ""),
    ("Regards,", ""),
    ("Priya Nair", ""),
]


def make_sample_pdf(path: str):
    c = canvas.Canvas(path, pagesize=A4)
    c.setTitle("Annual performance review (synthetic demo)")
    y = 800
    for text, style in LINES:
        c.setFont("Helvetica-Bold" if style == "b" else "Helvetica", 10.5)
        c.drawString(52, y, text); y -= 18
    c.showPage(); c.save()
    return path
