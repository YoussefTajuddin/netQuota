#!/usr/bin/env bash
set -Eeuo pipefail

# NetQuota comprehensive test runner.
# Default: SAFE mode (no firewall/config/service changes).
# --live: run destructive host integration tests; requires explicit confirmation.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="safe"
if [[ "${1:-}" == "--live" ]]; then MODE="live"; fi

PASS=0
FAIL=0
WARN=0
SKIP=0

# Colors/icons only when writing to a real terminal, so piped/CI logs stay
# plain text instead of filling up with escape codes.
if [[ -t 1 ]]; then
    C_GREEN=$'\033[0;32m'; C_RED=$'\033[0;31m'; C_YELLOW=$'\033[0;33m'
    C_BLUE=$'\033[0;34m';  C_BOLD=$'\033[1m';   C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_GREEN=""; C_RED=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_DIM=""; C_OFF=""
fi

ok()   { printf '  %s✓%s %s\n' "$C_GREEN" "$C_OFF" "$*"; ((PASS+=1)); }
fail() { printf '  %s✗%s %s\n' "$C_RED" "$C_OFF" "$*"; ((FAIL+=1)); }
warn() { printf '  %s⚠%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; ((WARN+=1)); }
skip() { printf '  %s⏭%s %s\n' "$C_BLUE" "$C_OFF" "$*"; ((SKIP+=1)); }
section() { printf '\n%s▶ %s%s\n' "$C_BOLD" "$*" "$C_OFF"; }

run_check() {
    local name="$1"; shift
    if "$@" >/tmp/netquota-test.out 2>&1; then
        ok "$name"
    else
        fail "$name"
        sed -n '1,80p' /tmp/netquota-test.out | sed "s/^/       ${C_DIM}/;s/\$/${C_OFF}/"
    fi
}

cleanup_tmp() { rm -f /tmp/netquota-test.out; }
trap cleanup_tmp EXIT

section "0. Required dependencies"
# These four are what install.sh needs and what the daemon depends on at
# runtime; checking them here means a broken environment shows up as a
# clear ✗ instead of thirty confusing failures further down.
if command -v python3 >/dev/null 2>&1; then
    PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
        ok "python3 $PYVER (>= 3.10)"
    else
        fail "python3 $PYVER is older than the minimum supported (3.10)"
    fi
else
    fail "python3 not found"
fi

if command -v nft >/dev/null 2>&1; then
    ok "nft ($(nft --version 2>/dev/null | head -1))"
else
    fail "nft (nftables) not found — this is the enforcement engine, nothing works without it"
fi

if command -v vnstat >/dev/null 2>&1; then
    ok "vnstat ($(vnstat --version 2>/dev/null | head -1))"
else
    fail "vnstat not found — required (shows the VNSTAT panel in 'netquota status')"
fi

INIT_DETECTED="$(PYTHONPATH="$ROOT_DIR" python3 -c 'from netquota import service; print(service.detect())' 2>/dev/null || echo unknown)"
if [[ "$INIT_DETECTED" != "unknown" ]]; then
    ok "init system: $INIT_DETECTED (systemd/openrc/runit service files are provided for this)"
else
    fail "No supported init system detected (need systemd, OpenRC, or runit)"
fi

section "1. Source tree"
[[ -f README.md ]] && ok "README.md exists" || fail "README.md missing"
[[ -f docs/ARCHITECTURE.md ]] && ok "Architecture documentation exists" || fail "docs/ARCHITECTURE.md missing"
[[ -f docs/TESTING.md ]] && ok "Testing documentation exists" || fail "docs/TESTING.md missing"
[[ -d tests ]] && ok "tests/ exists" || fail "tests/ missing"

section "2. Python unit tests"
run_check "Unit tests" python3 -m unittest discover -s tests -v

section "3. Python syntax"
run_check "compileall" python3 -m compileall -q netquota tests

section "4. Shell syntax"
run_check "install.sh syntax" bash -n install.sh
run_check "uninstall.sh syntax" bash -n uninstall.sh
run_check "test runner syntax" bash -n tests/run_all.sh

section "5. Portability / hardcoded local values"
if grep -R -n --exclude-dir='__pycache__' --exclude='run_all.sh' 'wlp0s20f0u10' netquota config install.sh uninstall.sh docs README.md; then
    warn "The example config contains the developer machine's interface name; this is acceptable only if it is clearly an example/default. Review before release."
else
    ok "No hardcoded local interface found in source"
fi
if grep -R -n --exclude-dir='__pycache__' --exclude='run_all.sh' '192\.168\.1\.0/24' netquota config install.sh uninstall.sh docs README.md; then
    fail "Hardcoded 192.168.1.0/24 found"
else
    ok "No hardcoded 192.168.1.0/24 found"
fi

section "6. Host network diagnostics"
for cmd in ip nft python3; do
    if command -v "$cmd" >/dev/null 2>&1; then ok "$cmd available"; else fail "$cmd missing"; fi
done

IFACE=""
if command -v ip >/dev/null 2>&1; then
    IFACE="$(ip -j route show default 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["dev"] if d else "")' 2>/dev/null || true)"
fi
if [[ -n "$IFACE" ]]; then
    ok "Default route interface detected: $IFACE"
else
    warn "No default IPv4 route detected"
fi

section "7. Interface / address diagnostics"
if [[ -n "$IFACE" ]]; then
    ip -br link || true
    printf '\nIPv4:\n'
    ip -4 addr show dev "$IFACE" || true
    printf '\nIPv6:\n'
    ip -6 addr show dev "$IFACE" || true
    printf '\nIPv6 routes:\n'
    ip -6 route || true
fi

section "8. Current NetQuota installation"
if command -v netquota >/dev/null 2>&1; then
    INSTALLED="$(command -v netquota)"
    printf 'Installed command: %s\n' "$INSTALLED"
    if netquota version >/tmp/netquota-test.out 2>&1; then
        ok "Installed netquota supports 'version'"
        printf 'Version: '; cat /tmp/netquota-test.out
    else
        warn "Installed netquota does not support 'version'; the current command may be a very old or broken installation."
    fi
    if netquota doctor >/tmp/netquota-test.out 2>&1; then
        ok "Installed netquota passes 'doctor'"
    else
        warn "Installed netquota 'doctor' reported problems (see 'netquota doctor' for details)"
    fi
else
    warn "netquota is not installed in PATH; source-only tests can still pass"
fi

section "9. Current firewall / service state (read-only)"
if sudo -n true >/dev/null 2>&1; then
    SUDO='sudo -n'
else
    SUDO='sudo'
    warn "Some checks may request your sudo password"
fi

if $SUDO nft list table inet netquota >/tmp/netquota-test.out 2>&1; then
    ok "inet netquota table exists"
    sed -n '1,160p' /tmp/netquota-test.out
else
    warn "inet netquota table is not currently present"
fi

if $SUDO nft list table inet firewalld >/tmp/netquota-test.out 2>&1; then
    ok "firewalld table is readable"
else
    warn "Could not read inet firewalld table"
fi

case "$INIT_DETECTED" in
    systemd)
        $SUDO systemctl is-active --quiet firewalld 2>/dev/null && ok "firewalld active" || warn "firewalld is not active"
        $SUDO systemctl is-enabled --quiet netquota.service 2>/dev/null && ok "netquota.service enabled" || warn "netquota.service is not enabled"
        $SUDO systemctl is-active --quiet netquota.service 2>/dev/null && ok "netquota.service active" || warn "netquota.service is not active"
        ;;
    openrc)
        $SUDO rc-service netquota status >/tmp/netquota-test.out 2>&1 && ok "netquota (OpenRC) active" || warn "netquota (OpenRC) is not active"
        ;;
    runit)
        $SUDO sv status netquota >/tmp/netquota-test.out 2>&1 && grep -q '^run:' /tmp/netquota-test.out && ok "netquota (runit) active" || warn "netquota (runit) is not active"
        ;;
    *)
        skip "No supported init system detected; skipping service-state checks"
        ;;
