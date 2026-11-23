"""Plumbing tests for slm.py against a MOCK Ollama server. The mock is not a real model: it answers from a
fixed list, so this proves batching, parsing, fallbacks and confidence handling, NOT model accuracy.
Real accuracy: run `python evaluate_holdout.py slm` with Ollama running."""
import json, os, re, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PEOPLE = {"Tobias Lindqvist", "Anneliese Brandt"}
STATE = {"calls": 0, "fail": False, "tags": ["qwen2.5:1.5b"]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._send({"models": [{"name": n} for n in STATE["tags"]]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["calls"] += 1
        if STATE["fail"]: return self._send({"error": "boom"}, 500)
        items = re.findall(r"^(\d+)\. (.+?) \|", body["prompt"], re.M)
        yes = [n for n, ph in items if ph in PEOPLE]
        self._send({"response": ",".join(yes) if yes else "NONE"})


srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
sys.path.insert(0, os.path.dirname(__file__))
import summarize; summarize.HOST = f"http://127.0.0.1:{srv.server_port}"
from pipeline import analyze
W = sys.argv[1]; os.makedirs(W, exist_ok=True)


def run(text, slm=True):
    p = os.path.join(W, "s.txt"); open(p, "w").write(text); STATE["calls"] = 0
    return analyze(p, use_slm=slm)


names = lambda a: {c.text: c for c in a["cands"] if c.label == "NAME"}

# 1. discovery: a name with no cue is found only with the model
t = "She mentored Tobias Lindqvist and Anneliese Brandt on the project.\n"
a_off, a_on = run(t, False), run(t, True)
print("1. rules only :", sorted(names(a_off)))
print("   with model :", sorted(names(a_on)), "| info:", {k: a_on["slm"][k] for k in ("used", "calls", "discovered")})
assert "Tobias Lindqvist" in names(a_on) and "Tobias Lindqvist" not in names(a_off)
assert names(a_on)["Tobias Lindqvist"].source == "slm" and names(a_on)["Tobias Lindqvist"].conf == 0.6

# 2. verification: a low-confidence cue match that is NOT a person gets downgraded, a real one upgraded
a = run("Please ask Quantum Leap about it. Also with Anneliese Brandt.\n")
n = names(a)
print("2. 'Quantum Leap'     conf", n["Quantum Leap"].conf, "|", n["Quantum Leap"].reason)
print("   'Anneliese Brandt' conf", n["Anneliese Brandt"].conf, "|", n["Anneliese Brandt"].reason)
assert n["Quantum Leap"].conf <= 0.4 and n["Anneliese Brandt"].conf >= 0.8
assert "Quantum Leap" in n, "downgraded, never silently dropped"

# 3. batching: many capitalised phrases -> few calls, capped
many = "\n".join(f"The {w} Rivera Group met." if False else f"Zorblax{chr(97+i)}ton Quendrel{chr(97+i)}sh arrived." for i in range(26))
a = run(many); print("3. 26 unknown phrases ->", a["slm"]["calls"], "model calls"); assert a["slm"]["calls"] <= 4

# 4. headings: nothing invented
a = run("Annual Operations Review\nSupply Chain Overview\n"); print("4. headings flagged as names:", sorted(names(a)))
assert not names(a)

# 5. model down -> rules only, flagged in info, results intact
STATE["tags"] = []; a = run(t); print("5. no model:", a["slm"]["used"], "|", a["slm"]["note"]); assert not a["slm"]["used"]
STATE["tags"] = ["qwen2.5:1.5b"]

# 6. model errors mid-run -> rule results kept, note says so
STATE["fail"] = True; a = run("Ask Quantum Leap. Dr. Meena Rao signed.\n")
print("6. model error:", a["slm"]["note"], "| names kept:", sorted(names(a))); assert "Dr. Meena Rao" in names(a) and a["slm"]["note"]
STATE["fail"] = False

# 7. user-rejected phrase is not re-proposed by the model
from feedback import Feedback
fbp = os.path.join(W, "fb.json"); fb = Feedback(fbp); p = os.path.join(W, "s.txt")
open(p, "w").write(t); a0 = analyze(p, fb, use_slm=True); fb.reject("Tobias Lindqvist")
a1 = analyze(p, fb, use_slm=True); print("7. after reject:", sorted(names(a1))); assert "Tobias Lindqvist" not in names(a1)
print("\nALL SLM PLUMBING TESTS PASSED")
