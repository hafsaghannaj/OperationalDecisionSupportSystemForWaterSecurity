from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen


def fetch_json(url: str, *, method: str = "GET", body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = Request(url, data=data, method=method, headers=headers)
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    checks = [
        ("api health", lambda: fetch_json("http://localhost:8000/health")),
        ("pilot definition", lambda: fetch_json("http://localhost:8000/pilot")),
        (
            "cag ask",
            lambda: fetch_json(
                "http://localhost:8000/cag/ask",
                method="POST",
                body={"question": "What actions are recommended at elevated risk?"},
            ),
        ),
    ]

    for label, loader in checks:
        try:
            payload = loader()
        except URLError as exc:
            raise SystemExit(f"{label} failed: {exc}") from exc
        print(f"{label}: ok -> {list(payload)[:3]}")


if __name__ == "__main__":
    main()
