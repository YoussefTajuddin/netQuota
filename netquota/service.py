"""Init-system abstraction.

NetQuota's daemon is a single foreground process (``python3 -m netquota
daemon``) that reads its config once and loops until it receives SIGTERM.
That shape works unchanged under systemd, OpenRC (via supervise-daemon) and
runit (which supervises foreground processes natively) -- only the
start/stop/enable/disable *commands* differ. This module hides that
difference so ``app.py`` and ``install.sh``/``uninstall.sh`` can call one
API regardless of which init system is running.

Detection is intentionally conservative: it looks for the canonical marker
of each init system rather than guessing from the distro name, so it keeps
working on distros this project has never been tested on.
"""
import os
import shutil
import subprocess

UNIT_NAME = "netquota"
RUNIT_SERVICE_DIR = "/etc/sv/netquota"
# Common locations where a distro's runsvdir watches for enabled services.
RUNIT_ENABLE_DIRS = ("/var/service", "/run/runit/service", "/etc/runit/runsvdir/default")


def detect():
    """Return 'systemd', 'openrc', 'runit', or 'unknown'."""
    if os.path.isdir("/run/systemd/system"):
        return "systemd"
    if shutil.which("rc-service") and shutil.which("openrc-run"):
        return "openrc"
    if shutil.which("sv") and os.path.isdir(RUNIT_SERVICE_DIR):
        return "runit"
    # Last-resort fallbacks for systems where the primary marker is missing
    # (e.g. running inside some containers) but the tool is clearly present.
    if shutil.which("systemctl"):
        return "systemd"
    if shutil.which("rc-service"):
        return "openrc"
    if shutil.which("sv"):
        return "runit"
    return "unknown"


def _run(*args, check=False):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def _runit_enable_dir():
    for d in RUNIT_ENABLE_DIRS:
        if os.path.isdir(d):
            return d
    return RUNIT_ENABLE_DIRS[0]


def start(init=None):
    init = init or detect()
    if init == "systemd":
        _run("systemctl", "start", f"{UNIT_NAME}.service")
    elif init == "openrc":
        _run("rc-service", UNIT_NAME, "start")
    elif init == "runit":
        _run("sv", "up", UNIT_NAME)
    else:
        raise RuntimeError("No supported init system detected (systemd/openrc/runit).")


def stop(init=None):
    init = init or detect()
    if init == "systemd":
        _run("systemctl", "stop", f"{UNIT_NAME}.service")
    elif init == "openrc":
        _run("rc-service", UNIT_NAME, "stop")
    elif init == "runit":
        _run("sv", "down", UNIT_NAME)
    else:
        raise RuntimeError("No supported init system detected (systemd/openrc/runit).")


def enable(init=None):
    init = init or detect()
    if init == "systemd":
        _run("systemctl", "enable", f"{UNIT_NAME}.service")
    elif init == "openrc":
        _run("rc-update", "add", UNIT_NAME, "default")
    elif init == "runit":
        link = os.path.join(_runit_enable_dir(), UNIT_NAME)
        if not os.path.exists(link):
            os.symlink(RUNIT_SERVICE_DIR, link)
    else:
        raise RuntimeError("No supported init system detected (systemd/openrc/runit).")


def disable(init=None):
    init = init or detect()
    if init == "systemd":
        _run("systemctl", "disable", f"{UNIT_NAME}.service")
    elif init == "openrc":
        _run("rc-update", "del", UNIT_NAME, "default")
    elif init == "runit":
        link = os.path.join(_runit_enable_dir(), UNIT_NAME)
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
    else:
        raise RuntimeError("No supported init system detected (systemd/openrc/runit).")


def is_active(init=None):
    init = init or detect()
    if init == "systemd":
        return _run("systemctl", "is-active", "--quiet", f"{UNIT_NAME}.service").returncode == 0
    if init == "openrc":
        return _run("rc-service", UNIT_NAME, "status").returncode == 0
    if init == "runit":
        r = _run("sv", "status", UNIT_NAME)
        return r.returncode == 0 and r.stdout.strip().startswith("run:")
    return False


def status_text(init=None):
    init = init or detect()
    if init == "systemd":
        return _run("systemctl", "status", "--no-pager", f"{UNIT_NAME}.service").stdout
    if init == "openrc":
        return _run("rc-service", UNIT_NAME, "status").stdout
    if init == "runit":
        return _run("sv", "status", UNIT_NAME).stdout
    return "No supported init system detected (systemd/openrc/runit)."
