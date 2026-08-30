from __future__ import annotations

import json
import time
from typing import Any

from machina.paths import audit_path


def log_event(event: dict[str, Any]) -> None:
    payload = {"ts": time.time(), **event}
    path = audit_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


def read_recent(limit: int = 200) -> list[dict[str, Any]]:
    path = audit_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows = []
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rows.reverse()
    return rows
