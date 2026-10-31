"""Smoke test against a running stack: `uv run python scripts/smoke.py [base_url] [pdf]`."""

import sys
import time
from pathlib import Path

import httpx

DEFAULT_PDF = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample.pdf"
TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.5


def check_health(client: httpx.Client) -> bool:
    for path in ("/health", "/ready"):
        response = client.get(path)
        print(f"GET {path} -> {response.status_code} {response.text}")
        if response.status_code != 200:
            return False
    return True


def process_pdf(client: httpx.Client, pdf_path: Path) -> bool:
    files = [("files", (pdf_path.name, pdf_path.read_bytes(), "application/pdf"))]
    response = client.post("/api/documents", files=files, data={"parser": "pypdf"})
    print(f"POST /api/documents -> {response.status_code}")
    if response.status_code != 202:
        print(response.text)
        return False
    document_id = response.json()[0]["id"]

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        document = client.get(f"/api/documents/{document_id}").json()
        if document["status"] in ("done", "failed"):
            print(
                f"document {document_id}: {document['status']} {document.get('error') or ''}"
            )
            for page in document["pages"]:
                print(f"  page {page['number']}: {page['markdown'][:80]!r}")
            return bool(document["status"] == "done")
        time.sleep(POLL_INTERVAL_SECONDS)
    print(f"document {document_id}: not finished after {TIMEOUT_SECONDS}s")
    return False


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    pdf_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PDF
    with httpx.Client(base_url=base_url, timeout=30) as client:
        ok = check_health(client) and process_pdf(client, pdf_path)
    print("smoke: OK" if ok else "smoke: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
