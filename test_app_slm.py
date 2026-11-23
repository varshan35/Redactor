"""App-level test of the small-model wiring against a MOCK Ollama (proves plumbing, not model accuracy)."""
import json, os, re, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

STATE = {"calls": 0, "tags": ["qwen2.5:1.5b"]}
PEOPLE = {"Tobias Lindqvist"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o):
        b = json.dumps(o).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._send({"models": [{"name": n} for n in STATE["tags"]]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); STATE["calls"] += 1
        items = re.findall(r"^(\d+)\. (.+?) \|", body["prompt"], re.M)
        yes = [n for n, ph in items if ph in PEOPLE]
        self._send({"response": ",".join(yes) if yes else "NONE"})


srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
W = sys.argv[1]; os.makedirs(W, exist_ok=True); os.environ["REDACTOR_WORK"] = os.path.join(W, "work")
sys.path.insert(0, os.path.dirname(__file__))
import summarize; summarize.HOST = f"http://127.0.0.1:{srv.server_port}"
import app as A
c = A.app.test_client()
p = os.path.join(W, "t.txt"); open(p, "w").write("She mentored Tobias Lindqvist on the project.\nName: Anita Verma\n")
up = lambda: c.post("/api/upload", data={"file": (open(p, "rb"), "t.txt")}, content_type="multipart/form-data").get_json()

j = up(); names = {x["text"] for x in j["cands"] if x["label"] == "NAME"}
print("1. upload with model:", sorted(names), "|", {k: j["slm"][k] for k in ("enabled", "used", "calls", "discovered")})
assert "Tobias Lindqvist" in names and j["slm"]["used"] and j["slm"]["calls"] >= 1
calls_after_upload = STATE["calls"]

STATE["calls"] = 0; j = c.post("/api/rescan").get_json()
print("2. rescan: new model calls =", STATE["calls"], "(cached)"); assert STATE["calls"] == 0

j = c.post("/api/slm", json={"enabled": False}).get_json(); names = {x["text"] for x in j["cands"] if x["label"] == "NAME"}
print("3. model off:", sorted(names), "|", j["slm"]["enabled"]); assert "Tobias Lindqvist" not in names and "Anita Verma" in names

j = c.post("/api/slm", json={"enabled": True}).get_json(); names = {x["text"] for x in j["cands"] if x["label"] == "NAME"}
print("4. model on again:", sorted(names)); assert "Tobias Lindqvist" in names

STATE["tags"] = []; j = up()
print("5. Ollama down:", j["slm"]["used"], "|", j["slm"]["note"]); assert not j["slm"]["used"] and "Anita Verma" in {x["text"] for x in j["cands"]}
print("\nAPP SLM WIRING TESTS PASSED")
