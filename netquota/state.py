import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

@dataclass
class State:
    period_start: str
    period_end: str
    used_bytes: int = 0
    blocked: bool = False
    bypass_until: str | None = None

    @classmethod
    def new(cls, days: int, now=None):
        now = now or datetime.now(timezone.utc)
        return cls(now.isoformat(), (now + timedelta(days=days)).isoformat())

    @classmethod
    def load(cls, path, days):
        p = Path(path)
        if not p.exists():
            return cls.new(days)
        with p.open(encoding="utf-8") as f:
            d = json.load(f)
        return cls(
            period_start=d["period_start"], period_end=d["period_end"],
            used_bytes=int(d.get("used_bytes", 0)),
            blocked=bool(d.get("blocked", False)),
            bypass_until=d.get("bypass_until"),
        )

    def save(self, path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", dir=p.parent)
        try:
            # mkstemp creates the file 0600 regardless of umask. state.json
            # holds nothing sensitive (just quota numbers), and `netquota
            # status` is meant to be run by an ordinary user without sudo —
            # os.replace() below takes the *new* inode's permissions, so
            # without this every write would silently reset the file back
            # to owner-only and lock everyone else out of `status`.
            os.fchmod(fd, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.__dict__, f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def expired(self, now=None):
        now = now or datetime.now(timezone.utc)
        return now >= datetime.fromisoformat(self.period_end)
