"""Lightweight smoke check for a deployed/local BizXusAI API.

Run from backend/:
    python scripts/smoke_check.py http://localhost:8000/api/v1
"""

from __future__ import annotations

import sys
import httpx

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api/v1").rstrip("/")
ENDPOINTS = ["/health", "/health/readiness", "/health/demo-accounts", "/health/phase-summary", "/health/submission-summary"]


def main() -> int:
    print(f"Running smoke checks against {BASE_URL}")
    failures = 0
    with httpx.Client(timeout=10) as client:
        for endpoint in ENDPOINTS:
            url = f"{BASE_URL}{endpoint}"
            try:
                response = client.get(url)
                ok = 200 <= response.status_code < 300
                print(f"{'PASS' if ok else 'FAIL'} {endpoint} -> {response.status_code}")
                if not ok:
                    failures += 1
            except Exception as exc:
                print(f"FAIL {endpoint} -> {exc}")
                failures += 1
    if failures:
        print(f"Smoke check completed with {failures} failure(s).")
        return 1
    print("Smoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
