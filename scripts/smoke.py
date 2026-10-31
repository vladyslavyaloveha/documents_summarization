"""Smoke test against a running stack: `uv run python scripts/smoke.py [base_url]`."""

import sys

import httpx


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    with httpx.Client(base_url=base_url, timeout=5) as client:
        for path in ("/health", "/ready"):
            response = client.get(path)
            print(f"GET {path} -> {response.status_code} {response.text}")
            if response.status_code != 200:
                return 1
    print("smoke: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
