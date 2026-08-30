from __future__ import annotations

import sys
import unittest
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from machina.telemetry import _collect_power


class CpuPowerFlagTests(unittest.TestCase):
    def test_package_watts_absent_so_ok_requires_a_value(self) -> None:
        power = _collect_power()
        self.assertIsNone(power.package_power_w)
        readable_ok = power.package_power_w is not None
        if power.rapl_energy_readable:
            self.assertFalse(readable_ok)
        else:
            self.assertFalse(readable_ok)

    def test_cpu_ok_if_temp_or_usage(self) -> None:
        from machina.telemetry import Sampler
        import time

        sampler = Sampler()
        sampler.snapshot()
        time.sleep(0.35)
        snap = sampler.snapshot()
        self.assertTrue(
            snap.cpu.package_temp_c is not None or snap.cpu.usage is not None
        )
        self.assertEqual(
            snap.sources["cpu"].ok,
            snap.cpu.package_temp_c is not None or snap.cpu.usage is not None,
        )
        bat = snap.battery
        self.assertEqual(snap.sources["battery"].ok, (not bat.present) or bat.percent is not None)


if __name__ == "__main__":
    unittest.main()
