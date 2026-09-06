import re

def seconds(text):
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhdw])\s*", text.lower())
    if not m: raise ValueError("duration must look like 30m, 2h, 1d, or 1w")
    n = float(m.group(1)); unit = m.group(2)
    mult = {"s":1,"m":60,"h":3600,"d":86400,"w":604800}[unit]
    value = int(n * mult)
    if value <= 0: raise ValueError("duration must be > 0")
    return value
