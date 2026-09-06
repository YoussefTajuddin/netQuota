#!/usr/bin/env bash
set -euo pipefail

PREFIX=/usr/local/lib/netquota
BIN=/usr/local/bin/netquota
LEGACY_BIN=/usr/local/sbin/netquota
CONF=/etc/netquota.conf
STATE=/var/lib/netquota
UNIT=/etc/systemd/system/netquota.service
OPENRC_INITD=/etc/init.d/netquota
RUNIT_DIR=/etc/sv/netquota
SVC_USER=netquota
FIREWALLD_MARKER="$STATE/.we-enabled-firewalld"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./install.sh"
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Package manager + dependencies
# ---------------------------------------------------------------------------
if command -v dnf >/dev/null; then PM=dnf
elif command -v apt-get >/dev/null; then PM=apt-get
elif command -v pacman >/dev/null; then PM=pacman
elif command -v xbps-install >/dev/null; then PM=xbps
elif command -v apk >/dev/null; then PM=apk
else
  echo "Unsupported package manager. Install python3, nftables, vnstat, iproute2 (and util-linux for setpriv) manually, then re-run this script."
  exit 1
fi

echo "Installing dependencies via $PM..."
case "$PM" in
  dnf)    dnf install -y python3 nftables firewalld vnstat iproute util-linux ;;
  apt-get) apt-get update && apt-get install -y python3 nftables firewalld vnstat iproute2 util-linux ;;
  pacman) pacman -Sy --needed --noconfirm python nftables firewalld vnstat iproute util-linux ;;
  xbps)   xbps-install -Sy python3 nftables vnstat iproute2 util-linux ;;
  apk)    apk add --no-cache python3 nftables vnstat iproute2 util-linux openrc ;;
esac

# ---------------------------------------------------------------------------
# 2. Init system detection
# ---------------------------------------------------------------------------
if [[ -d /run/systemd/system ]]; then
  INIT=systemd
elif command -v rc-service >/dev/null && command -v openrc-run >/dev/null; then
  INIT=openrc
elif command -v sv >/dev/null && [[ -d /etc/sv || -n "$(command -v runsvdir || true)" ]]; then
  INIT=runit
else
  echo "Could not detect systemd, OpenRC, or runit. NetQuota needs one of these to supervise the daemon."
  exit 1
fi
echo "Detected init system: $INIT"

install -d -m 0755 "$STATE"

# ---------------------------------------------------------------------------
# 3. Back up anything from a previous install before touching it
# ---------------------------------------------------------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$STATE/migration-backup-$STAMP"
NEEDS_BACKUP=0
for f in "$CONF" "$STATE/state.json" "$UNIT" "$OPENRC_INITD" "$RUNIT_DIR" "$BIN" "$LEGACY_BIN" "$PREFIX"; do
  [[ -e "$f" ]] && NEEDS_BACKUP=1
done

if [[ "$NEEDS_BACKUP" -eq 1 ]]; then
  mkdir -p "$BACKUP"
  [[ -f "$CONF" ]] && cp -a "$CONF" "$BACKUP/config"
  [[ -f "$STATE/state.json" ]] && cp -a "$STATE/state.json" "$BACKUP/state"
  [[ -f "$UNIT" ]] && cp -a "$UNIT" "$BACKUP/netquota.service"
  [[ -f "$OPENRC_INITD" ]] && cp -a "$OPENRC_INITD" "$BACKUP/netquota.initd"
  [[ -d "$RUNIT_DIR" ]] && cp -a "$RUNIT_DIR" "$BACKUP/runit-netquota"
  [[ -f "$BIN" ]] && cp -a "$BIN" "$BACKUP/bin-netquota"
  [[ -f "$LEGACY_BIN" ]] && cp -a "$LEGACY_BIN" "$BACKUP/sbin-netquota"
  [[ -d "$PREFIX" ]] && cp -a "$PREFIX" "$BACKUP/lib-netquota"
  nft list table inet netquota >"$BACKUP/nft-netquota.rules" 2>/dev/null || true
  printf 'Existing NetQuota files found — backed up to: %s\n' "$BACKUP"
  printf '(Restore later with: sudo ./rollback.sh %s)\n\n' "$BACKUP"
