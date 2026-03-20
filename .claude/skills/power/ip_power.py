#!/usr/bin/env python3
"""
Aviosys IP Power 9258W2 - Power Outlet Controller
Usage examples:
  python ip_power.py --outlet 1 --action on
  python ip_power.py --outlet 1 --action off
  python ip_power.py --outlet 1 --action toggle
  python ip_power.py --status
"""
import argparse
import requests
from requests.auth import HTTPBasicAuth
# ── Configuration ─────────────────────────────────────────────────────────────
HOST     = "10.56.17.6"
USERNAME = "user"          # default credentials for IP Power 9258W2
PASSWORD = "user"       # change if you've updated them
TIMEOUT  = 5                # seconds
# ──────────────────────────────────────────────────────────────────────────────
BASE_URL = f"http://{HOST}"
AUTH     = HTTPBasicAuth(USERNAME, PASSWORD)
HEADERS  = {"Connection": "close"}   # PDU web server only supports HTTP/1.0

def get_status() -> dict:
    """Read the current on/off status of all 4 outlets.
    /ioread.asp returns values separated by '=':
      index 0-3  → outlet 1-4 status  (0 = OFF, 1 = ON)
      index 4-7  → outlet 1-4 current (Amps)
      index 8    → temperature
    """
    url = f"{BASE_URL}/ioread.asp"
    resp = requests.get(url, auth=AUTH, timeout=TIMEOUT, headers=HEADERS)
    resp.raise_for_status()
    values = resp.content.decode("utf-8-sig").split("=")
    status = {}
    for i in range(4):
        outlet_num = i + 1
        state = int(values[i].strip()) if values[i].strip() else 0
        current = float(values[i + 4].strip()) if values[i + 4].strip() else 0.0
        status[outlet_num] = {
            "on":      bool(state),
            "state":   "ON" if state else "OFF",
            "current": current,
        }
    return status
    
def set_outlet(outlet: int, turn_on: bool) -> bool:
    """Turn a single outlet ON (turn_on=True) or OFF (turn_on=False).
    Endpoint: GET /goform/setpower?p6{outlet}={0|1}
    """
    if outlet not in range(1, 5):
        raise ValueError(f"Outlet must be 1–4, got {outlet}")
    value = 1 if turn_on else 0
    url   = f"{BASE_URL}/goform/setpower?p6{outlet}={value}"
    resp  = requests.get(url, auth=AUTH, timeout=TIMEOUT, headers=HEADERS)
    resp.raise_for_status()
    return resp.status_code == 200
    
def toggle_outlet(outlet: int) -> bool:
    """Toggle the current state of an outlet."""
    status    = get_status()
    currently_on = status[outlet]["on"]
    return set_outlet(outlet, not currently_on)
    
def power_cycle(outlet: int, cycle_seconds: int = 5) -> None:
    """Turn outlet OFF, wait, then turn it back ON."""
    import time
    print(f"Power cycling outlet {outlet}: turning OFF…")
    set_outlet(outlet, False)
    time.sleep(cycle_seconds)
    print(f"Power cycling outlet {outlet}: turning ON…")
    set_outlet(outlet, True)
    
# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    global HOST, BASE_URL, AUTH
    parser = argparse.ArgumentParser(description="Control Aviosys IP Power 9258W2 outlets")
    parser.add_argument("--host",     default=HOST,     help="Device IP address")
    parser.add_argument("--user",     default=USERNAME, help="HTTP username")
    parser.add_argument("--password", default=PASSWORD, help="HTTP password")
    parser.add_argument("--outlet",   type=int, choices=[1, 2, 3, 4],
                        help="Outlet number (1–4)")
    parser.add_argument("--action",   choices=["on", "off", "toggle", "cycle"],
                        help="Action to perform")
    parser.add_argument("--status",   action="store_true",
                        help="Print status of all outlets")
    parser.add_argument("--cycle-sec", type=int, default=5,
                        help="Seconds to wait during power cycle (default: 5)")
    args = parser.parse_args()
    
    # Override globals if provided via CLI
    HOST     = args.host
    BASE_URL = f"http://{HOST}"
    AUTH     = HTTPBasicAuth(args.user, args.password)
    if args.status or not args.action:
        status = get_status()
        print(f"{'Outlet':<8} {'State':<6} {'Current':>8}")
        print("-" * 26)
        for num, info in status.items():
            print(f"  {num:<6} {info['state']:<6} {info['current']:>7.1f}A")
        return
    if not args.outlet:
        parser.error("--outlet is required when using --action")
    outlet = args.outlet
    if args.action == "on":
        set_outlet(outlet, True)
        print(f"Outlet {outlet} turned ON.")
    elif args.action == "off":
        set_outlet(outlet, False)
        print(f"Outlet {outlet} turned OFF.")
    elif args.action == "toggle":
        toggle_outlet(outlet)
        print(f"Outlet {outlet} toggled.")
    elif args.action == "cycle":
        power_cycle(outlet, args.cycle_sec)
        print(f"Outlet {outlet} power cycle complete.")

if __name__ == "__main__":
    main()