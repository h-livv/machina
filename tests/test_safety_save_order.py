from __future__ import annotations

import sys
import unittest
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from machina.guardrails import DEFAULTS, thresholds_ordered


class SafetySaveOrderTests(unittest.TestCase):
    def test_defaults_are_ordered(self) -> None:
        self.assertTrue(
            thresholds_ordered(
                DEFAULTS["warn_temp_c"],
                DEFAULTS["trip_temp_c"],
                DEFAULTS["critical_temp_c"],
            )
        )

    def test_equal_or_inverted_rejected(self) -> None:
        self.assertFalse(thresholds_ordered(90, 90, 100))
        self.assertFalse(thresholds_ordered(97, 90, 100))
        self.assertFalse(thresholds_ordered(90, 100, 97))
        self.assertFalse(thresholds_ordered(100, 97, 90))

    def test_strict_increase_accepted(self) -> None:
        self.assertTrue(thresholds_ordered(80, 90, 100))
        self.assertTrue(thresholds_ordered(90, 97, 100))


if __name__ == "__main__":
    unittest.main()