fi

# ---------------------------------------------------------------------------
# 4. Dedicated unprivileged system user (CAP_NET_ADMIN only, no shell/home).
# ---------------------------------------------------------------------------
if ! id "$SVC_USER" >/dev/null 2>&1; then
  case "$PM" in
    apk)
      adduser -S -D -H -s /sbin/nologin "$SVC_USER"
      ;;
    *)
      # Pre-create the group explicitly rather than relying on useradd's
      # implicit "create a same-named private group" behavior — a leftover
      # group from an earlier partial/failed install is a common, opaque
      # cause of useradd refusing to proceed.
      getent group "$SVC_USER" >/dev/null || groupadd --system "$SVC_USER"
      useradd --system --no-create-home --gid "$SVC_USER" --shell /usr/sbin/nologin "$SVC_USER"
      ;;
  esac
  echo "Created system user: $SVC_USER"
fi

# ---------------------------------------------------------------------------
# 5. Stop whatever is currently running, then clean up conflicting files.
# ---------------------------------------------------------------------------
systemctl stop netquota.service 2>/dev/null || true
rc-service netquota stop 2>/dev/null || true
sv down netquota 2>/dev/null || true
nft delete table inet netquota 2>/dev/null || true

rm -rf "$PREFIX"
find "$ROOT_DIR/netquota" -name '__pycache__' -type d -prune -exec rm -rf {} +
[[ -e "$LEGACY_BIN" ]] && rm -f "$LEGACY_BIN" && echo "Removed conflicting legacy binary: $LEGACY_BIN"
[[ -e "$BIN" ]] && rm -f "$BIN"

# ---------------------------------------------------------------------------
# 6. Install files
# ---------------------------------------------------------------------------
install -d -m 0755 "$PREFIX"
cp -a "$ROOT_DIR/netquota/." "$PREFIX/"
find "$PREFIX" -name '__pycache__' -type d -prune -exec rm -rf {} +

install -m 0755 "$ROOT_DIR/packaging/common/netquota-wrapper" "$BIN"

if [[ ! -e "$CONF" ]]; then
  cp "$ROOT_DIR/config/netquota.conf.example" "$CONF"
fi

install -d -m 0755 -o "$SVC_USER" -g "$SVC_USER" "$STATE"
# Belt-and-braces: `install -d` on some systems only applies the mode when
# it creates the directory, not when it already exists (an upgrade from an
# install that used the old, too-strict 0750). Force it every run.
chmod 0755 "$STATE"
chown "$SVC_USER:$SVC_USER" "$STATE"
[[ -f "$STATE/state.json" ]] && chown "$SVC_USER:$SVC_USER" "$STATE/state.json" && chmod 0644 "$STATE/state.json"

case "$INIT" in
  systemd)
    install -m 0644 "$ROOT_DIR/systemd/netquota.service" "$UNIT"
    systemctl daemon-reload
    ;;
  openrc)
    install -m 0755 "$ROOT_DIR/openrc/netquota.initd" "$OPENRC_INITD"
    ;;
  runit)
    rm -rf "$RUNIT_DIR"
    install -d -m 0755 "$RUNIT_DIR"
    install -m 0755 "$ROOT_DIR/runit/netquota/run" "$RUNIT_DIR/run"
    install -m 0755 "$ROOT_DIR/runit/netquota/finish" "$RUNIT_DIR/finish"
    ;;
esac

# ---------------------------------------------------------------------------
# 7. firewalld: only start it if it wasn't already running, and remember
#    that decision so uninstall.sh can put it back exactly as it found it.
# ---------------------------------------------------------------------------
if command -v firewalld >/dev/null || command -v firewall-cmd >/dev/null; then
  if ! systemctl is-active --quiet firewalld 2>/dev/null; then
    systemctl enable --now firewalld 2>/dev/null && touch "$FIREWALLD_MARKER"
  fi
fi

