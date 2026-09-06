# NetQuota

A small Linux CLI that enforces a combined **download + upload Internet
quota** on one network interface, using nftables for enforcement and vnStat
for display statistics. When the quota runs out before the period ends,
NetQuota blocks that interface's Internet traffic (IPv4 **and** IPv6) until
the next period — or until you temporarily lift it with `bypass`.

> **Status: 0.3.0 development release.** The OpenRC and runit service files
> are believed correct but have only been syntax-checked, not run on a real
> Alpine/Void/Gentoo machine — please open an issue (or a PR) with results
> from your distro.

```
╭────────────────────────────────────────────────╮
│                 INTERNET QUOTA                  │
├────────────────────────────────────────────────┤
│    QUOTA                                       │
│    █████░░░░░░░░░░░░░░░░░░░░░░░░░ 18.40%       │
│                                                │
│    Used                9.20 GB                 │
│    Remaining           40.80 GB                │
│    Limit               50.00 GB                │
├────────────────────────────────────────────────┤
│    STATUS                                      │
│    ● Internet   ENABLED                        │
│    ● Service    RUNNING                        │
│    ● Bypass     OFF                            │
├────────────────────────────────────────────────┤
│    COMMANDS                                    │
│    netquota bypass 2h                          │
│      Temporarily lift the block                │
│    netquota on / off                           │
│      Enable/disable enforcement entirely       │
│    ... (full list below the box)               │
╰────────────────────────────────────────────────╯
```
(colors and a VNSTAT panel appear in a real terminal; shown here as plain text)

## Features

- Combined RX + TX quota, enforced for both IPv4 and IPv6 in one nftables table.
- Configurable quota size and period (interactive at install time, or edit `/etc/netquota.conf`).
- Survives daemon restart and reboot — usage is persisted, not reset.
- Temporary bypass (`netquota bypass 2h`) that doesn't touch the usage counter.
- `netquota off` / `netquota on` — pause enforcement entirely (Internet fully open) without uninstalling, and resume later from the same usage counter.
- Runs as a dedicated, unprivileged `netquota` system user with only `CAP_NET_ADMIN` — never full root.
- Works under **systemd**, **OpenRC**, or **runit** — the same daemon, different supervision.
- `netquota doctor` checks all required dependencies before you rely on it.
- Full backup before any install/upgrade, plus `rollback.sh` to undo it, and `uninstall.sh --purge` to remove everything including config/state.

## Commands

```text
netquota status                  Colored status screen (see above)
netquota usage                   Plain-text usage numbers (scriptable)
netquota bypass <30m|2h|1d>      Temporarily lift the block
netquota bypass off              Cancel an active bypass now
netquota reset                   Reset usage and start a new period
netquota on / off                Enable/disable enforcement entirely
netquota interface [name]        Show/change the monitored interface
netquota setup                   Interactive interface/quota/period wizard
netquota config                  Print the config file
netquota service                 Underlying service status (systemd/OpenRC/runit)
netquota doctor                  Check required dependencies
netquota version
```

Set `NO_COLOR=1` (or pipe the output to a file) to get plain text instead of
the colored box — `netquota status` detects non-terminal output automatically.

## Install

```bash
sudo ./install.sh
```

This:

1. Detects your package manager (`dnf`/`apt-get`/`pacman`/`xbps-install`/`apk`) and installs `python3`, `nftables`, `vnstat`, `iproute2`, and `util-linux`.
2. Detects your init system (systemd / OpenRC / runit).
3. **Backs up** any previous NetQuota install (config, state, service files, library dir) to `/var/lib/netquota/migration-backup-<timestamp>/`, and removes anything that would otherwise conflict with a clean install (stale library files, an old legacy binary path, `__pycache__`).
4. Creates a dedicated `netquota` system user (no shell, no home) that the daemon runs as.
5. Lists the network interfaces that can reach the Internet and asks you to pick one, then asks for the quota period (days) and size (GB).
6. Installs and starts the service.
7. Runs `netquota version` at the end to confirm the install actually works before declaring success.

