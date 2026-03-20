#!/usr/bin/env python3
"""
Shared HTTP server helper for deploying files to the AXN-2020 DUT.

Manages the lifecycle of a Python HTTP server: start, stop, status.
Ensures only one server runs on a given port at a time.

Usage:
    # Start server (kills existing, then runs in foreground — use with run_in_background)
    python http_server.py --start --dir ./tmp --bind 30.0.0.1 --port 8080

    # Stop any server on port
    python http_server.py --stop  [--port 8080]

    # Check if server is running
    python http_server.py --status [--port 8080]
"""

import argparse
import http.server
import os
import socket
import subprocess
import sys
import time


def find_pid_on_port(port):
    """Find the PID of a process listening on the given port."""
    try:
        import psutil
        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                return conn.pid
    except ImportError:
        pass

    # Fallback: parse netstat output
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and f":{port}" in parts[1] and "LISTENING" in parts[3]:
                return int(parts[4])
    except Exception:
        pass

    return None


def kill_pid(pid):
    """Kill a process by PID."""
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.terminate()
        proc.wait(timeout=5)
        return True
    except ImportError:
        pass
    except Exception:
        try:
            import psutil
            psutil.Process(pid).kill()
            return True
        except Exception:
            pass

    # Fallback: taskkill on Windows
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            check=True, capture_output=True
        )
        return True
    except Exception:
        return False


def is_port_free(port):
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def wait_for_port_free(port, retries=10):
    """Wait for a port to become free."""
    for _ in range(retries):
        if is_port_free(port):
            return True
        time.sleep(0.5)
    return False


def do_status(port):
    """Print the status of the HTTP server on the given port."""
    pid = find_pid_on_port(port)
    if pid:
        print(f"HTTP server running on port {port} (PID {pid})")
        return True
    else:
        print(f"No server running on port {port}")
        return False


def do_stop(port):
    """Stop any HTTP server running on the given port."""
    pid = find_pid_on_port(port)
    if not pid:
        print(f"No server running on port {port}")
        return True

    print(f"Killing PID {pid} on port {port}...", end=" ")
    if kill_pid(pid):
        wait_for_port_free(port)
        print("OK")
        return True
    else:
        print("FAILED")
        return False


def do_start(directory, bind_ip, port):
    """Kill any existing server on the port, then run HTTP server in foreground.

    This function does NOT return until the server is interrupted (Ctrl+C or killed).
    Intended to be run with Bash tool's run_in_background: true.
    """
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        print(f"Error: directory '{directory}' does not exist")
        sys.exit(1)

    # Kill existing server on this port
    pid = find_pid_on_port(port)
    if pid:
        print(f"Existing server on port {port} (PID {pid}), killing...", end=" ")
        if not kill_pid(pid):
            print("FAILED — cannot free port")
            sys.exit(1)
        if not wait_for_port_free(port):
            print("FAILED — port still in use after kill")
            sys.exit(1)
        print("OK")

    # Run server in foreground
    print(f"Starting HTTP server on {bind_ip}:{port}")
    print(f"Serving: {directory}")

    handler = http.server.SimpleHTTPRequestHandler
    os.chdir(directory)
    server = http.server.HTTPServer((bind_ip, port), handler)
    print(f"PID {os.getpid()} ready")
    sys.stdout.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Server stopped")


def main():
    parser = argparse.ArgumentParser(description="HTTP server lifecycle manager")

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--start", action="store_true",
                        help="Kill existing server on port, then start in foreground (use with run_in_background)")
    action.add_argument("--stop", action="store_true", help="Stop HTTP server on port")
    action.add_argument("--status", action="store_true", help="Check if HTTP server is running")

    parser.add_argument("--dir", default="./tmp", help="Directory to serve (default: ./tmp)")
    parser.add_argument("--bind", default="30.0.0.1", help="IP to bind to (default: 30.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port number (default: 8080)")

    args = parser.parse_args()

    if args.status:
        do_status(args.port)
    elif args.stop:
        do_stop(args.port)
    elif args.start:
        do_start(args.dir, args.bind, args.port)


if __name__ == "__main__":
    main()
