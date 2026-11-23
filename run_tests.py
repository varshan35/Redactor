"""Run every test and the evaluation:  python run_tests.py
Each test is a standalone script; all use synthetic data, the small model is off or mocked, no network."""
import os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = [("Detection accuracy (evaluate.py)", "evaluate.py", False, "No problems."),
         ("Export + report + per-document learning", "test_report.py", True, None),
         ("Forensic inspector (live search, SHA-256)", "test_forensic.py", True, None),
         ("Re-identification risk + generalise", "test_risk.py", True, None),
         ("Privacy-safe summary", "test_summary.py", True, None),
         ("Small-model assist (mock Ollama)", "test_slm.py", True, None),
         ("App + small model", "test_app_slm.py", True, None)]

failed = 0
for title, script, wants_dir, must_contain in SUITE:
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        cmd = [sys.executable, script] + ([d] if wants_dir else [])
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    out = p.stdout + p.stderr
    ok = p.returncode == 0 and (must_contain is None or must_contain in out)
    failed += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {title:<44} {time.time() - t0:5.1f}s")
    if not ok:
        print("   " + "\n   ".join(out.strip().splitlines()[-8:]))
print("\nALL PASSED" if not failed else f"\n{failed} FAILED")
sys.exit(1 if failed else 0)
