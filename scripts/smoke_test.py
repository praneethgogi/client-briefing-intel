"""First-run smoke test: does a clean checkout actually work?

    python scripts/smoke_test.py

The unit tests and the eval gate both run against an already-built store. Neither
starts the server, and neither renders the UI - so a first-run failure, or a
front-end regression, passes CI untouched. This walks the path a reviewer takes:
start the API from nothing, with no API key, and drive the endpoints the app calls
on load.

It found nothing on its own, but the bug that prompted it (a collapsed section
printing a stray "0") was invisible to every other check we had.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("SMOKE_PORT", "8099"))
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  - ' + detail) if detail else ''}")
    if not ok:
        failures.append(name)


def get(path: str, user: str = "ava.chen", method: str = "GET", body: bytes | None = None):
    req = urllib.request.Request(BASE + path, method=method, data=body,
                                 headers={"X-User-Id": user, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read() or "null")


def wait_for_api(proc: subprocess.Popen, seconds: int = 90) -> bool:
    for _ in range(seconds):
        if proc.poll() is not None:
            return False
        try:
            get("/api/health")
            return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(1)
    return False


def main() -> int:
    env = {**os.environ, "CBI_DB_PATH": str(ROOT / "data" / "smoke.db")}
    Path(env["CBI_DB_PATH"]).unlink(missing_ok=True)   # a genuinely first run
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api.main:app", "--port", str(PORT)],
        cwd=str(ROOT / "backend"), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        if not wait_for_api(proc):
            print("  FAIL  the API never came up")
            return 1

        health = get("/api/health")
        check("health responds", health.get("status") == "ok", health.get("llm_mode", ""))

        clients = get("/api/clients")
        check("clients listed", len(clients) >= 1, f"{len(clients)} covered")

        cal = get("/api/readiness")
        check("calendar triage", cal.get("total", 0) >= 1,
              f"{cal.get('by_state')}")
        check("triage gives reasons", any(m["data"] or m["prep"] for m in cal["meetings"]))

        cid = clients[0]["client_id"]
        b = get(f"/api/clients/{cid}/briefings", method="POST", body=b"{}")
        check("briefing builds", len(b.get("sections", [])) == 7,
              f"{len(b.get('sections', []))} sections")
        check("a pack was selected", bool(b.get("pack", {}).get("id")), b.get("pack", {}).get("id", ""))
        check("every section has content", all(s["bullets"] for s in b["sections"]))
        check("every bullet is cited",
              all(x["citations"] for s in b["sections"] for x in s["bullets"]))
        check("conflicts detected", len(b.get("conflicts", [])) >= 1,
              f"{len(b.get('conflicts', []))}")

        # Entitlements are the one thing that must never regress quietly.
        denied = False
        try:
            get("/api/clients/C001/briefings", user="ben.osei", method="POST", body=b"{}")
        except urllib.error.HTTPError as e:
            denied = e.code == 403
        check("uncovered user is refused", denied)

        print()
        print("smoke: " + ("all checks passed" if not failures
                           else f"{len(failures)} failed -> {', '.join(failures)}"))
        return 1 if failures else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        Path(env["CBI_DB_PATH"]).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
