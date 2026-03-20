#!/usr/bin/env python3
"""
Minimal TFTP server using tftpy.
Serves a local directory for a fixed duration, then exits.

Usage:
  python tftp_server.py --dir ./tmp --ip 30.0.0.1 --port 69 --timeout 180
"""
import argparse
import threading
import time
import tftpy

def main():
    parser = argparse.ArgumentParser(description="TFTP server for firmware deployment")
    parser.add_argument("--dir",     default="./tmp",      help="Directory to serve (default: ./tmp)")
    parser.add_argument("--ip",      default="30.0.0.1",   help="IP address to listen on (default: 30.0.0.1)")
    parser.add_argument("--port",    type=int, default=69,  help="UDP port (default: 69)")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to run before exiting (default: 180)")
    args = parser.parse_args()

    server = tftpy.TftpServer(args.dir)
    t = threading.Thread(
        target=server.listen,
        kwargs={"listenip": args.ip, "listenport": args.port}
    )
    t.daemon = True
    t.start()
    print(f"TFTP server started on {args.ip}:{args.port} serving '{args.dir}'")
    time.sleep(args.timeout)
    print("TFTP server timeout — exiting.")

if __name__ == "__main__":
    main()
