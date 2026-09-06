import argparse
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

from . import __version__
from .config import Config, CONFIG_PATH
from .state import State
from . import firewall, network, service, vnstat
from .duration import seconds
from .ui import status_text, human, c


class App:
    def __init__(self, config_path=CONFIG_PATH):
        self.config_path = config_path
        self.cfg = Config.from_file(config_path)
        self.cfg.validate()

    def state(self):
        return State.load(self.cfg.state_file, self.cfg.period_days)

    def reset(self):
        s = State.new(self.cfg.period_days)
        firewall.install(self.cfg, 0)
        s.save(self.cfg.state_file)
        return s

    def bypass(self, duration):
        s = self.state()
        sec = seconds(duration)
        v4, v6 = network.interface_addresses(self.cfg.interface)
        until = datetime.now(timezone.utc).timestamp() + sec
        s.bypass_until = datetime.fromtimestamp(until, timezone.utc).isoformat()
        s.save(self.cfg.state_file)
        firewall.add_bypass((v4, v6), sec)
        return s

    def bypass_off(self):
        s = self.state()
        firewall.clear_bypass()
        s.bypass_until = None
        s.save(self.cfg.state_file)

    def daemon(self):
        s = self.state()
        firewall.install(self.cfg, s.used_bytes)
        if s.bypass_until:
            try:
                until = datetime.fromisoformat(s.bypass_until)
                remaining = max(0, int((until - datetime.now(timezone.utc)).total_seconds()))
                if remaining:
                    firewall.add_bypass(network.interface_addresses(self.cfg.interface), remaining)
                else:
                    s.bypass_until = None
            except Exception as e:
                print(f"netquota bypass restore: {e}", flush=True)
        last = 0
        stop = False

        def sig(*_):
            nonlocal stop
            stop = True

        signal.signal(signal.SIGTERM, sig)
        signal.signal(signal.SIGINT, sig)
        while not stop:
            try:
                now = datetime.now(timezone.utc)
                if s.expired(now):
                    s = State.new(self.cfg.period_days)
                    firewall.install(self.cfg, 0)
                    last = 0
                used = firewall.get_quota_used()
                delta = used - last if used >= last else used
                s.used_bytes = min(self.cfg.limit_bytes, s.used_bytes + delta)
                last = used
                s.blocked = s.used_bytes >= self.cfg.limit_bytes
                if s.bypass_until and datetime.fromisoformat(s.bypass_until) <= now:
                    firewall.clear_bypass()
                    s.bypass_until = None
                s.save(self.cfg.state_file)
                time.sleep(self.cfg.poll_seconds)
            except Exception as e:
                print(f"netquota: {e}", flush=True)
                time.sleep(self.cfg.poll_seconds)
        # The service's stop hook (systemd ExecStopPost / OpenRC stop_post /
        # runit finish) removes the nftables table on every stop, including
        # this one, so a plain service stop always restores full Internet
        # access rather than freezing the last-installed drop rule in place.

    def status(self):
        s = self.state()
        v = None
        try:
            v = vnstat.read(self.cfg.interface)
        except Exception:
            pass
        active = service.is_active()
        print(status_text(s, self.cfg, v, self.cfg.interface, service_active=active))

    def usage(self):
        s = self.state()
        print(f"Quota: {human(self.cfg.limit_bytes)}")
        print(f"Used: {human(s.used_bytes)}")
        print(f"Remaining: {human(max(0, self.cfg.limit_bytes - s.used_bytes))}")
        print(f"Period: {s.period_start} -> {s.period_end}")

    def config(self):
        print(self.config_path)
        with open(self.config_path, encoding="utf-8") as f:
            print(f.read(), end="")

    def setup(self):
        print("Available interfaces:")
        for x in network.interfaces():
            marker = "*" if x["name"] == self.cfg.interface else " "
            print(" {} {} ({}) {}".format(marker, x["name"], x["type"], "UP" if x["up"] else "DOWN"))
        name = input(f"Interface [{self.cfg.interface}]: ").strip() or self.cfg.interface
        if not network.valid_interface(name):
            raise SystemExit(f"Unknown interface: {name}")
        limit = input(f"Quota GB [{self.cfg.limit_bytes / 1_000_000_000:g}]: ").strip()
        days = input(f"Period days [{self.cfg.period_days}]: ").strip()
        lines = open(self.config_path, encoding="utf-8").readlines()
        vals = {"INTERFACE": name}
        if limit:
            vals["LIMIT_BYTES"] = str(int(float(limit) * 1_000_000_000))
        if days:
            vals["PERIOD_DAYS"] = str(int(days))
        out = []
        seen = set()
        for line in lines:
            key = line.split("=", 1)[0] if "=" in line else ""
            if key in vals:
                out.append(f"{key}={vals[key]}\n")
                seen.add(key)
            else:
                out.append(line)
        for key, val in vals.items():
            if key not in seen:
                out.append(f"{key}={val}\n")
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.writelines(out)
        print("Configuration updated. Restart the netquota service to apply it.")

    def interface(self, name=None):
        if name is None:
            print(f"Interface: {self.cfg.interface}")
            return
        if not network.valid_interface(name):
            raise SystemExit(f"Unknown interface: {name}")
        with open(self.config_path, encoding="utf-8") as f:
            lines = f.readlines()
        found = False
        out = []
        for line in lines:
            if line.startswith("INTERFACE="):
                out.append(f"INTERFACE={name}\n")
                found = True
            else:
                out.append(line)
        if not found:
            out.insert(0, f"INTERFACE={name}\n")
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.writelines(out)
        print(f"Interface changed to {name}. Restart the netquota service to apply.")

    def service_status(self):
        print(service.status_text())

    def off(self):
        service.stop()
        service.disable()

    def on(self):
        service.enable()
        service.start()


