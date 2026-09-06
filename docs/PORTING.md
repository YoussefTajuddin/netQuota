# Porting NetQuota to a new distro or init system

NetQuota's core (`netquota/*.py`) is distro-agnostic: it shells out to
`nft`, `vnstat`, and `ip`, all of which behave the same everywhere. Porting
to a new environment should only ever touch the installer and the
packaging/service layer — never the core modules.

## Adding a new Linux distribution

You almost certainly don't need a new packaging format — `install.sh`
already works standalone anywhere with one of the package managers it knows
about. To add a new one:

1. Open `install.sh` and find the package-manager detection block near the
   top (`if command -v dnf ...`).
2. Add a `elif command -v <your-pm> >/dev/null; then PM=<name>` branch.
3. Add a matching case in the `case "$PM" in ... esac` dependency-install
   block with that distro's package names for: `python3` (>=3.10), `nft`
   (nftables), `vnstat`, `iproute2`, and `util-linux` (for `setpriv`, needed
   on OpenRC/runit).
4. If the distro's default init system isn't already handled by
   `netquota/service.py:detect()` (systemd/OpenRC/runit cover the large
   majority), see the next section first.
5. Run `sudo ./tests/run_all.sh` on that distro and open a PR with the
   output — that's the acceptance bar, since this project can't test every
   distro in CI.

Only reach for a native package (`packaging/debian`, `packaging/arch`,
`packaging/fedora`) if your distro's users specifically expect `apt
install`/`pacman -S`/`dnf install` to work without cloning the repo. Those
are thin wrappers that call the same `install.sh` logic (or reimplement the
handful of `cp`/`useradd`/service-enable steps needed for that packaging
format) — they should never duplicate business logic from `netquota/*.py`.

## Adding a new init system

systemd, OpenRC, and runit are supported today. To add a fourth
(s6, dinit, SysV init scripts, ...):

1. **Detection** — add a branch to `netquota/service.py:detect()` using
   that init system's own canonical marker (a directory, a binary that only
   it ships, not a distro-name guess). Order matters: put more specific
   checks before more general ones.
2. **Dispatch** — implement the new init's branch in each of `start`,
   `stop`, `enable`, `disable`, `is_active`, `status_text`.
3. **Service definition** — add a new top-level directory (e.g. `s6/`)
   with whatever files that init system needs to supervise
   `python3 -m netquota daemon` as a foreground process. Two requirements
   that aren't optional:
   - It must run as the unprivileged `netquota` user with `CAP_NET_ADMIN`
     (see `runit/netquota/run` for the `setpriv` invocation to copy).
   - It must run `nft delete table inet netquota` after the daemon stops,
     for *any* reason — this is what makes `netquota off` and a plain
     service stop both correctly restore Internet access. See
     `runit/netquota/finish` or `openrc/netquota.initd`'s `stop_post()`.
4. **Installer wiring** — add the new init to `install.sh`'s detection
   block and its two `case "$INIT" in ... esac` blocks (service-file
   install, and enable+start), and to `uninstall.sh`'s cleanup block.
5. **Tests** — add a `tests/test_service.py`-style block that mocks
   `service._run` and asserts the right command is dispatched, plus
   `bash -n` on any new shell/init script.

## What NOT to do

- Don't add `if distro == "fedora"` branches inside `netquota/*.py`. If a
  core module needs to know about the OS, that's a sign the abstraction
  (usually `service.py`, sometimes `network.py`) needs a new case, not a
  special-cased core module.
- Don't skip the stop-hook requirement in step 3 above. It's the difference
  between `netquota off` actually opening up the Internet and just quietly
  doing nothing.
- Don't hardcode a developer machine's interface name, IP range, or
  distro-specific path anywhere under `netquota/`, `config/`, or `install.sh`
  — `tests/run_all.sh` section 5 greps for exactly this and will fail your
  PR's CI run.
