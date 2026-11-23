"""HELD-OUT test set: written after the name lists were frozen, using names that are NOT in names_data.py.
Measures what the rules alone miss, and (with Ollama running) what the small model recovers.
    python evaluate_holdout.py          rules only
    python evaluate_holdout.py slm      rules + small model (needs Ollama)"""
import os, re, sys, tempfile
from names_data import FIRST_NAMES, SURNAMES
from pipeline import analyze

DOCS = [
 ("H1 meeting", "Minutes of the budget meeting.\nPresent: Oluwaseun Adebayo, Tamsin Whitlock and Ravindranath Tagore.\n"
  "The proposal from Zainab Okonkwo was accepted. Contact Bartholomew Quill for the revised numbers.\n",
  ["Oluwaseun Adebayo","Tamsin Whitlock","Ravindranath Tagore","Zainab Okonkwo","Bartholomew Quill"],
  ["Minutes","Present"]),
 ("H2 customer note", "Customer called about delivery. Spoke with Imogen Fairweather at the Delhi branch.\n"
  "Callback requested by Lakshmipriya Venkataraghavan before Friday.\nTicket TCK-5512 closed on 2024-06-18.\n",
  ["Imogen Fairweather","Lakshmipriya Venkataraghavan"],["TCK-5512","2024-06-18"]),
 ("H3 reference letter", "To whom it may concern,\nI worked with Dhruvanshi Kothari for four years at the Infosys Campus.\n"
  "She mentored Tobias Lindqvist and Anneliese Brandt on the Atlas Platform project.\n",
  ["Dhruvanshi Kothari","Tobias Lindqvist","Anneliese Brandt"],["Infosys Campus","Atlas Platform"]),
 ("H4 headings (no people)", "Annual Operations Review\nSupply Chain Overview\nNorthern Region Summary\n"
  "Key Performance Indicators improved. The Digital Transformation Programme continues at Mumbai Port.\n",
  [], ["Annual Operations Review","Supply Chain Overview","Northern Region Summary",
       "Key Performance Indicators","Digital Transformation Programme","Mumbai Port"]),
]


def run(use_slm):
    d = tempfile.mkdtemp(); hit = tot = fp = 0; rows = []
    for name, text, people, safe in DOCS:
        p = os.path.join(d, "h.txt"); open(p, "w").write(text)
        a = analyze(p, use_slm=use_slm); c = a["cands"]
        ov = lambda s, e: any(x.start < e and x.end > s for x in c)
        for n in people:
            m = re.search(re.escape(n), text); tot += 1
            ok = ov(m.start(), m.end()); hit += ok
            if not ok: rows.append(f"  MISSED  [{name}] {n}")
        for s in safe:
            m = re.search(re.escape(s), text)
            if m and ov(m.start(), m.end()): fp += 1; rows.append(f"  EXTRA   [{name}] flagged {s!r}")
        if use_slm: print(f"  {name}: slm {a['slm']}")
    print(f"{'rules + small model' if use_slm else 'rules only'}: recall {hit}/{tot}  look-alike/heading false flags {fp}")
    print("\n".join(rows) or "  none")
    leak = [n for _, _, ps, _ in DOCS for n in ps if any(w.lower() in FIRST_NAMES | SURNAMES for w in n.split())]
    print(f"  (names in these docs that appear in the lists: {leak or 'none'})")


if __name__ == "__main__":
    run(len(sys.argv) > 1 and sys.argv[1] == "slm")
