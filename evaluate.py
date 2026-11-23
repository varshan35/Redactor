"""Labeled test set + scorer. Run:  python evaluate.py
Each doc lists the strings that ARE personal data (with a label) and, separately, look-alikes
that must NOT be flagged. Some docs are deliberately hard; the gaps are reported, not hidden."""
import os, re, sys, tempfile
from detect import verhoeff_check_digit
from pipeline import analyze

b = "23456789012"; AAD = f"{b[:4]} {b[4:8]} {b[8:]}{verhoeff_check_digit(b)}"
b2 = "56781234567"; AAD2 = f"{b2[:4]} {b2[4:8]} {b2[8:]}{verhoeff_check_digit(b2)}"

DOCS = [
 dict(name="01 HR form", text=
  "EMPLOYEE RECORD\nName: Anita Verma\nEmployee ID: EMP-4412\nMobile: 98765 01234\n"
  "Email: anita.verma@infosolve.in\nAddress: Plot 12, Sector 18, Noida 201301\nPAN: AKLPM5678Q\n"
  "Joining date: 15/08/2023\nCost centre ref: INV-8891\nAsset tag SKU-1020 issued to Anita.\n",
  pii=[("Anita Verma","NAME"),("Anita","NAME"),("EMP-4412","ID"),("98765 01234","PHONE"),
       ("anita.verma@infosolve.in","EMAIL"),("Plot 12, Sector 18, Noida 201301","ADDRESS"),("AKLPM5678Q","ID")],
  safe=["15/08/2023","INV-8891","SKU-1020"]),
 dict(name="02 Email thread", text=
  "From: Rohit Mehta <rohit.mehta@gmail.com>\nTo: Neha Kapoor\nSubject: Q3 numbers\n\n"
  "Hi Neha,\n\nPlease send the Q3 numbers by Friday. You can also reach me at rohit at mailbox dot net.\n"
  "My colleague is reachable at neha.kapoor [at] example [dot] org.\n\nThanks,\nRohit\n",
  pii=[("Rohit Mehta","NAME"),("rohit.mehta@gmail.com","EMAIL"),("Neha Kapoor","NAME"),("Neha","NAME"),
       ("rohit at mailbox dot net","EMAIL"),("neha.kapoor [at] example [dot] org","EMAIL"),("Rohit","NAME")],
  safe=[]),
 dict(name="03 Medical note", text=
  f"Patient: Suresh Iyer, age 54\nAadhaar: {AAD}\nPhone: +91 98450 12345 / (080) 2345 6789\n"
  "Address: No. 5, 3rd Cross, Jayanagar, Bengaluru 560041\nConsulting: Dr. Meena Rao\n"
  "Rx: Paracetamol 500 mg, Batch No: B-77231, Lot 4456\nVisit date: 2024-03-09\n",
  pii=[("Suresh Iyer","NAME"),(AAD,"ID"),("+91 98450 12345","PHONE"),("(080) 2345 6789","PHONE"),
       ("No. 5, 3rd Cross, Jayanagar, Bengaluru 560041","ADDRESS"),("Dr. Meena Rao","NAME")],
  safe=["500 mg","B-77231","Lot 4456","2024-03-09"]),
 dict(name="04 Same surname", text=
  "Attendees: Anil Kumar and Sunil Kumar\nName: Anil Kumar\nManager: Sunil Kumar\n"
  "Mr. Kumar approved the budget. A. Kumar will present.\n",
  pii=[("Anil Kumar","NAME"),("Sunil Kumar","NAME"),("Mr. Kumar","NAME"),("A. Kumar","NAME")],
  safe=[]),
 dict(name="05 Look-alike numbers", text=
  "Order ID: 9988776655\nTracking no 1234567890\nRef: 5521-8890\nSerial: 9123456780\n"
  "Amount: Rs. 12,345.00 paid in 2021\nPart number 4455667788\nCall me on 98765 43210 after 6 pm.\n",
  pii=[("98765 43210","PHONE")],
  safe=["9988776655","1234567890","5521-8890","9123456780","12,345.00","4455667788"]),
 dict(name="06 Financial", text=
  f"Account number: 004512345678\nCard: 4111 1111 1111 1111\nPAN: BQRPS4321K\nAadhaar: {AAD2}\n"
  "UPI: richa@okhdfc\nTransaction ref: TXN-9981223\n",
  pii=[("004512345678","ID"),("4111 1111 1111 1111","ID"),("BQRPS4321K","ID"),(AAD2,"ID"),("richa@okhdfc","ID")],
  safe=["TXN-9981223"]),
 dict(name="07 Names, no cue", text=
  "The review was chaired by Kavita Joshi and attended by Vikram Singh.\n"
  "Budget approval came from Harshavardhan Pillai after the meeting.\n",
  pii=[("Kavita Joshi","NAME"),("Vikram Singh","NAME"),("Harshavardhan Pillai","NAME")],
  safe=[]),
 dict(name="08 Phone formats", text=
  "Mobile: +91-98765-43210\nAlt: 098765 43210\nOffice: 022-2345-6789\nLandline: (022) 2345 6789\n"
  "US: +1 (415) 555-0132\n",
  pii=[("+91-98765-43210","PHONE"),("098765 43210","PHONE"),("022-2345-6789","PHONE"),
       ("(022) 2345 6789","PHONE"),("+1 (415) 555-0132","PHONE")],
  safe=[]),
 dict(name="09 Contract", text=
  "SERVICE AGREEMENT dated 1 March 2024\nBetween Mrs. Lakshmi Narayan, residing at 14, MG Road, "
  "Mysuru 570001 (the Client) and Tech Works Pvt Ltd (the Vendor).\n"
  "Authorised signatory: Prakash Rao\nContact: lakshmi.narayan@client.co.in\nContract no. CN-2024-0099\n",
  pii=[("Mrs. Lakshmi Narayan","NAME"),("14, MG Road, Mysuru 570001","ADDRESS"),
       ("Prakash Rao","NAME"),("lakshmi.narayan@client.co.in","EMAIL")],
  safe=["1 March 2024","CN-2024-0099"]),
 dict(name="10 No personal data", text=
  "Product specification v2.4.1\nModel X-200, weight 12.5 kg, SKU-5521, serial SN-0099231.\n"
  "Released on 2023-11-02. Tested in Room 402, Block B at 10:30.\nOrder reference ORD-77120 applies.\n",
  pii=[], safe=["v2.4.1","X-200","12.5 kg","SKU-5521","SN-0099231","2023-11-02","ORD-77120"]),
]


