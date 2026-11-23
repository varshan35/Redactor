"""Re-identification risk (rule-based heuristic), attacker query, generalisation with change list."""
import os, sys
W = sys.argv[1]; os.makedirs(W, exist_ok=True)
os.environ["REDACTOR_WORK"] = os.path.join(W, "work"); os.environ["REDACTOR_SLM"] = "0"; os.environ["OLLAMA_HOST"] = "http://127.0.0.1:1"
sys.path.insert(0, os.path.dirname(__file__))
from summarize import risk_assess, _generalise, risk_in_document
import app as A, json
t = "[NAME_1], the CFO of a Pune-based robotics startup founded in 2021, led the migration."
r = risk_assess(t); print(r)
assert r["level"] == "High" and r["query"].startswith("site:linkedin.com") and '"CFO"' in r["query"] and '"Pune"' in r["query"]
assert "candidates" not in json.dumps(r) and "est" not in r["query"].lower()      # no invented counts
ch = []; g = _generalise(t, ch); print(g, ch)
assert "Pune" not in g and "CFO" not in g and "2021" not in g and "Western India" in g and risk_assess(g)["level"] == "Low"
assert any("CFO" == c["from"] for c in ch) and any("Pune" in c["from"] for c in ch)
assert risk_assess("The team shipped the release on schedule.")["level"] == "Low"
assert risk_assess("The manager in Mumbai joined in 2020.")["level"] == "Medium"
c = A.app.test_client(); j = c.post("/api/demo").get_json()
for x in j["cands"]: c.post("/api/decide", json={"id": x["id"], "status": "approved"})
s = c.post("/api/summary").get_json(); k = s["risk"]
print("demo summary risk:", k["before"]["level"], "->", k["after"]["level"], "| doc:", k["document"]["level"], "|", k["before"]["query"])
assert k["before"]["level"] == "High" and k["after"]["level"] == "Low" and k["changes"] and s["ok"]
assert "CFO" in k["raw_summary"] and "CFO" not in s["summary"]
assert k["document"]["level"] == "High"           # the body still has CFO + Pune + 2019 in one sentence
rep = c.get("/report").get_data(as_text=True); assert "heuristic" in rep and "CFO" not in rep and "Pune" not in rep
print("\nRISK TESTS PASSED")
