from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from machina.privileged import _comm_matches


class CommMatchTests(unittest.TestCase):
    def test_matches_this_process(self) -> None:
        pid = os.getpid()
        comm = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
        self.assertTrue(_comm_matches(pid, comm))
        self.assertTrue(_comm_matches(pid, comm[:15]))
        self.assertFalse(_comm_matches(pid, "not-this-process-zzzz"))

    def test_gone_pid_does_not_match(self) -> None:
        self.assertFalse(_comm_matches(2**30, "bash"))


if __name__ == "__main__":
    unittest.main()