def spans(text, strings):
    out = []
    for s, lab in strings:
        out += [(m.start(), m.end(), s, lab) for m in re.finditer(re.escape(s), text)]
    return out


def run():
    tot = {"gt": 0, "hit": 0, "cand": 0, "tp": 0, "fp_safe": 0}
    bylab = {}
    problems = []
    d = tempfile.mkdtemp()
    for doc in DOCS:
        p = os.path.join(d, "t.txt"); open(p, "w").write(doc["text"])
        a = analyze(p); text, cands = doc["text"], a["cands"]
        gt = spans(text, doc["pii"]); safe = spans(text, [(s, "") for s in doc["safe"]])
        ov = lambda c, g: c.start < g[1] and c.end > g[0]
        missed = [g for g in gt if not any(ov(c, g) for c in cands)]
        fp = [c for c in cands if not any(ov(c, g) for g in gt)]
        fp_safe = [s for s in safe if any(ov(c, s) for c in cands)]
        for g in gt:
            L = bylab.setdefault(g[3], [0, 0]); L[0] += 1; L[1] += g not in missed
        tot["gt"] += len(gt); tot["hit"] += len(gt) - len(missed)
        tot["cand"] += len(cands); tot["tp"] += len(cands) - len(fp); tot["fp_safe"] += len(fp_safe)
        amb = [c.text for c in cands if c.ambiguous]
        print(f"{doc['name']:24} recall {len(gt)-len(missed)}/{len(gt)}  extra flags {len(fp)}  look-alikes flagged {len(fp_safe)}"
              + (f"  ambiguous->review: {amb}" if amb else ""))
        for g in missed: problems.append(f"  MISSED   [{doc['name']}] {g[2]!r} ({g[3]})")
        for c in fp: problems.append(f"  EXTRA    [{doc['name']}] {c.text!r} flagged as {c.label}")
    print("\nPer-type recall: " + ", ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(bylab.items())))
    print(f"Overall recall   {tot['hit']}/{tot['gt']} = {tot['hit']/max(1,tot['gt']):.0%}")
    print(f"Overall precision {tot['tp']}/{tot['cand']} = {tot['tp']/max(1,tot['cand']):.0%}   look-alikes wrongly flagged: {tot['fp_safe']}")
    print("\n".join(problems) or "No problems.")


if __name__ == "__main__":
    run()