# ---------------------------------------------------------------------------
# 8. Interactive setup: interface, quota period, quota size
# ---------------------------------------------------------------------------
echo
echo "== NetQuota setup =="
echo "Interfaces that can reach the Internet:"
mapfile -t IFACES < <(ip -o link show | awk -F': ' '{print $2}' | grep -vE '^(lo|docker|veth|br-|virbr|tun|tap)')
if [[ "${#IFACES[@]}" -eq 0 ]]; then
  echo "  (none auto-detected — 'ip link show' to list them yourself)"
fi
default_if="$(ip -4 -o route show default 2>/dev/null | awk 'NR==1{print $5}')"
i=1
for name in "${IFACES[@]}"; do
  state="$(cat /sys/class/net/"$name"/operstate 2>/dev/null || echo unknown)"
  marker=" "
  [[ "$name" == "$default_if" ]] && marker="*"
  printf '  %s %d) %-12s [%s]\n' "$marker" "$i" "$name" "$state"
  i=$((i + 1))
done

read -rp "Interface to monitor — type a number from the list, or a name [${default_if:-enp0s3}]: " reply
reply="${reply:-${default_if:-enp0s3}}"
if [[ "$reply" =~ ^[0-9]+$ ]] && (( reply >= 1 && reply <= ${#IFACES[@]} )); then
  chosen_if="${IFACES[$((reply - 1))]}"
else
  chosen_if="$reply"
fi
while ! ip link show "$chosen_if" >/dev/null 2>&1; do
  read -rp "No such interface '$chosen_if'. Enter a number from the list above, or a valid interface name: " reply
  if [[ "$reply" =~ ^[0-9]+$ ]] && (( reply >= 1 && reply <= ${#IFACES[@]} )); then
    chosen_if="${IFACES[$((reply - 1))]}"
  else
    chosen_if="$reply"
  fi
done

read -rp "Quota period in days [28]: " period_days
period_days="${period_days:-28}"

read -rp "Quota limit in GB [50]: " limit_gb
limit_gb="${limit_gb:-50}"
limit_bytes=$(( ${limit_gb%.*} * 1000000000 ))

sed -i \
  -e "s/^INTERFACE=.*/INTERFACE=$chosen_if/" \
  -e "s/^LIMIT_BYTES=.*/LIMIT_BYTES=$limit_bytes/" \
  -e "s/^PERIOD_DAYS=.*/PERIOD_DAYS=$period_days/" \
  "$CONF"
# In case the example file didn't already have one of these keys.
grep -q '^INTERFACE=' "$CONF"   || echo "INTERFACE=$chosen_if" >>"$CONF"
grep -q '^LIMIT_BYTES=' "$CONF" || echo "LIMIT_BYTES=$limit_bytes" >>"$CONF"
grep -q '^PERIOD_DAYS=' "$CONF" || echo "PERIOD_DAYS=$period_days" >>"$CONF"

case "$INIT" in
  systemd) systemctl enable --now netquota.service ;;
  openrc)  rc-update add netquota default && rc-service netquota start ;;
  runit)
    mkdir -p /var/service 2>/dev/null || true
    ln -sf "$RUNIT_DIR" /var/service/netquota
    sv up netquota
    ;;
esac

# ---------------------------------------------------------------------------
# 9. Verify the CLI actually works before declaring success
# ---------------------------------------------------------------------------
if "$BIN" version >/dev/null 2>&1; then
  echo
  echo "Installed NetQuota $("$BIN" version) — monitoring $chosen_if, ${limit_gb}GB / ${period_days} days."
  echo "Run: netquota status"
  echo "Logs (systemd): journalctl -u netquota -f"
  if [[ "$NEEDS_BACKUP" -eq 1 ]]; then
    echo "Uninstall: sudo ./uninstall.sh   Rollback: sudo ./rollback.sh $BACKUP"
  else
    echo "Uninstall: sudo ./uninstall.sh"
  fi
else
  echo "Installation finished but 'netquota version' failed — please check the output above and open an issue." >&2
  exit 1
fi
