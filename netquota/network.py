import ipaddress
import json
import subprocess

EXCLUDED = {"lo", "docker0", "virbr0"}

def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True)

def interfaces():
    r = run("ip", "-j", "link", "show")
    out = []
    for x in json.loads(r.stdout):
        name = x["ifname"]
        if name == "lo" or name.startswith(("docker", "virbr", "br-", "veth")):
            continue
        out.append({"name": name, "type": x.get("link_type", "unknown"), "up": bool(x.get("flags") and "UP" in x["flags"])})
    return out

def interface_addresses(iface):
    r = run("ip", "-j", "addr", "show", "dev", iface)
    data = json.loads(r.stdout)[0]
    v4, v6 = [], []
    for a in data.get("addr_info", []):
        if a.get("family") == "inet": v4.append(a["local"])
        elif a.get("family") == "inet6": v6.append(a["local"])
    return v4, v6

def default_interface():
    r = run("ip", "-j", "route", "show", "default")
    routes = json.loads(r.stdout)
    if not routes: raise RuntimeError("No default IPv4 route found")
    return routes[0]["dev"]

def valid_interface(name):
    return any(x["name"] == name for x in interfaces())
