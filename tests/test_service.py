import unittest
from unittest.mock import patch, MagicMock
from netquota import service


class ServiceDetectTests(unittest.TestCase):
    def test_detects_systemd_first(self):
        with patch('os.path.isdir', side_effect=lambda p: p == "/run/systemd/system"):
            self.assertEqual(service.detect(), "systemd")

    def test_detects_openrc_when_no_systemd(self):
        with patch('os.path.isdir', return_value=False), \
             patch('shutil.which', side_effect=lambda x: "/sbin/" + x if x in ("rc-service", "openrc-run") else None):
            self.assertEqual(service.detect(), "openrc")

    def test_detects_runit_when_no_systemd_or_openrc(self):
        def isdir(p):
            return p == service.RUNIT_SERVICE_DIR
        with patch('os.path.isdir', side_effect=isdir), \
             patch('shutil.which', side_effect=lambda x: "/bin/sv" if x == "sv" else None):
            self.assertEqual(service.detect(), "runit")

    def test_unknown_when_nothing_found(self):
        with patch('os.path.isdir', return_value=False), patch('shutil.which', return_value=None):
            self.assertEqual(service.detect(), "unknown")


class ServiceCommandTests(unittest.TestCase):
    def test_start_dispatches_to_systemctl(self):
        with patch('netquota.service._run') as r:
            service.start(init="systemd")
            r.assert_called_once_with("systemctl", "start", "netquota.service")

    def test_start_dispatches_to_rc_service(self):
        with patch('netquota.service._run') as r:
            service.start(init="openrc")
            r.assert_called_once_with("rc-service", "netquota", "start")

    def test_start_dispatches_to_sv(self):
        with patch('netquota.service._run') as r:
            service.start(init="runit")
            r.assert_called_once_with("sv", "up", "netquota")

    def test_unknown_init_raises(self):
        with self.assertRaises(RuntimeError):
            service.start(init="unknown")

    def test_is_active_systemd(self):
        with patch('netquota.service._run', return_value=MagicMock(returncode=0)):
            self.assertTrue(service.is_active(init="systemd"))
        with patch('netquota.service._run', return_value=MagicMock(returncode=3)):
            self.assertFalse(service.is_active(init="systemd"))

    def test_is_active_runit_checks_status_text(self):
        with patch('netquota.service._run', return_value=MagicMock(returncode=0, stdout="run: /etc/sv/netquota: (pid 1) 3s")):
            self.assertTrue(service.is_active(init="runit"))
        with patch('netquota.service._run', return_value=MagicMock(returncode=0, stdout="down: /etc/sv/netquota: 1s")):
            self.assertFalse(service.is_active(init="runit"))


if __name__ == '__main__':
    unittest.main()
