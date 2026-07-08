from datetime import datetime
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from publish_cindy_now import is_slot_window_open


class CindyTimeWindowTests(unittest.TestCase):
    def test_cindy_window_rejects_before_slot(self) -> None:
        now = datetime(2026, 7, 8, 2, 26)
        self.assertFalse(is_slot_window_open(now, "10", 3))

    def test_cindy_window_accepts_inside_window(self) -> None:
        now = datetime(2026, 7, 8, 10, 30)
        self.assertTrue(is_slot_window_open(now, "10", 3))

    def test_cindy_window_rejects_after_window(self) -> None:
        now = datetime(2026, 7, 8, 13, 1)
        self.assertFalse(is_slot_window_open(now, "10", 3))


if __name__ == "__main__":
    unittest.main()
