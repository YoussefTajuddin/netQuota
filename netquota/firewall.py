import ipaddress
import subprocess


def nft(*args, check=True):
    return subprocess.run(["nft", *args], text=True, capture_output=True, check=check)


def get_quota_used():
    import json
    r = nft("-j", "list", "quota", "inet", "netquota", "internet_quota")
    data = json.loads(r.stdout)
    for item in data.get("nftables", []):
        q = item.get("quota")
        if q and q.get("name") == "internet_quota":
            return int(q.get("used", 0))
    raise RuntimeError("internet_quota not found")


def _network(s):
    return ipaddress.ip_network(s, strict=False)


def install(cfg, used_bytes):
    remaining = max(0, cfg.limit_bytes - used_bytes)
    # nft's quota syntax accepts bytes; using bytes avoids unit rounding.
    v4_local = _network(cfg.local_ipv4)
    v4_ex = _network(cfg.exclude_ipv4)
    v6_local = _network(cfg.local_ipv6)
    v6_ex = _network(cfg.exclude_ipv6)
    lines = [
        "table inet netquota {",
        f"  quota internet_quota {{ over {remaining} bytes }}",
        "  set bypass4 { type ipv4_addr; flags timeout; }",
        "  set bypass6 { type ipv6_addr; flags timeout; }",
        "  chain input {",
        "    type filter hook input priority -200; policy accept;",
        f'    iifname "{cfg.interface}" ip daddr @bypass4 accept',
        f'    iifname "{cfg.interface}" ip6 daddr @bypass6 accept',
        f'    iifname "{cfg.interface}" ip saddr != {v4_local} ip saddr != {v4_ex} quota name "internet_quota" drop',
        f'    iifname "{cfg.interface}" ip6 saddr != {v6_local} ip6 saddr != {v6_ex} ip6 daddr != ff00::/8 quota name "internet_quota" drop',
        "  }",
        "  chain output {",
        "    type filter hook output priority -200; policy accept;",
        f'    oifname "{cfg.interface}" ip saddr @bypass4 accept',
        f'    oifname "{cfg.interface}" ip6 saddr @bypass6 accept',
        f'    oifname "{cfg.interface}" ip daddr != {v4_local} ip daddr != {v4_ex} quota name "internet_quota" drop',
        f'    oifname "{cfg.interface}" ip6 daddr != {v6_local} ip6 daddr != {v6_ex} ip6 daddr != ff00::/8 quota name "internet_quota" drop',
        "  }",
        "}",
    ]
    ruleset = "\n".join(lines) + "\n"
    check = subprocess.run(["nft", "-c", "-f", "-"], input=ruleset, text=True, capture_output=True)
    if check.returncode:
        raise RuntimeError("nft syntax validation failed: " + check.stderr.strip())
    nft("delete", "table", "inet", "netquota", check=False)
    p = subprocess.run(["nft", "-f", "-"], input=ruleset, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.strip())


def uninstall():
    """Remove the netquota nftables table entirely, restoring unrestricted
    traffic on the configured interface. Used by `netquota off` and by
    uninstall.sh. Never touches any other table (firewalld's included)."""
    nft("delete", "table", "inet", "netquota", check=False)


def clear_bypass():
    nft("flush", "set", "inet", "netquota", "bypass4", check=False)
    nft("flush", "set", "inet", "netquota", "bypass6", check=False)


def add_bypass(addresses, seconds):
    for family, addrs in ((4, addresses[0]), (6, addresses[1])):
        for addr in addrs:
            setname = "bypass4" if family == 4 else "bypass6"
            nft("add", "element", "inet", "netquota", setname, "{", addr, "timeout", f"{seconds}s", "}")
