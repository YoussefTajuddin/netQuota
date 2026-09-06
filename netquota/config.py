from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path("/etc/netquota.conf")

@dataclass
class Config:
    interface: str
    limit_bytes: int
    period_days: int
    state_file: str = "/var/lib/netquota/state.json"
    poll_seconds: float = 1.0
    local_ipv4: str = "192.168.0.0/16"
    local_ipv6: str = "fc00::/7"
    exclude_ipv4: str = "169.254.0.0/16"
    exclude_ipv6: str = "fe80::/10"

    @classmethod
    def from_file(cls, path=CONFIG_PATH):
        try:
            with open(path, encoding="utf-8") as f:
                raw_lines = f.readlines()
        except FileNotFoundError:
            raise SystemExit(
                f"Config file not found: {path}\n"
                f"Run 'sudo ./install.sh' (or 'sudo netquota setup') to create it."
            )
        values = {}
        for raw in raw_lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"')
        if not values.get("INTERFACE"):
            raise SystemExit(
                f"INTERFACE is missing or empty in {path}.\n"
                f"Run 'sudo netquota interface <name>' or 'sudo netquota setup' to set it."
            )
        try:
            return cls(
                interface=values["INTERFACE"],
                limit_bytes=int(values.get("LIMIT_BYTES", "50000000000")),
                period_days=int(values.get("PERIOD_DAYS", "28")),
                state_file=values.get("STATE_FILE", "/var/lib/netquota/state.json"),
                poll_seconds=float(values.get("POLL_SECONDS", "1")),
                local_ipv4=values.get("LOCAL_IPV4", "192.168.0.0/16"),
                local_ipv6=values.get("LOCAL_IPV6", "fc00::/7"),
                exclude_ipv4=values.get("EXCLUDE_IPV4", "169.254.0.0/16"),
                exclude_ipv6=values.get("EXCLUDE_IPV6", "fe80::/10"),
            )
        except ValueError as e:
            raise SystemExit(f"Invalid value in {path}: {e}")

    def validate(self):
        if not self.interface or any(c.isspace() for c in self.interface):
            raise ValueError("INTERFACE must be a valid interface name")
        if self.limit_bytes <= 0:
            raise ValueError("LIMIT_BYTES must be > 0")
        if self.period_days <= 0:
            raise ValueError("PERIOD_DAYS must be > 0")
        if self.poll_seconds <= 0:
            raise ValueError("POLL_SECONDS must be > 0")
