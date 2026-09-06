# Testing Guide

## Unit tests

Run without root/network changes:

```bash
python3 -m unittest discover -s tests -v
```

Coverage areas include duration parsing, vnStat parsing, state persistence, expiry, configuration validation, interface/address discovery, and generated IPv4/IPv6 nftables rules.

## Manual integration test (recommended before release)

Run on a disposable VM or machine where temporary Internet interruption is acceptable:

1. Install NetQuota with a small test quota (for example 10 MB).
2. Confirm `netquota status`.
3. Generate download traffic and verify usage increases.
4. Generate upload traffic and verify usage increases.
5. Generate IPv6 traffic if the host has a global IPv6 route.
6. Confirm LAN traffic does not consume the quota.
7. Use `netquota bypass 2m`; verify Internet works while quota usage remains unchanged.
8. Wait for timeout; verify normal accounting resumes.
9. Run `netquota bypass off`; verify immediate removal.
10. Force a reboot below the limit; verify remaining quota is preserved.
11. Consume the quota; verify Internet traffic is blocked.
12. Reboot while blocked; verify it remains blocked.
13. Run `netquota reset`; verify a new 28-day period and restored connectivity.
14. Change `netquota interface eth0`, restart service, and verify the new interface is enforced.
15. Stop/start `netquota.service` repeatedly; verify the counter is not reset.
16. Inspect `journalctl -u netquota` for clean recovery.
17. Run `netquota off`; verify Internet is immediately fully open (both IPv4 and IPv6, even above the quota) and the service is stopped+disabled.
18. Run `netquota on`; verify enforcement resumes from the same usage counter (not reset to 0).
19. Run `netquota doctor` with `vnstat` or `nft` temporarily uninstalled (or renamed); verify it reports the missing dependency clearly and exits non-zero.
20. On OpenRC/runit hosts: repeat steps 1–18 using `rc-service netquota` / `sv up|down netquota` instead of `systemctl`.

## Safety checks

- Never run `nft flush ruleset`.
- Verify `nft list table inet firewalld` is unchanged before/after installation.
- Keep an out-of-band shell (physical console/second network) during firewall testing.
