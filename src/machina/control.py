from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from machina import audit
from machina.privileged import try_unprivileged


@dataclass
class ApplyResult:
    ok: bool
    privileged: bool
    cancelled: bool
    message: str
    details: list[str]
    raw: dict[str, Any]


def _helper_path() -> Path:
    return Path(__file__).resolve().parent / "privileged.py"


def _pkexec_apply(actions: list[dict[str, Any]]) -> ApplyResult:
    pkexec = shutil.which("pkexec")
    if not pkexec:
        return ApplyResult(False, True, False, "pkexec is not installed; cannot elevate.", [], {})
    payload = json.dumps({"actions": actions})
    try:
        proc = subprocess.run(
            [pkexec, sys.executable, str(_helper_path())],
            input=payload,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ApplyResult(False, True, False, "Privileged helper timed out.", [], {})
    if proc.returncode in {126, 127} or "dismissed" in (proc.stderr or "").lower():
        return ApplyResult(False, True, True, "Authorization was cancelled.", [], {})
    raw_text = (proc.stdout or "").strip().splitlines()
    parsed: dict[str, Any] = {}
    if raw_text:
        try:
            parsed = json.loads(raw_text[-1])
        except json.JSONDecodeError:
            parsed = {"ok": False, "errors": [{"detail": proc.stdout[-400:]}]}
    if not parsed:
        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:400]
        return ApplyResult(False, True, False, err or "Privileged helper failed.", [], {"stderr": proc.stderr})
    details = [str(r.get("detail", "")) for r in parsed.get("results", [])]
    ok = bool(parsed.get("ok")) and proc.returncode == 0
    msg = "Applied with administrator permission." if ok else "Some privileged writes failed."
    if parsed.get("errors"):
        msg = parsed["errors"][0].get("detail", msg)
    return ApplyResult(ok, True, False, msg, details, parsed)


def apply_actions(actions: list[dict[str, Any]], reason: str = "user") -> ApplyResult:
    attempt = try_unprivileged(actions)
    details = [str(x.get("detail", "")) for x in attempt["done"]]
    leftover: list[dict[str, Any]] = list(attempt["leftover"])
    errors = attempt["errors"]

    if leftover:
        elevated = _pkexec_apply(leftover)
        details.extend(elevated.details)
        audit.log_event(
            {
                "reason": reason,
                "actions": actions,
                "ok": elevated.ok and not errors,
                "privileged": True,
                "cancelled": elevated.cancelled,
                "message": elevated.message,
                "unprivileged_done": attempt["done"],
                "errors": errors + elevated.raw.get("errors", []),
            }
        )
        if errors and elevated.ok:
            return ApplyResult(
                False,
                True,
                elevated.cancelled,
                errors[0].get("detail", "Partial failure"),
                details,
                {"unprivileged_errors": errors, **elevated.raw},
            )
        return ApplyResult(
            elevated.ok and not errors,
            True,
            elevated.cancelled,
            elevated.message if not errors else errors[0].get("detail", elevated.message),
            details,
            elevated.raw,
        )

    ok = not errors
    message = "Applied without elevation." if ok else errors[0].get("detail", "Failed")
    audit.log_event(
        {
            "reason": reason,
            "actions": actions,
            "ok": ok,
            "privileged": False,
            "cancelled": False,
            "message": message,
            "unprivileged_done": attempt["done"],
            "errors": errors,
        }
    )
    return ApplyResult(ok, False, False, message, details, {"errors": errors, "done": attempt["done"]})
