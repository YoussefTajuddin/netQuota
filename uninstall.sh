#!/usr/bin/env bash
set -euo pipefail

PREFIX=/usr/local/lib/netquota
BIN=/usr/local/bin/netquota
CONF=/etc/netquota.conf
STATE=/var/lib/netquota
UNIT=/etc/systemd/system/netquota.service
OPENRC_INITD=/etc/init.d/netquota
RUNIT_DIR=/etc/sv/netquota
SVC_USER=netquota
FIREWALLD_MARKER="$STATE/.we-enabled-firewalld"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./uninstall.sh"
  exit 1
fi

KEEP_DATA=1
if [[ "${1:-}" == "--purge" ]]; then
  KEEP_DATA=0
fi

# ---------------------------------------------------------------------------
# 1. Stop + disable + remove the service, whichever init system owns it.
#    Every stop path (systemd ExecStopPost / OpenRC stop_post / runit
#    finish) already removes the nftables table, so Internet access is
#    restored the moment the daemon actually stops.
# ---------------------------------------------------------------------------
if [[ -f "$UNIT" ]]; then
  systemctl disable --now netquota.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl daemon-reload 2>/dev/null || true
fi

if [[ -f "$OPENRC_INITD" ]]; then
  rc-service netquota stop 2>/dev/null || true
  rc-update del netquota default 2>/dev/null || true
  rm -f "$OPENRC_INITD"
fi

if [[ -d "$RUNIT_DIR" ]]; then
  sv down netquota 2>/dev/null || true
  rm -f /var/service/netquota /run/runit/service/netquota /etc/runit/runsvdir/default/netquota 2>/dev/null || true
  rm -rf "$RUNIT_DIR"
fi

# Belt-and-braces: remove the table directly in case none of the stop hooks
# above ran (e.g. the service file was already missing).
nft delete table inet netquota 2>/dev/null || true

# ---------------------------------------------------------------------------
# 2. Remove installed files
# ---------------------------------------------------------------------------
rm -rf "$PREFIX"
rm -f "$BIN"

# ---------------------------------------------------------------------------
# 3. firewalld: only touch it if install.sh is the one that turned it on.
#    Isolation goal: uninstalling NetQuota should leave every *other*
#    system-level setting exactly as it was found.
# ---------------------------------------------------------------------------
if [[ -f "$FIREWALLD_MARKER" ]]; then
  systemctl disable --now firewalld 2>/dev/null || true
  echo "Disabled firewalld (it was off before NetQuota enabled it)."
fi

# ---------------------------------------------------------------------------
# 4. Dedicated service user
# ---------------------------------------------------------------------------
if id "$SVC_USER" >/dev/null 2>&1; then
  userdel "$SVC_USER" 2>/dev/null || deluser "$SVC_USER" 2>/dev/null || true
fi
getent group "$SVC_USER" >/dev/null 2>&1 && groupdel "$SVC_USER" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 5. Config/state: kept by default so a re-install (or `git pull` + re-run
#    of install.sh) picks up where you left off. --purge removes them too.
# ---------------------------------------------------------------------------
if [[ "$KEEP_DATA" -eq 0 ]]; then
  rm -f "$CONF"
  rm -rf "$STATE"
  echo "NetQuota removed completely, including /etc/netquota.conf and $STATE."
else
  rm -f "$FIREWALLD_MARKER"
  echo "NetQuota removed. $CONF and $STATE were kept (run with --purge to delete them too)."
fi
