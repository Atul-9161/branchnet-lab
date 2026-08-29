#!/usr/bin/env python3
"""
monitor.py — reachability + uptime trend monitor for BranchNet-Lab

Pings a fixed list of hosts on a loop and logs state changes only
(not every single check — that just makes the log unreadable).
A host has to fail twice in a row before it's marked down, so a
single dropped ICMP packet doesn't trigger a false alert.

On top of basic up/down logging, this version tracks how many checks
each host passed vs failed overall, so you can see which devices are
flaky over time rather than just their current state — closer to how
real monitoring tools help spot a failing NIC or a bad cable before
it causes a full outage.

Usage:
    python3 monitor.py
    (edit HOSTS below to match your lab's IPs)
    Ctrl+C to stop — prints an uptime summary on exit
"""

import subprocess
import time
import platform
from datetime import datetime

IS_WINDOWS = platform.system().lower() == "windows"

HOSTS = {
    "Google-DNS":    "8.8.8.8",
    "Cloudflare-DNS": "1.1.1.1",
    "Localhost":     "127.0.0.1",
    "Fake-Host":     "192.0.2.1",   # this one should always show DOWN (unreachable test IP)
}

CHECK_INTERVAL_SECONDS = 30
FAILS_BEFORE_DOWN = 2
LOG_FILE = "network_log.txt"

# Terminal colors for alerts — plain ANSI, works in most terminals
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def ping(ip):
    """Returns True if host responds, False otherwise. One packet, ~1s timeout.

    Windows and Linux/Mac use different ping flags:
      - Windows:    -n <count>  -w <timeout in milliseconds>
      - Linux/Mac:  -c <count>  -W <timeout in seconds>
    Using the wrong flags doesn't error out cleanly on Windows — it just
    causes every single ping to "fail", which looks exactly like every
    host being down. Found this the hard way testing on Windows.
    """
    if IS_WINDOWS:
        cmd = ["ping", "-n", "1", "-w", "1000", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]

    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def log_event(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")


def alert(message):
    """Loud terminal alert for a DOWN event — bell + red text."""
    print(f"\a{RED}!! ALERT: {message} !!{RESET}")


def print_summary(checks_total, checks_ok):
    """Uptime trend summary — printed on exit (Ctrl+C)."""
    print("\n" + "=" * 50)
    print("UPTIME SUMMARY (this session)")
    print("=" * 50)
    for name in HOSTS:
        total = checks_total[name]
        ok = checks_ok[name]
        pct = (ok / total * 100) if total else 0
        color = GREEN if pct >= 99 else YELLOW if pct >= 90 else RED
        print(f"  {name:<16} {color}{pct:5.1f}%{RESET}  ({ok}/{total} checks passed)")
    print("=" * 50)


def main():
    state = {name: "up" for name in HOSTS}
    consecutive_fails = {name: 0 for name in HOSTS}
    checks_total = {name: 0 for name in HOSTS}
    checks_ok = {name: 0 for name in HOSTS}

    log_event(f"Monitoring started for {len(HOSTS)} hosts "
              f"(interval={CHECK_INTERVAL_SECONDS}s, threshold={FAILS_BEFORE_DOWN} fails)")

    try:
        while True:
            for name, ip in HOSTS.items():
                alive = ping(ip)
                checks_total[name] += 1

                if alive:
                    checks_ok[name] += 1
                    if state[name] == "down":
                        log_event(f"RECOVERED: {name} ({ip}) is back up")
                    state[name] = "up"
                    consecutive_fails[name] = 0
                else:
                    consecutive_fails[name] += 1
                    if consecutive_fails[name] >= FAILS_BEFORE_DOWN and state[name] == "up":
                        msg = f"{name} ({ip}) failed {consecutive_fails[name]} checks in a row"
                        log_event(f"DOWN: {msg}", level="WARNING")
                        alert(msg)
                        state[name] = "down"

            up_count = sum(1 for s in state.values() if s == "up")
            down_hosts = [n for n, s in state.items() if s == "down"]
            status_line = f"-- status: {up_count}/{len(HOSTS)} hosts up"
            if down_hosts:
                status_line += f"  |  DOWN: {', '.join(down_hosts)}"
            status_line += " --"
            print(status_line)

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        log_event("Monitoring stopped by user")
        print_summary(checks_total, checks_ok)


if __name__ == "__main__":
    main()