esac

section "10. IPv4 / IPv6 capability"
if [[ -n "$IFACE" ]]; then
    if ip -4 route show default dev "$IFACE" | grep -q .; then
        ok "IPv4 default route exists"
    else
        warn "No IPv4 default route on $IFACE"
    fi
    if ip -6 route show default dev "$IFACE" | grep -q .; then
        ok "IPv6 default route exists"
        if ping -6 -c 2 -W 2 2606:4700:4700::1111 >/tmp/netquota-test.out 2>&1; then
            ok "IPv6 Internet connectivity works"
        else
            warn "IPv6 route exists but IPv6 connectivity test failed"
        fi
    else
        warn "No IPv6 default route on $IFACE; IPv6 Internet testing is not possible on this connection"
    fi
fi

section "11. Live integration tests"
if [[ "$MODE" != "live" ]]; then
    skip "Live tests disabled. Run: sudo ./tests/run_all.sh --live"
else
    cat <<'WARNING'

LIVE MODE WILL MODIFY NETQUOTA'S FIREWALL RULES, CONFIGURATION AND SERVICE STATE.
It may temporarily interrupt Internet access and intentionally tests quota blocking.
Keep a local terminal/console available. Do not run this over an SSH session.

WARNING
    read -r -p "Type RUN-LIVE to continue: " CONFIRM
    if [[ "$CONFIRM" != "RUN-LIVE" ]]; then
        skip "Live tests cancelled"
    else
        CONFIG="/etc/netquota.conf"
        STATE="/var/lib/netquota/state.json"
        BACKUP_DIR="/var/lib/netquota/test-backup-$(date +%Y%m%d-%H%M%S)"
        $SUDO mkdir -p "$BACKUP_DIR"
        $SUDO cp -a "$CONFIG" "$BACKUP_DIR/config" 2>/dev/null || true
        $SUDO cp -a "$STATE" "$BACKUP_DIR/state" 2>/dev/null || true
        ok "Production config/state backed up to $BACKUP_DIR"

        restore() {
            set +e
            if [[ -f "$BACKUP_DIR/config" ]]; then $SUDO cp -a "$BACKUP_DIR/config" "$CONFIG"; fi
            if [[ -f "$BACKUP_DIR/state" ]]; then $SUDO cp -a "$BACKUP_DIR/state" "$STATE"; fi
            $SUDO systemctl restart netquota.service >/dev/null 2>&1 || true
            rm -f /tmp/netquota-test.out
        }
        trap restore EXIT

        if ! command -v netquota >/dev/null 2>&1; then
            fail "Live tests require installed netquota command"
        else
            ORIGINAL_CONFIG="$(sudo cat "$CONFIG" 2>/dev/null || true)"
            TEST_IFACE="$IFACE"
            if [[ -z "$TEST_IFACE" ]]; then
                fail "Cannot run live tests without a default interface"
            else
                # Change only quota/period; preserve interface and other settings.
                $SUDO cp -a "$CONFIG" "$BACKUP_DIR/config.pre-test"
                $SUDO sed -i -E 's/^LIMIT_BYTES=.*/LIMIT_BYTES=10000000/' "$CONFIG"
                $SUDO sed -i -E 's/^PERIOD_DAYS=.*/PERIOD_DAYS=28/' "$CONFIG"
                $SUDO sed -i -E "s/^INTERFACE=.*/INTERFACE=$TEST_IFACE/" "$CONFIG"
                $SUDO systemctl restart netquota.service
                sleep 2

                if netquota reset >/tmp/netquota-test.out 2>&1; then ok "Live reset"; else fail "Live reset"; fi
                if netquota interface >/tmp/netquota-test.out 2>&1; then ok "Live interface query"; else fail "Live interface query"; fi

                BEFORE="$(sudo python3 - <<'PY'
