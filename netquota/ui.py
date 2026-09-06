import os
import re
import sys
from datetime import datetime, timezone

ESC = "\033["
BOX_WIDTH = 50          # total width including both border characters
INNER_WIDTH = BOX_WIDTH - 4   # text area between the two single-space margins


def _color_enabled():
    """Colors are opt-out, not opt-in: disabled only when explicitly asked
    (NO_COLOR, a common cross-tool convention) or when stdout isn't a real
    terminal (piped to a file/log, non-interactive service context)."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


COLOR = _color_enabled()


def c(code, s):
    if not COLOR:
        return s
    return f"{ESC}{code}m{s}{ESC}0m"


def human(n, binary=False):
    units = ["B", "KiB", "MiB", "GiB", "TiB"] if binary else ["B", "KB", "MB", "GB", "TB"]
    base = 1024 if binary else 1000
    x = float(max(0, n))
    for u in units:
        if x < base:
            return f"{x:.2f} {u}"
        x /= base
    return f"{x:.2f} PB"


def width(s):
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def row(s, w=INNER_WIDTH):
    return "│ " + s + " " * max(0, w - width(s)) + " │"


def divider():
    return "├" + "─" * (BOX_WIDTH - 2) + "┤"


def title_row(text):
    pad = max(0, INNER_WIDTH - len(text))
    left = pad // 2
    right = pad - left
    return row(c("1;36", " " * left + text + " " * right))


def section_row(label):
    return row(c("1", f"   {label}"))


COMMANDS = [
    ("netquota status", "Show this screen"),
    ("netquota usage", "Plain-text usage numbers"),
    ("netquota bypass <30m|2h|1d>", "Temporarily lift the block"),
    ("netquota bypass off", "Cancel an active bypass now"),
    ("netquota reset", "Reset usage and start a new period"),
    ("netquota on / off", "Enable/disable enforcement entirely"),
    ("netquota interface [name]", "Show/change the monitored interface"),
    ("netquota config", "Print the config file"),
    ("netquota service", "Underlying service status"),
    ("netquota doctor", "Check required dependencies"),
]


def status_text(state, cfg, vn=None, iface=None, now=None, service_active=None):
    now = now or datetime.now(timezone.utc)
    used = state.used_bytes
    limit = cfg.limit_bytes
    pct = min(100, used / limit * 100) if limit else 0
    if pct >= 90:
        col = "1;31"
    elif pct >= 75:
        col = "1;33"
    elif pct >= 50:
        col = "1;93"
    else:
        col = "1;32"
    filled = int(30 * pct / 100)
    bar = c(col, "█" * filled) + c("2", "░" * (30 - filled))
    rem = max(0, limit - used)
    end = datetime.fromisoformat(state.period_end)
    left = max(0, int((end - now).total_seconds()))
    d, r = divmod(left, 86400)
    h, _ = divmod(r, 3600)

    lines = [
        "╭" + "─" * (BOX_WIDTH - 2) + "╮",
        title_row("INTERNET QUOTA"),
        divider(),
        section_row("QUOTA"),
        row(f"   {bar} {c(col, f'{pct:5.2f}%')}"),
        row(""),
        row(f"   Used                {c('1', human(used))}"),
        row(f"   Remaining           {c('1;32', human(rem))}"),
        row(f"   Limit               {human(limit)}"),
        divider(),
    ]

    if vn:
        lines += [
            section_row("VNSTAT — NETWORK STATISTICS"),
            row(""),
            row("   Today"),
            row(f"   {c('1;34', '↓')} Download         {human(vn['day_rx'], True)}"),
            row(f"   {c('1;35', '↑')} Upload           {human(vn['day_tx'], True)}"),
            row(f"   ⇅ Total            {human(vn['day_total'], True)}"),
            row(""),
            row("   Since monitoring started"),
            row(f"   {c('1;34', '↓')} Download        {human(vn['total_rx'], True)}"),
            row(f"   {c('1;35', '↑')} Upload          {human(vn['total_tx'], True)}"),
            row(f"   ⇅ Total           {human(vn['total'], True)}"),
            divider(),
        ]

    active = service_active if service_active is not None else True
    if not active:
        internet_label = c("1;33", "UNRESTRICTED (enforcement off)")
    elif state.blocked:
        internet_label = c("1;31", "BLOCKED")
    else:
        internet_label = c("1;32", "ENABLED")
    service_label = c("1;32", "RUNNING") if active else c("1;33", "STOPPED")
    bypass_label = c("1;32", "ON") if state.bypass_until else "OFF"
    dot = c("1;32", "●") if active else c("1;33", "●")

    lines += [
        section_row("PERIOD"),
        row(f"   Started     {datetime.fromisoformat(state.period_start).astimezone().strftime('%d %b %Y  %H:%M')}"),
        row(f"   Ends        {end.astimezone().strftime('%d %b %Y  %H:%M')}"),
        row(f"   Remaining   {d}d {h:02d}h"),
        divider(),
        section_row("STATUS"),
        row(f"   {dot} Internet   {internet_label}"),
        row(f"   {dot} Service    {service_label}"),
        row(f"   {dot} Bypass     {bypass_label}"),
        divider(),
        section_row("COMMANDS"),
    ]
    for cmd, desc in COMMANDS:
        lines.append(row(f"   {c('1;36', cmd)}"))
        lines.append(row(f"     {c('2', desc)}"))
    lines.append("╰" + "─" * (BOX_WIDTH - 2) + "╯")
    return "\n".join(lines)
