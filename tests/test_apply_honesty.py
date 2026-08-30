from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from machina.control import ApplyResult, apply_actions


def _elevated(**kwargs: object) -> ApplyResult:
    defaults: dict = {
        "ok": True,
        "privileged": True,
        "cancelled": False,
        "message": "Applied with administrator permission.",
        "details": ["platform_profile=balanced"],
        "raw": {},
    }
    defaults.update(kwargs)
    return ApplyResult(**defaults)  # type: ignore[arg-type]


class ApplyHonestyTests(unittest.TestCase):
    def test_cancel_with_nothing_done_keeps_status_string(self) -> None:
        attempt = {
            "done": [],
            "leftover": [{"op": "set_rapl", "pl1_w": 45, "pl2_w": 90}],
            "errors": [],
        }
        cancelled = _elevated(
            ok=False,
            cancelled=True,
            message="Authorization was cancelled.",
            details=[],
        )
        with (
            patch("machina.control.try_unprivileged", return_value=attempt),
            patch("machina.control._pkexec_apply", return_value=cancelled),
            patch("machina.control.audit.log_event") as log,
        ):
            result = apply_actions([{"op": "set_rapl", "pl1_w": 45, "pl2_w": 90}])
        self.assertTrue(result.cancelled)
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Authorization cancelled — nothing changed.")
        self.assertEqual(log.call_args.args[0]["message"], result.message)
        self.assertFalse(log.call_args.args[0]["ok"])

    def test_cancel_after_unprivileged_done_does_not_claim_nothing_changed(self) -> None:
        attempt = {
            "done": [{"action": {"op": "set_backlight", "percent": 40}, "ok": True, "detail": "backlight=400/1000"}],
            "leftover": [{"op": "set_gpu_power_limit", "watts": 60}],
            "errors": [],
        }
        cancelled = _elevated(
            ok=False,
            cancelled=True,
            message="Authorization was cancelled.",
            details=[],
        )
        with (
            patch("machina.control.try_unprivileged", return_value=attempt),
            patch("machina.control._pkexec_apply", return_value=cancelled),
            patch("machina.control.audit.log_event") as log,
        ):
            result = apply_actions(
                [
                    {"op": "set_backlight", "percent": 40},
                    {"op": "set_gpu_power_limit", "watts": 60},
                ]
            )
        self.assertTrue(result.cancelled)
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Authorization cancelled — some writes already applied.")
        self.assertIn("backlight=400/1000", result.details)
        self.assertEqual(log.call_args.args[0]["ok"], False)
        self.assertEqual(log.call_args.args[0]["message"], result.message)

    def test_restore_safe_fail_detail_is_not_ok(self) -> None:
        attempt = {
            "done": [],
            "leftover": [{"op": "restore_safe"}],
            "errors": [],
        }
        elevated = _elevated(
            ok=True,
            message="Applied with administrator permission.",
            details=["platform_profile=balanced; FAIL set_gpu_power_limit: nvidia-smi failed"],
            raw={"ok": True, "results": [], "errors": []},
        )
        with (
            patch("machina.control.try_unprivileged", return_value=attempt),
            patch("machina.control._pkexec_apply", return_value=elevated),
            patch("machina.control.audit.log_event") as log,
        ):
            result = apply_actions([{"op": "restore_safe"}])
        self.assertFalse(result.cancelled)
        self.assertFalse(result.ok)
        self.assertIn("FAIL ", result.message)
        self.assertFalse(log.call_args.args[0]["ok"])

    def test_happy_path_elevated_success_unchanged(self) -> None:
        attempt = {
            "done": [],
            "leftover": [{"op": "set_platform_profile", "value": "balanced"}],
            "errors": [],
        }
        elevated = _elevated()
        with (
            patch("machina.control.try_unprivileged", return_value=attempt),
            patch("machina.control._pkexec_apply", return_value=elevated),
            patch("machina.control.audit.log_event") as log,
        ):
            result = apply_actions([{"op": "set_platform_profile", "value": "balanced"}])
        self.assertTrue(result.ok)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.message, "Applied with administrator permission.")
        self.assertTrue(log.call_args.args[0]["ok"])

    def test_unprivileged_success_unchanged(self) -> None:
        attempt = {
            "done": [{"action": {"op": "set_backlight", "percent": 50}, "ok": True, "detail": "backlight=500/1000"}],
            "leftover": [],
            "errors": [],
        }
        with (
            patch("machina.control.try_unprivileged", return_value=attempt),
            patch("machina.control.audit.log_event") as log,
        ):
            result = apply_actions([{"op": "set_backlight", "percent": 50}])
        self.assertTrue(result.ok)
        self.assertFalse(result.privileged)
        self.assertEqual(result.message, "Applied without elevation.")
        self.assertTrue(log.call_args.args[0]["ok"])


if __name__ == "__main__":
    unittest.main()