Run `sudo ./install.sh` again any time to change interface/quota/period
interactively, or edit `/etc/netquota.conf` directly and restart the service
(`netquota` doesn't restart itself when you hand-edit the file).

### Uninstall / rollback

```bash
sudo ./uninstall.sh            # removes NetQuota; keeps /etc/netquota.conf and usage history
sudo ./uninstall.sh --purge    # removes everything, including config and state
sudo ./rollback.sh /var/lib/netquota/migration-backup-<timestamp>   # undo the last install
```

`uninstall.sh` only disables `firewalld` if `install.sh` is the one that
turned it on in the first place (tracked in a marker file) — it never
disables something you already had running. This isolation goal — leave
everything else on the system exactly as it was found — is central to the
design; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Configuration

`/etc/netquota.conf` is deliberately simple. See `config/netquota.conf.example`.

| Key | Meaning |
|---|---|
| `INTERFACE` | Interface to monitor/protect. |
| `LIMIT_BYTES` | Decimal bytes. `50000000000` = 50 GB. |
| `PERIOD_DAYS` | Quota period length. |
| `POLL_SECONDS` | How often usage is persisted to disk (default 1s). |
| `LOCAL_IPV4` / `LOCAL_IPV6` | Networks that don't count against the quota (your LAN). |
| `EXCLUDE_IPV4` / `EXCLUDE_IPV6` | Link-local/automatic-local traffic exclusions. |

**If your LAN doesn't use `192.168.0.0/16`** (e.g. it's `10.0.0.0/8`), update
`LOCAL_IPV4` accordingly, or LAN traffic will be counted as Internet usage.

## Persistence and reboot behavior

The live nftables quota counter is not persistent across a reboot. NetQuota
persists observed usage in `/var/lib/netquota/state.json` and recreates the
nftables quota with the remaining bytes on every start. A sudden power
failure can lose at most about one `POLL_SECONDS` interval of unsaved
traffic; lower it for a smaller window at the cost of more disk writes.

Whatever stops the daemon — `netquota off`, a plain `systemctl stop`, a
crash-and-restart — always removes the nftables table first (via
`ExecStopPost=`/`stop_post()`/`finish`, depending on your init system), so a
stopped service never leaves a stale block in place.

## Security model

The daemon runs as the unprivileged `netquota` user with only
`CAP_NET_ADMIN` ambient — the one capability nftables needs — rather than
full root, and the systemd unit additionally sandboxes it with
`ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, and
`NoNewPrivileges=true`. `sudo netquota ...` commands (status, bypass, reset,
etc.) run as your root shell as normal — only the long-running daemon is
deprivileged.

NetQuota only ever touches `table inet netquota` in nftables; it never
flushes the ruleset and never modifies `firewalld`'s own table.

## IPv6 notes

IPv6 traffic is enforced in the same `inet` table, so a global IPv6 route
can't silently bypass the quota. ULA, link-local, and multicast are excluded
by default. Networks with non-standard local IPv6 addressing should adjust
`LOCAL_IPV6`/`EXCLUDE_IPV6`.

IPv6 privacy-extension addresses (RFC 4941) rotate periodically — a
`bypass` window keyed to "the current address" can stop matching if the OS
rotates addresses mid-bypass. This is a known limitation; see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#known-limitations).

## Development

```bash
python3 -m unittest discover -s tests -v   # unit tests (no root/host state needed)
./tests/run_all.sh                          # full suite: unit tests, syntax, doctor checks, read-only host diagnostics
sudo ./tests/run_all.sh --live              # also exercises real firewall/service state — see docs/TESTING.md
python3 -m netquota --help
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module boundaries
and [docs/PORTING.md](docs/PORTING.md) for adding a new distro or init
system — that's a packaging-layer change, not a core-module change.

## Packaging

`install.sh`/`uninstall.sh` are the source of truth and work standalone on
any supported distro. `packaging/` has thin wrappers for native package
managers:

```
packaging/debian/    → .deb (Debian/Ubuntu, systemd)
packaging/arch/       → PKGBUILD (Arch, systemd)
packaging/fedora/     → .spec (Fedora/RHEL, systemd)
openrc/               → OpenRC init script (Alpine, Gentoo, Artix-OpenRC)
runit/                → runit run/finish scripts (Void, Artix-runit)
```

See [docs/PORTING.md](docs/PORTING.md) before adding a new one.
