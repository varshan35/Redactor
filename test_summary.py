"""Tests the summarizer: fallback path, Ollama path (mock server), scrub, QID, failed-check fallback."""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

MODE = {"reply": "", "tags": ["qwen2.5:1.5b"], "seen": []}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o):
        b = json.dumps(o).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        self._send({"models": [{"name": n} for n in MODE["tags"]]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        MODE["seen"].append(body["prompt"])
        self._send({"response": MODE["reply"]})


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:1"          # nothing listens here at first
sys.path.insert(0, os.path.dirname(__file__))
import summarize as S
from pipeline import analyze

W = sys.argv[1]
os.makedirs(W, exist_ok=True)
TXT = (
    "Employee Name: Richa Sharma\nEmail: richa.sharma@acme-analytics.com\nPhone: +91-98765-43210\n"
    "Address: Flat 402, Lotus Heights, 14 MG Road, Pune 411001\n\n"
    "Performance review. Ms. Sharma, the CFO of the Pune office, led the migration of product PROD-404 "
    "during 2023. R. Sharma exceeded every quarterly target and the team reports strong morale. "
    "The migration reduced infrastructure costs by twenty percent across all regions. "
    "Priya Nair recommends a promotion and a budget increase for the migration programme next year.\n")
p = os.path.join(W, "review.txt"); open(p, "w").write(TXT)
a = analyze(p)
approved = a["cands"]


def show(title, r):
    print(f"--- {title}\n  method : {r['method']}\n  ok     : {r['ok']}\n  summary: {r['summary']}")
    for l in r["log"]: print("  log    :", l)
    if r["remaining"]["leaks"] or r["remaining"]["detector_hits"]:
        print("  REMAINING:", r["remaining"])


def leaked(summary):
    bad = ["Richa", "Sharma", "richa.sharma", "acme-analytics", "98765", "Lotus", "411001", "Priya", "Nair"]
    return [b for b in bad if b.lower() in summary.lower()]


# 1. Ollama not running -> rule-based fallback
r1 = S.make_summary(a["doc"], approved); show("1. Ollama down", r1)
assert r1["method"] == "rules" and r1["ok"] and not leaked(r1["summary"])

# 2. Ollama up, clean model output that keeps placeholders
os.environ["OLLAMA_HOST"] = S.HOST = f"http://127.0.0.1:{srv.server_port}"
MODE["reply"] = "[NAME_1] led a product migration and exceeded targets. [NAME_2] recommends a promotion."
r2 = S.make_summary(a["doc"], approved); show("2. Ollama clean", r2)
assert r2["method"].startswith("ollama") and r2["ok"]
assert "Richa" not in MODE["seen"][-1] and "[NAME_1]" in MODE["seen"][-1], "model must only see redacted text"
print("  model prompt contained no raw PII: OK")

# 3. Ollama leaks a name + email domain + pincode -> scrubbed
MODE["reply"] = "Richa led the work from Pune 411001; contact acme-analytics. [NAME_2] backs a promotion."
r3 = S.make_summary(a["doc"], approved); show("3. Ollama leaks -> scrub", r3)
assert r3["ok"] and not leaked(r3["summary"])

# 4. quasi-identifier combination spread over two sentences
MODE["reply"] = ("The CFO of a Pune-based fintech startup led the project. "
                 "The 54-year-old executive joined in 2021. [NAME_2] agrees.")
r4 = S.make_summary(a["doc"], approved); show("4. QID combination", r4)
assert r4["qid_findings"] and "CFO" not in r4["summary"] and "Pune" not in r4["summary"] and "54" not in r4["summary"]

# 5. model invents a placeholder and an unredacted-looking email -> blocked, rule fallback used
MODE["reply"] = "[NAME_9] wrote to someone.test@example.org about the migration."
r5 = S.make_summary(a["doc"], approved); show("5. invented placeholder / new PII", r5)
assert r5["method"].startswith("rules") and r5["ok"]

# 6. long document -> map-reduce (several model calls)
open(p, "w").write(TXT + ("\nFiller paragraph about quarterly planning and delivery. " * 60 + "\n\n") * 6)
a2 = analyze(p); MODE["seen"].clear(); MODE["reply"] = "A short partial summary about delivery planning."
r6 = S.make_summary(a2["doc"], a2["cands"])
print(f"--- 6. long doc: {len(MODE['seen'])} model calls, ok={r6['ok']}")
assert len(MODE["seen"]) > 2

# 7. Ollama up but no model installed -> fallback
MODE["tags"] = []
r7 = S.make_summary(a["doc"], approved); print("--- 7. no model installed ->", r7["method"], "|", r7["log"][0])
assert r7["method"] == "rules"
print("\nALL SUMMARY TESTS PASSED")
