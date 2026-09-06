import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from netquota import app


class VersionCommandTests(unittest.TestCase):
    def test_version_does_not_require_a_config_file(self):
        # Regression test: main() used to construct App() (which loads and
        # validates /etc/netquota.conf) unconditionally, so `netquota
        # version` used to fail if the config was missing or broken.
        with patch('netquota.app.Config') as MockConfig:
            buf = io.StringIO()
            with redirect_stdout(buf):
                app.main(["version"])
            MockConfig.from_file.assert_not_called()
        self.assertEqual(buf.getvalue().strip(), app.__version__)


class DoctorCommandTests(unittest.TestCase):
    def test_doctor_does_not_require_a_config_file(self):
        with patch('netquota.app.Config') as MockConfig:
            with self.assertRaises(SystemExit):
                app.main(["doctor"])
            MockConfig.from_file.assert_not_called()

    def test_doctor_reports_missing_tool(self):
        with patch('shutil.which', return_value=None), \
             patch('netquota.app.service.detect', return_value="unknown"):
            self.assertFalse(app.doctor())


if __name__ == '__main__':
    unittest.main()
