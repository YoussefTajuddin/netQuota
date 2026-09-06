# Contributing to NetQuota

Thanks for looking at the source instead of just filing an issue. This
project is small on purpose — please read this before your first PR.

## Before you start

- Skim [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module
  boundaries. The short version: `netquota/*.py` never contains
  distro-name or init-system-name checks — those live in
  `netquota/service.py` (init system) or `install.sh`/`packaging/`
  (distro/package manager).
- If you're porting to a new distro or init system, read
  [docs/PORTING.md](docs/PORTING.md) first — it's a checklist, not
  just prose.
- Check `CHANGELOG.md` for recent history before assuming something is a
  bug; several past issues (a broken CLI wrapper, an interface
  auto-detection that never ran) are documented there with root causes.

## Setup

No build step — it's Python + shell.

```bash
git clone <this repo>
cd netquota
python3 -m unittest discover -s tests -v
```

You don't need root or a real network interface to run the unit tests —
they mock every `subprocess` call to `nft`/`vnstat`/`ip`.

## Workflow

1. Change one module.
2. Add or adjust unit tests in `tests/` for that module. If you add a new
   module, add a matching `tests/test_<module>.py`.
3. Run the full test suite:
   ```bash
   python3 -m unittest discover -s tests -v
   ./tests/run_all.sh
   ```
4. If your change touches firewall rules, the daemon loop, or a service
   file, also run the manual integration plan in
   [docs/TESTING.md](docs/TESTING.md) — ideally on a VM, since it
   intentionally blocks and unblocks Internet access.
5. Update `CHANGELOG.md` under an `## Unreleased` heading (or the next
   version, if you know it) — one line per user-visible change, in the
   same "Fixed:"/"Added:"/"Removed:" style as existing entries.

## Style / review checklist

Things reviewers (including CI, via `tests/run_all.sh`) will check:

- **No hardcoded developer-machine values.** No specific interface names,
  IP ranges, or absolute paths outside the documented config keys.
  `tests/run_all.sh` section 5 greps for this.
- **`bash -n` clean** on any shell script you touch or add.
- **One CLI wrapper, one systemd unit.** If you're touching install/package
  logic, it must install `packaging/common/netquota-wrapper` and
  `systemd/netquota.service` (or the OpenRC/runit equivalents) — never a
  second copy embedded elsewhere. See `packaging/README.md`.
- **Stop hooks stay intact.** Any change to a service definition
  (`systemd/`, `openrc/`, `runit/`) must keep the
  `nft delete table inet netquota` cleanup that runs on every stop — this
  is what makes `netquota off` and a plain service stop both correctly
  restore Internet access (see docs/ARCHITECTURE.md).
- **Privilege stays minimal.** The daemon should keep running as the
  unprivileged `netquota` user with only `CAP_NET_ADMIN` — don't add code
  paths that assume it has full root.
- **New commands update `netquota/ui.py`'s `COMMANDS` list** if they're
  meant to be user-facing, so `netquota status`'s command reference stays
  accurate.

## Reporting a bug

Please include:
- Distro + version, init system (`systemctl --version` /
  `openrc --version` / `sv --version`, whichever applies).
- `netquota doctor` output.
- The exact command and its output (or `journalctl -u netquota -e` /
  the OpenRC or runit equivalent).

## What NOT to send a PR for

- New enforcement mechanisms competing with nftables (this project is
  intentionally nftables-only — see docs/ARCHITECTURE.md).
- Per-application or per-device quotas — out of scope; NetQuota enforces
  one quota per interface by design.
- Anything that requires the daemon to run as full root when
  `CAP_NET_ADMIN` alone would do.