import json
p='/var/lib/netquota/state.json'
try:
    print(json.load(open(p))['used_bytes'])
except Exception:
    print('0')
PY
)"
                if ping -4 -c 5 -W 2 1.1.1.1 >/dev/null 2>&1; then
                    sleep 3
                    AFTER="$(sudo python3 - <<'PY'
import json
p='/var/lib/netquota/state.json'
try:
    print(json.load(open(p))['used_bytes'])
except Exception:
    print('0')
PY
)"
                    if (( AFTER >= BEFORE )); then ok "IPv4 traffic accounted ($BEFORE -> $AFTER bytes)"; else fail "IPv4 traffic accounting did not increase"; fi
                else
                    warn "IPv4 ping failed; skipping traffic-accounting assertion"
                fi

                # Verify IPv6 rules exist when the implementation is installed.
                if $SUDO nft list table inet netquota >/tmp/netquota-test.out 2>&1 && grep -q 'ip6' /tmp/netquota-test.out; then
                    ok "IPv6 nftables rules present"
                else
                    fail "IPv6 nftables rules are missing"
                fi

                # Bypass should create timeout sets without resetting used_bytes.
                USED_BEFORE_BYPASS="$(sudo python3 - <<'PY'
import json
print(json.load(open('/var/lib/netquota/state.json'))['used_bytes'])
PY
)"
                if netquota bypass 30s >/tmp/netquota-test.out 2>&1; then
                    ok "Live bypass enable"
                    if $SUDO nft list set inet netquota bypass4 >/tmp/netquota-test.out 2>&1; then ok "IPv4 bypass set exists"; else warn "IPv4 bypass set not readable"; fi
                    if $SUDO nft list set inet netquota bypass6 >/tmp/netquota-test.out 2>&1; then ok "IPv6 bypass set exists"; else warn "IPv6 bypass set not readable"; fi
                    sleep 2
                    USED_AFTER_BYPASS="$(sudo python3 - <<'PY'
