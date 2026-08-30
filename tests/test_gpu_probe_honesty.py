from __future__ import annotations

import sys
import unittest
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from machina.gpu_layers import highest_fitting


class GpuProbeHonestyTests(unittest.TestCase):
    def test_nothing_fits_stays_below_low(self) -> None:
        self.assertEqual(highest_fitting(1, 8, lambda _n: False), 0)
        floor = 32
        best = highest_fitting(max(floor, 1), 48, lambda _n: False)
        self.assertLess(best, max(floor, 1))

    def test_true_fit_is_kept(self) -> None:
        self.assertEqual(highest_fitting(1, 8, lambda n: n <= 5), 5)


if __name__ == "__main__":
    unittest.main()
