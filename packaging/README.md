# Packaging

`install.sh`/`uninstall.sh` at the repo root are the source of truth and
work standalone on any distro with dnf/apt/pacman/xbps/apk — that's the
first-class, always-tested path. Everything in this directory is a thin,
**untested** wrapper around the same files (`netquota/`, `systemd/`,
`config/netquota.conf.example`, `packaging/common/netquota-wrapper`) for
distros where users expect a native package manager to work:

| Directory | Format | Init system |
|---|---|---|
| `debian/` | `.deb` (`dpkg-buildpackage`) | systemd |
| `arch/` | `PKGBUILD` (`makepkg`) | systemd |
| `fedora/` | `.spec` (`rpmbuild`) | systemd |

OpenRC (Alpine/Gentoo) and runit (Void) service definitions live at the
repo root in `openrc/` and `runit/` rather than here, since `install.sh`
uses them directly — there's no separate native-package step for them yet.

**Before adding a new format:** read [`../docs/PORTING.md`](../docs/PORTING.md).
The short version: every format here must install exactly
`packaging/common/netquota-wrapper` as the CLI and `systemd/netquota.service`
(or the OpenRC/runit equivalent) as the service — never a second copy of
either. Two divergent copies of the CLI wrapper is literally the bug that
shipped in 0.2.0 (see `CHANGELOG.md`); don't reintroduce it in a packaging
format.

**Status:** none of these three have been run through their respective
build tools yet. If you test one, please open a PR with the build/install
log.