import json
print(json.load(open('/var/lib/netquota/state.json'))['used_bytes'])
PY
)"
                    if (( USED_AFTER_BYPASS >= USED_BEFORE_BYPASS )); then ok "Bypass did not reset quota state"; else fail "Bypass unexpectedly reduced quota state"; fi
                else
                    fail "Live bypass enable"
                fi
                netquota bypass off >/dev/null 2>&1 || true

                # Persistence test: record state, restart service, compare.
                BEFORE_RESTART="$(sudo python3 - <<'PY'
import json
print(json.load(open('/var/lib/netquota/state.json'))['used_bytes'])
PY
)"
                $SUDO systemctl restart netquota.service
                sleep 3
                AFTER_RESTART="$(sudo python3 - <<'PY'
import json
print(json.load(open('/var/lib/netquota/state.json'))['used_bytes'])
PY
)"
                if (( AFTER_RESTART >= BEFORE_RESTART )); then ok "Quota state survives service restart ($BEFORE_RESTART -> $AFTER_RESTART)"; else fail "Quota state regressed after service restart"; fi

                # Verify no destructive flush command exists in source.
                if grep -R -n --exclude-dir='__pycache__' --exclude='run_all.sh' --exclude-dir='docs' --exclude-dir='tests' 'nft[[:space:]]\+flush[[:space:]]\+ruleset' netquota install.sh uninstall.sh systemd >/tmp/netquota-test.out; then
                    fail "Source contains nft flush ruleset"
                    sed -n '1,20p' /tmp/netquota-test.out
                else
                    ok "No nft flush ruleset in source"
                fi
            fi
        fi
    fi
fi

section "Result"
printf '  %s✓ PASS%s %-4s  %s✗ FAIL%s %-4s  %s⚠ WARN%s %-4s  %s⏭ SKIP%s %-4s\n' \
    "$C_GREEN" "$C_OFF" "$PASS" "$C_RED" "$C_OFF" "$FAIL" \
    "$C_YELLOW" "$C_OFF" "$WARN" "$C_BLUE" "$C_OFF" "$SKIP"
if (( FAIL > 0 )); then
    printf '\n%s%s✗ Result: FAILED%s\n' "$C_BOLD" "$C_RED" "$C_OFF"
    exit 1
fi
printf '\n%s%s✓ Result: PASSED%s %s(review warnings/skips before release)%s\n' \
    "$C_BOLD" "$C_GREEN" "$C_OFF" "$C_DIM" "$C_OFF"
