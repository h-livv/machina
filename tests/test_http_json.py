from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from machina.util import http_json


class _Resp:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class HttpJsonTests(unittest.TestCase):
    def test_empty_body_is_not_ok(self) -> None:
        with patch("urllib.request.urlopen", return_value=_Resp("  ")):
            ok, data, err = http_json("http://127.0.0.1/x")
        self.assertFalse(ok)
        self.assertIsNone(data)
        self.assertIn("empty", err)

    def test_non_json_is_not_ok(self) -> None:
        with patch("urllib.request.urlopen", return_value=_Resp("<html>nope</html>")):
            ok, data, err = http_json("http://127.0.0.1/x")
        self.assertFalse(ok)
        self.assertIsNone(data)
        self.assertIn("html", err.lower())

    def test_json_still_ok(self) -> None:
        with patch("urllib.request.urlopen", return_value=_Resp(json.dumps({"version": "1"}))):
            ok, data, err = http_json("http://127.0.0.1/x")
        self.assertTrue(ok)
        self.assertEqual(data, {"version": "1"})
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
