# Architecture

NetQuota deliberately separates **enforcement**, **accounting**,
**presentation**, and **OS integration** so a distro/init-system port never
has to touch the first two.

## Components

- `netquota/app.py`: CLI and daemon orchestration.
- `netquota/firewall.py`: nftables only. Owns `table inet netquota`; never
  flushes the ruleset and never touches `table inet firewalld`.
- `netquota/state.py`: durable quota-period state. Writes are atomic and
  fsynced before rename.
- `netquota/network.py`: interface discovery, default-route discovery, and
  address discovery.
- `netquota/vnstat.py`: read-only statistics adapter. vnStat is **not** the
  quota authority — it's display-only.
- `netquota/ui.py`: terminal presentation only (the colored status box).
  Colors are disabled automatically when stdout isn't a terminal, or when
  `NO_COLOR` is set.
- `netquota/config.py`: configuration schema, defaults, and file parsing.
  Raises a friendly `SystemExit` (not a bare exception) for a missing file,
  a missing/empty `INTERFACE`, or an invalid value — this is deliberately a
  message the person running the command can act on without reading source.
- `netquota/service.py`: the **only** module that knows about
  systemd/OpenRC/runit. `detect()` picks one by looking for each init
  system's canonical marker (`/run/systemd/system`, `rc-service` +
  `openrc-run`, `sv` + `/etc/sv`) rather than the distro name, so it degrades
  gracefully on distros nobody has tested yet. `start`/`stop`/`enable`/
  `disable`/`is_active`/`status_text` are the only operations the rest of
  the codebase needs from an init system.
- `systemd/netquota.service`, `openrc/netquota.initd`, `runit/netquota/`:
  boot integration per init system. See "Adding another init system" below.

## Quota accounting model

The kernel nftables quota object is the live counter. The daemon samples it
every `POLL_SECONDS` and persists the delta into `state.json`. On
restart/reboot, nftables is recreated with `LIMIT_BYTES - persisted_used`,
so the quota does not reset merely because the machine rebooted.

The persisted value is the recovery point. A sudden power loss can lose at
most approximately one polling interval of newly observed traffic. Lower
`POLL_SECONDS` to reduce that window at the cost of more disk writes.

## Stopping always restores Internet access

Every supported init system runs a cleanup hook after the daemon process
exits, for any reason — a normal stop, `netquota off`, a crash followed by
`Restart=on-failure`, or a reboot:

| Init system | Hook |
|---|---|
| systemd | `ExecStopPost=-/usr/bin/nft delete table inet netquota` |
| OpenRC | `stop_post()` in `openrc/netquota.initd` |
| runit | `runit/netquota/finish` |

Without this, stopping the daemon process would leave the last-installed
nftables rule (including any active `drop`) in place indefinitely, since nft
rules live in the kernel independently of the userspace process that
created them. `netquota off` relies on exactly this behavior — it just calls
the init system's normal stop, and the hook does the rest.

## IPv4/IPv6

Both families are enforced in `inet netquota`. Private/ULA, link-local, and
multicast traffic are excluded by configurable networks/rules, so a global
IPv6 route is not an alternate path around the quota.

Before deployment on a network with unusual addressing, review
`LOCAL_IPV4`, `LOCAL_IPV6`, `EXCLUDE_IPV4`, and `EXCLUDE_IPV6`.

## Bypass

Bypass uses nftables timeout sets. It does not alter `used_bytes` and
therefore does not reset the quota. Current IPv4 and IPv6 addresses on the
selected interface are added with an nft timeout. The daemon removes
expired entries and stores the expiry in state for restart recovery.

## Security model

The daemon runs as a dedicated, unprivileged `netquota` system user
(created by `install.sh`) with only `CAP_NET_ADMIN` as an ambient
capability — the one nftables needs — instead of full root:

- **systemd**: `User=`/`Group=netquota`, `AmbientCapabilities=CAP_NET_ADMIN`,
  `CapabilityBoundingSet=CAP_NET_ADMIN`, `NoNewPrivileges=true`, plus
  `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`.
- **OpenRC/runit**: the daemon is launched through `setpriv --reuid=netquota
  --regid=netquota --ambient-caps=+net_admin ...`, which does the equivalent
  capability drop without systemd's unit directives. This depends on
  `setpriv` (util-linux); if it's unavailable, fall back to running the
  daemon as root and file an issue.

Interactive `sudo netquota ...` commands (status, bypass, reset, setup...)
run as your root shell as normal — only the long-running daemon is
deprivileged, since it's the far more exposed, longer-lived process.

## Adding another distribution

Avoid changing core modules for package-manager differences — see
[PORTING.md](PORTING.md). In short: dependency package names and service
enable/start semantics belong in `install.sh`'s per-`$PM` case statement or
under `packaging/`, never in `netquota/firewall.py` or `netquota/app.py`.

## Adding another init system

1. Add detection to `netquota/service.py:detect()` using that init system's
   own canonical marker — not a distro-name guess.
2. Implement the six dispatch branches in `start`/`stop`/`enable`/
   `disable`/`is_active`/`status_text`.
3. Add a service definition under a new top-level directory (mirroring
   `openrc/`, `runit/`) with a stop hook that runs
   `nft delete table inet netquota` — this is not optional; see "Stopping
   always restores Internet access" above.
4. Wire it into `install.sh`'s init-system case statements and
   `uninstall.sh`'s cleanup.
5. Add a `tests/test_service.py`-style unit test that mocks `_run` and
   asserts the right command is dispatched.

## Known limitations

- **One interface per install.** Aggregating quota across multiple
  interfaces (e.g. Wi-Fi + Ethernet) is not supported; each would need its
  own install/config.
- **IPv6 privacy addresses rotate.** A `bypass` window is keyed to the
  interface's *current* addresses at the time it's created. If the OS
  rotates its RFC 4941 temporary address mid-bypass, the new address isn't
  automatically covered.
- **No historical usage log.** Only the current period's usage is kept;
  there's no built-in export of past periods.
- **`nft`/`vnstat` output-format dependency.** `firewall.get_quota_used()`
  parses `nft -j list quota` JSON, and `vnstat.py` parses `vnstat
  --oneline`'s fixed column layout. A future nftables/vnStat release that
  changes either format could break parsing; there's no version pin today.
