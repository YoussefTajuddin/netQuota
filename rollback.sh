#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo ./rollback.sh <backup-dir>"; exit 1; }

BACKUP="${1:-}"
[[ -n "$BACKUP" && -d "$BACKUP" ]] || {
  echo "Usage: sudo ./rollback.sh /var/lib/netquota/migration-backup-TIMESTAMP"
  echo "Available backups:"
  ls -1d /var/lib/netquota/migration-backup-* 2>/dev/null || echo "  (none found)"
  exit 1
}

echo "Stopping the current install before restoring the backup..."
systemctl stop netquota.service 2>/dev/null || true
rc-service netquota stop 2>/dev/null || true
sv down netquota 2>/dev/null || true
nft delete table inet netquota 2>/dev/null || true

[[ -f "$BACKUP/config" ]] && cp -a "$BACKUP/config" /etc/netquota.conf && echo "Restored /etc/netquota.conf"
[[ -f "$BACKUP/state" ]] && install -d -m 0755 /var/lib/netquota && cp -a "$BACKUP/state" /var/lib/netquota/state.json && echo "Restored state.json"
[[ -d "$BACKUP/lib-netquota" ]] && rm -rf /usr/local/lib/netquota && cp -a "$BACKUP/lib-netquota" /usr/local/lib/netquota && echo "Restored /usr/local/lib/netquota"
[[ -f "$BACKUP/bin-netquota" ]] && cp -a "$BACKUP/bin-netquota" /usr/local/bin/netquota && chmod 0755 /usr/local/bin/netquota && echo "Restored /usr/local/bin/netquota"
[[ -f "$BACKUP/sbin-netquota" ]] && cp -a "$BACKUP/sbin-netquota" /usr/local/sbin/netquota && echo "Restored legacy /usr/local/sbin/netquota"

if [[ -f "$BACKUP/netquota.service" ]]; then
  cp -a "$BACKUP/netquota.service" /etc/systemd/system/netquota.service
  systemctl daemon-reload
  systemctl enable --now netquota.service
  echo "Restored and started the systemd unit."
elif [[ -f "$BACKUP/netquota.initd" ]]; then
  cp -a "$BACKUP/netquota.initd" /etc/init.d/netquota
  chmod 0755 /etc/init.d/netquota
  rc-update add netquota default
  rc-service netquota start
  echo "Restored and started the OpenRC service."
elif [[ -d "$BACKUP/runit-netquota" ]]; then
  rm -rf /etc/sv/netquota
  cp -a "$BACKUP/runit-netquota" /etc/sv/netquota
  ln -sf /etc/sv/netquota /var/service/netquota 2>/dev/null || true
  sv up netquota
  echo "Restored and started the runit service."
else
  echo "No service definition found in the backup — the files were restored but nothing was (re)started."
fi

echo "Rollback complete."