def _check(label, ok, hint=""):
    mark = c("1;32", "✓") if ok else c("1;31", "✗")
    print(f"  {mark} {label}" + (f" — {hint}" if hint and not ok else ""))
    return ok


def doctor():
    """Preflight check: everything install.sh needs, checkable before any
    config exists. Shared between install.sh and `netquota doctor` so the
    user gets the same answer whether they ask before or after installing."""
    print(f"{c('1', 'NetQuota dependency check')}")
    all_ok = True
    all_ok &= _check("python3 (>= 3.10)", sys.version_info >= (3, 10), "install a newer Python 3")
    all_ok &= _check("nft (nftables)", shutil.which("nft") is not None, "install the nftables package")
    all_ok &= _check("vnstat", shutil.which("vnstat") is not None, "install the vnstat package")
    all_ok &= _check("ip (iproute2)", shutil.which("ip") is not None, "install the iproute2 package")
    init = service.detect()
    all_ok &= _check(f"init system: {init}", init != "unknown",
                      "no supported init system found (systemd/openrc/runit)")
    if shutil.which("nft"):
        r = subprocess.run(["nft", "list", "tables"], capture_output=True, text=True)
        all_ok &= _check("nftables kernel support", r.returncode == 0, r.stderr.strip())
    return all_ok


def main(argv=None):
    p = argparse.ArgumentParser(prog="netquota")
    sub = p.add_subparsers(dest="cmd")
    for x in ("status", "usage", "reset", "config", "service", "version", "doctor", "on", "off"):
        sub.add_parser(x)
    b = sub.add_parser("bypass")
    b.add_argument("duration", nargs="?")
    i = sub.add_parser("interface")
    i.add_argument("name", nargs="?")
    sub.add_parser("setup")
    sub.add_parser("daemon")
    a = p.parse_args(argv)

    if a.cmd == "version":
        print(__version__)
        return
    if a.cmd == "doctor":
        raise SystemExit(0 if doctor() else 1)

    app = App()
    if a.cmd in (None, "status"):
        app.status()
    elif a.cmd == "usage":
        app.usage()
    elif a.cmd == "reset":
        app.reset()
        print("Quota reset.")
    elif a.cmd == "bypass":
        if a.duration is None or a.duration == "off":
            app.bypass_off()
            print("Bypass disabled.")
        else:
            app.bypass(a.duration)
            print(f"Bypass enabled for {a.duration}.")
    elif a.cmd == "interface":
        app.interface(a.name)
    elif a.cmd == "setup":
        app.setup()
    elif a.cmd == "config":
        app.config()
    elif a.cmd == "service":
        app.service_status()
    elif a.cmd == "off":
        app.off()
        print("NetQuota enforcement disabled. Internet is unrestricted. Run 'netquota on' to resume.")
    elif a.cmd == "on":
        app.on()
        print("NetQuota enforcement enabled.")
    elif a.cmd == "daemon":
        app.daemon()
