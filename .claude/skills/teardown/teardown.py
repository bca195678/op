#!/usr/bin/env python3
"""Teardown — clean up session state on Host and DUT."""

import argparse
import os
import shutil
import subprocess
import sys
import time

import psutil
import serial


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
TMP_DIR = os.path.join(PROJECT_ROOT, 'tmp')
NAT_REMOVE_SRC = os.path.join(SCRIPT_DIR, '..', 'picoclaw', 'nat-remove.ps1')
IP_POWER_SCRIPT = os.path.join(SCRIPT_DIR, '..', 'power', 'ip_power.py')


def kill_http_servers():
    """Kill any python http.server processes on ports 808x."""
    killed = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline'] or []
            cmd = ' '.join(cmdline)
            if 'http.server' in cmd and '808' in cmd:
                proc.kill()
                killed += 1
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return killed


def kill_picoclaw(device, baud):
    """Send killall picoclaw-linux-arm64 to DUT via serial."""
    try:
        s = serial.Serial(device, baud, timeout=3)
        # Send Ctrl+C first in case something is blocking
        s.write(b'\x03\r\n')
        time.sleep(0.5)
        s.read(s.in_waiting or 1)
        # Send killall
        s.write(b'killall picoclaw-linux-arm64 2>/dev/null && echo KILLED || echo NOT_RUNNING\r\n')
        time.sleep(2)
        out = s.read(s.in_waiting or 1).decode('utf-8', errors='replace')
        s.close()
        if 'KILLED' in out:
            return 'killed'
        elif 'NOT_RUNNING' in out:
            return 'not running'
        else:
            return 'unknown'
    except serial.SerialException as e:
        return f'serial error: {e}'


def remove_nat():
    """Remove Windows NAT by running nat-remove.ps1 elevated."""
    src = os.path.abspath(NAT_REMOVE_SRC)
    dst = os.path.join(TMP_DIR, 'nat-remove.ps1')
    result_file = os.path.join(TMP_DIR, 'nat-result.txt')

    if not os.path.exists(src):
        return 'nat-remove.ps1 not found'

    os.makedirs(TMP_DIR, exist_ok=True)
    shutil.copy2(src, dst)

    # Clear previous result
    if os.path.exists(result_file):
        os.remove(result_file)

    # Run elevated
    subprocess.run([
        'powershell', '-Command',
        f'Start-Process powershell -Verb RunAs -ArgumentList '
        f"'-NoProfile -ExecutionPolicy Bypass -File {dst}' -Wait"
    ], timeout=30)

    # Read result
    if os.path.exists(result_file):
        with open(result_file, 'r', encoding='utf-8') as f:
            result = f.read().strip()
        return 'removed' if 'REMOVE_OK' in result else result
    return 'no result file'


def power_off(python_exe):
    """Power off DUT outlet 2 via ip_power.py."""
    script = os.path.abspath(IP_POWER_SCRIPT)
    if not os.path.exists(script):
        return 'ip_power.py not found'
    try:
        r = subprocess.run(
            [python_exe, script, '--outlet', '2', '--action', 'off'],
            capture_output=True, text=True, timeout=15
        )
        return 'powered off' if r.returncode == 0 else r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 'timeout'


def main():
    parser = argparse.ArgumentParser(description='Teardown session state')
    parser.add_argument('--keep-nat', action='store_true',
                        help='Do not remove Windows NAT rule')
    parser.add_argument('--power-off', action='store_true',
                        help='Power off DUT after cleanup')
    parser.add_argument('--device', default='COM200',
                        help='DUT serial port (default: COM200)')
    parser.add_argument('--baud', type=int, default=115200,
                        help='Baud rate (default: 115200)')
    args = parser.parse_args()

    python_exe = sys.executable
    results = []

    # 1. Kill HTTP servers
    count = kill_http_servers()
    results.append(('HTTP servers', f'{count} killed' if count else 'none running'))

    # 2. Kill picoclaw on DUT
    status = kill_picoclaw(args.device, args.baud)
    results.append(('Picoclaw gateway', status))

    # 3. NAT removal (optional)
    if args.keep_nat:
        results.append(('Windows NAT', 'kept (--keep-nat)'))
    else:
        status = remove_nat()
        results.append(('Windows NAT', status))

    # 4. Power off (optional)
    if args.power_off:
        status = power_off(python_exe)
        results.append(('DUT power', status))
    else:
        results.append(('DUT power', 'skipped (use --power-off)'))

    # Print summary
    print()
    print(f'{"Component":<22} {"Result"}')
    print('-' * 44)
    for component, result in results:
        print(f'{component:<22} {result}')
    print()


if __name__ == '__main__':
    main()
