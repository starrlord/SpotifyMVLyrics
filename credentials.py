"""Read/write Spotify credentials from a local JSON file.

The file is stored next to the script and should never be committed
(it is listed in .gitignore).
"""
from __future__ import annotations

import json
from pathlib import Path

_FILE = Path(__file__).parent / ".credentials.json"


def load() -> dict[str, str]:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save(client_id: str, client_secret: str) -> None:
    _FILE.write_text(
        json.dumps({"client_id": client_id, "client_secret": client_secret}, indent=2),
        encoding="utf-8",
    )


def get_client_id() -> str:
    return load().get("client_id", "")


def get_client_secret() -> str:
    return load().get("client_secret", "")


def are_set() -> bool:
    c = load()
    return bool(c.get("client_id") and c.get("client_secret"))
