import subprocess

def parse_size(value):
    parts = value.strip().split()
    if len(parts) != 2: raise ValueError(value)
    number = float(parts[0])
    units = {"B":1,"KiB":1024,"MiB":1024**2,"GiB":1024**3,"TiB":1024**4,"PiB":1024**5,"KB":1000,"MB":1000**2,"GB":1000**3,"TB":1000**4,"PB":1000**5}
    return int(number * units[parts[1]])

def read(interface):
    r = subprocess.run(["vnstat", "--oneline", "-i", interface], text=True, capture_output=True, check=True, timeout=3)
    f = r.stdout.strip().split(";")
    if len(f) < 15: raise ValueError("unexpected vnStat output")
    return {
        "day_rx": parse_size(f[3]), "day_tx": parse_size(f[4]), "day_total": parse_size(f[5]),
        "total_rx": parse_size(f[12]), "total_tx": parse_size(f[13]), "total": parse_size(f[14]),
    }
