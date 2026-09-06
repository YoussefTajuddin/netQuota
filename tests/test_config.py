import tempfile
import unittest
from pathlib import Path

from netquota.config import Config


class ConfigFromFileTests(unittest.TestCase):
    def test_missing_file_raises_friendly_error(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "does-not-exist.conf"
            with self.assertRaises(SystemExit) as cm:
                Config.from_file(missing)
            self.assertIn("Config file not found", str(cm.exception))

    def test_empty_interface_raises_friendly_error(self):
        # This is the exact shape install.sh's example config ships with
        # before the interactive wizard fills it in — must fail loudly
        # with guidance, not a bare KeyError.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "netquota.conf"
            p.write_text("INTERFACE=\nLIMIT_BYTES=50000000000\nPERIOD_DAYS=28\n")
            with self.assertRaises(SystemExit) as cm:
                Config.from_file(p)
            self.assertIn("INTERFACE is missing or empty", str(cm.exception))

    def test_missing_interface_key_raises_friendly_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "netquota.conf"
            p.write_text("LIMIT_BYTES=50000000000\n")
            with self.assertRaises(SystemExit):
                Config.from_file(p)

    def test_valid_file_loads(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "netquota.conf"
            p.write_text("INTERFACE=eth0\nLIMIT_BYTES=1000\nPERIOD_DAYS=7\n")
            cfg = Config.from_file(p)
            self.assertEqual(cfg.interface, "eth0")
            self.assertEqual(cfg.limit_bytes, 1000)
            self.assertEqual(cfg.period_days, 7)

    def test_invalid_number_raises_friendly_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "netquota.conf"
            p.write_text("INTERFACE=eth0\nLIMIT_BYTES=not-a-number\n")
            with self.assertRaises(SystemExit) as cm:
                Config.from_file(p)
            self.assertIn("Invalid value", str(cm.exception))


if __name__ == '__main__':
    unittest.main()
