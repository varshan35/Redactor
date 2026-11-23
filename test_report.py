"""Report + demo + per-document learning tests (mock Ollama is NOT needed: the small model is switched off)."""
import json, os, sys
W = sys.argv[1]; os.makedirs(W, exist_ok=True)
os.environ["REDACTOR_WORK"] = os.path.join(W, "work"); os.environ["REDACTOR_SLM"] = "0"; os.environ["OLLAMA_HOST"] = "http://127.0.0.1:1"
sys.path.insert(0, os.path.dirname(__file__))
import app as A
c = A.app.test_client()

j = c.post("/api/demo").get_json()
print("1. demo loaded:", len(j["cands"]), "candidates,", j["kind"])
assert j["kind"] == "pdf" and len(j["cands"]) >= 14

# approve everything, export, summary, report
for x in j["cands"]:
    c.post("/api/decide", json={"id": x["id"], "status": "approved"})
exp = c.post("/api/export").get_json(); print("2. export verification ok:", exp["verification"]["ok"], "engines:", exp["verification"]["engines"])
assert exp["verification"]["ok"]
sm = c.post("/api/summary").get_json(); print("3. summary ok:", sm["ok"], "|", sm["method"])
rep = c.get("/api/report").get_json(); html = c.get("/report").get_data(as_text=True)
print("4. report totals:", rep["totals"], "| export passed:", rep["export_check"]["passed"], "| summary passed:", rep["summary_check"]["passed"])

# the report must not contain ANY removed text
secrets = [x["text"] for x in j["cands"]] + ["Richa", "Sharma", "Priya", "Nair", "Rahul", "Verma", "meridian-logistics", "Lotus", "411001", "98765"]
blob = json.dumps(rep) + html
leaked = [s for s in secrets if len(s) >= 4 and s.lower() in blob.lower()]
print("5. removed text found in report:", leaked or "none"); assert not leaked

# per-document learning: reject in doc A must NOT hide the same text in doc B
open(os.path.join(W, "a.txt"), "w").write("Reference Ravi Kumar was mentioned. Name: Ravi Kumar\n")
open(os.path.join(W, "b.txt"), "w").write("Name: Ravi Kumar\nPhone: 98765 43210\n")
up = lambda p: c.post("/api/upload", data={"file": (open(p, "rb"), os.path.basename(p))}, content_type="multipart/form-data").get_json()
a = up(os.path.join(W, "a.txt")); rk = [x for x in a["cands"] if x["text"] == "Ravi Kumar"]
for x in rk: c.post("/api/decide", json={"id": x["id"], "status": "rejected"})
a2 = c.post("/api/rescan").get_json(); print("6. doc A after reject:", [x["text"] for x in a2["cands"] if x["label"] == "NAME"])
b = up(os.path.join(W, "b.txt")); print("   doc B (same name):", [x["text"] for x in b["cands"] if x["label"] == "NAME"])
assert any(x["text"] == "Ravi Kumar" for x in b["cands"]), "a reject in one document must not hide PII in another"
c.post("/api/reset_learning"); print("\nREPORT / DEMO / LEARNING TESTS PASSED")
