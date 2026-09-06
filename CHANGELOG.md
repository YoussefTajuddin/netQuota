# Changelog

## 0.3.0

- **Fixed:** the CLI wrapper installed by `install.sh` crashed on every
  command (`ModuleNotFoundError: 'netquota' is not a package`) because it
  ran `netquota.py` directly without `PYTHONPATH` set, colliding with the
  package of the same name. Only the systemd daemon (which set `PYTHONPATH`
  explicitly) worked. Fixed by installing a single shared wrapper
  (`packaging/common/netquota-wrapper`) that runs `python3 -m netquota`.
- **Fixed:** `install.sh`'s interface auto-detection never ran on a fresh
  install, because the shipped example config already contains an empty
  `INTERFACE=` line, which matched the "already set" check
  (`grep -q '^INTERFACE='`) even though the value was blank. The daemon
  then crash-looped on an empty interface. Fixed by checking for a
  non-empty value specifically.
- **Fixed:** `netquota version` (and any other command) required a valid
  `/etc/netquota.conf` to run at all, because `main()` unconditionally
  constructed `App()` before dispatching. `version` and the new `doctor`
  command no longer touch the config.
- **Fixed:** stopping the daemon (`systemctl stop`, a crash-restart, or a
  plain reboot) left the last-installed nftables rule in place indefinitely,
  since nft rules live in the kernel independently of the process that
  created them. Every supported init system now runs a stop hook
  (`ExecStopPost=`/`stop_post()`/`finish`) that removes `table inet
  netquota` whenever the daemon stops, for any reason.
- **Added:** `netquota off` / `netquota on` — pause enforcement entirely
  (Internet fully open) without uninstalling, then resume from the same
  usage counter.
- **Added:** `netquota doctor` — checks python3/nft/vnstat/init-system
  dependencies before you rely on the install.
- **Added:** OpenRC and runit support via a new `netquota/service.py`
  init-system abstraction, alongside systemd. Same daemon, different
  supervision.
- **Added:** the daemon now runs as a dedicated, unprivileged `netquota`
  system user with only `CAP_NET_ADMIN`, instead of full root. The systemd
  unit additionally sandboxes it (`ProtectSystem=strict`, `ProtectHome`,
  `PrivateTmp`, `NoNewPrivileges`).
- **Added:** new colored `netquota status` box with a live-updating quota
  bar and a commands reference printed at the bottom. Colors/icons are
  disabled automatically when output isn't a terminal, or when `NO_COLOR`
  is set.
- **Added:** `install.sh` is now interactive — lists Internet-facing
  interfaces and prompts for interface/quota-period/quota-size instead of
  only auto-detecting the interface.
- **Added:** `install.sh` backs up any previous install (config, state,
  service files, library dir, binary) before touching it, and cleans up
  anything that would conflict with a fresh install (stale library files,
  a legacy `/usr/local/sbin/netquota`, stray `__pycache__`).
  `rollback.sh` restores from that backup regardless of which init system
  or binary location it came from.
- **Added:** `uninstall.sh --purge` to also remove config/state (default
  keeps them); `uninstall.sh` only disables `firewalld` if `install.sh` is
  the one that enabled it.
- **Added:** packaging skeletons for `.deb`, Arch `PKGBUILD`, and Fedora
  `.spec` under `packaging/` (untested — see `packaging/README.md`), plus
  `docs/PORTING.md` for adding a new distro or init system.
- **Removed:** `install-and-test.sh`, which had silently diverged from
  `install.sh` (it contained the wrapper fix that `install.sh` was
  missing) — a second installer that can drift out of sync is worse than
  no second installer. `install.sh` is now the single source of truth.
- **Fixed:** `install.sh` created the dedicated `netquota` system user with a
  `useradd ... || adduser -S -D -H ...` fallback that assumed a failed
  `useradd` meant BusyBox's `adduser` was the only alternative. On Fedora
  (and most non-Alpine distros), `adduser` is a symlink to shadow-utils'
  own `useradd`, so the fallback fed it BusyBox-only flags (`-S -D -H`),
  which `useradd` rejected — aborting the whole script under `set -e`
  *after* it had already deleted the previous install's files, leaving
  neither the old nor the new install in place. The dialect is now chosen
  by the already-detected package manager (`apk` → BusyBox syntax,
  everything else → `useradd`) instead of probing which binary answers to
  `adduser`, and the group is now pre-created explicitly
  (`getent group ... || groupadd --system ...`) rather than relying on
  `useradd`'s implicit same-named-group behavior, which is a common,
  opaque failure point on a system with any leftover group of that name.
  User creation also now happens *before* any destructive cleanup step, so
  a failure there always leaves the previous install untouched instead of
  requiring a rollback.
- **Fixed:** `install.sh`'s interactive interface prompt displayed a
  numbered menu (`1) eno1`, `2) wlp0s20f0u10`) but only accepted a typed
  interface name — typing the number shown next to your choice (the
  obvious thing to do) silently became `INTERFACE=2` in the config, which
  isn't a real interface. The prompt now accepts either a menu number or a
  name, translates a number to the interface it labels, and re-prompts
  until the result is confirmed to exist via `ip link show`.
- **Fixed:** `/var/lib/netquota` was created `0750` (owner-and-group only),
  and `state.py`'s atomic write used `tempfile.mkstemp`'s default `0600`
  for the temporary file — which `os.replace()` then carried over to
  `state.json` on every save, regardless of the directory's permissions.
  Between the two, `netquota status` run as an ordinary user (as the
  README's own examples show it, with no `sudo`) failed with
  `PermissionError`, since neither the directory nor the file could be
  read by anyone but the `netquota` service user. `state.json` holds
  nothing sensitive — just quota numbers — so the directory is now `0755`
  and every write explicitly `chmod`s the file to `0644`; only the
  `netquota` user can write it, everyone can read it. `install.sh` also
  re-applies both permissions on every run so an existing install self-heals
  on upgrade, without needing `uninstall.sh` first.
- Friendlier `Config.from_file` errors (missing file / missing or empty
  `INTERFACE` / invalid value) instead of a bare `KeyError`/traceback.

## 0.2.0

- Refactored into separate config/state/network/firewall/vnStat/UI/application modules.
- Added IPv6 enforcement and bypass sets.
- Added interface discovery and interface change command.
- Added durable state with atomic + fsync writes.
- Added reboot-safe quota reconstruction from persisted usage.
- Added `usage`, `config`, `service`, `version`, and `bypass off` commands.
- Added unit tests and a manual integration test plan.
- Added architecture and porting documentation.
