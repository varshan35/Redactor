"""Forensic inspector tests: live search of the EXPORTED pdf, checksum, structure, report checksum."""
import hashlib, json, os, sys
W = sys.argv[1]; os.makedirs(W, exist_ok=True)
os.environ["REDACTOR_WORK"] = os.path.join(W, "work"); os.environ["REDACTOR_SLM"] = "0"; os.environ["OLLAMA_HOST"] = "http://127.0.0.1:1"
sys.path.insert(0, os.path.dirname(__file__))
import app as A
c = A.app.test_client()
assert c.get("/api/forensic").status_code == 404                       # nothing exported yet
j = c.post("/api/demo").get_json()
assert c.get("/api/forensic").status_code == 404                       # new document: no stale export
for x in j["cands"]:
    c.post("/api/decide", json={"id": x["id"], "status": "approved"})
c.post("/api/export")
o = c.get("/api/forensic").get_json()
real = hashlib.sha256(open(os.path.join(W, "work", "redacted.pdf"), "rb").read()).hexdigest()
assert o["sha256"] == real, "checksum must match the downloadable file"
assert o["images"] == o["pages"] and not o["annotations_present"] and o["auto_check"]["ok"]
print("overview ok:", o["pages"], "page(s), fonts", o["fonts"], "| sha256", real[:12] + "...")
s = lambda q: c.post("/api/forensic/search", json={"query": q}).get_json()
for q in ["Richa", "Sharma", "richa.sharma@meridian-logistics.com", "+91-98765-43210", "411001", "Rahul Verma", "ABCPE1234F"]:
    r = s(q); assert r["found"] is False and r["total"] == 0, (q, r)
from sample_doc import AADHAAR
assert s(AADHAAR)["total"] == 0 and s(AADHAAR.replace(" ", ""))["total"] == 0
print("removed values: 0 occurrences in every source, incl. Aadhaar with/without spaces")
r = s("[NAME_1]"); assert r["found"], "placeholders ARE in the invisible layer, so the search must be able to find them"
r = s("9876543210"); assert r["found"], "Order ID 9876543210 is deliberately NOT redacted in the demo, so it must be found"
r = s("Meridian"); assert r["found"], "text that was NOT redacted must be findable (the search is not rigged)"
print("sanity: placeholder and unredacted text are found ->", r["total"], "hit(s) for 'Meridian'")
assert c.post("/api/forensic/search", json={"query": "a"}).status_code == 400
# report carries the checksum but still no removed text
html = c.get("/report").get_data(as_text=True); rep = c.get("/api/report").get_json()
assert real in html and rep["export_check"]["sha256"] == real
blob = (html + json.dumps(rep)).lower()
assert not [t for t in ["richa", "sharma", "411001", "98765"] if t in blob]
# a txt export works too
open(os.path.join(W, "t.txt"), "w").write("Name: Ravi Kumar\nPhone: 98765 43210\n")
t = c.post("/api/upload", data={"file": (open(os.path.join(W, "t.txt"), "rb"), "t.txt")}, content_type="multipart/form-data").get_json()
for x in t["cands"]: c.post("/api/decide", json={"id": x["id"], "status": "approved"})
c.post("/api/export"); assert s("Ravi")["total"] == 0 and c.get("/api/forensic").get_json()["kind"] == "txt"
print("\nFORENSIC TESTS PASSED")
