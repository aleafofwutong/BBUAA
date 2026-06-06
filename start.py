from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8765
MAX_TRIES = 200


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def find_free_port(start_port: int) -> int:
    for port in range(start_port, start_port + MAX_TRIES):
        if is_port_free(port):
            return port
    raise RuntimeError(f"No free port found from {start_port} to {start_port + MAX_TRIES - 1}")


def parse_start_port(argv: list[str]) -> tuple[int, list[str]]:
    if not argv:
        return DEFAULT_PORT, []

    try:
        return int(argv[0]), argv[1:]
    except ValueError:
        return DEFAULT_PORT, argv


def main() -> int:
    start_port, extra_args = parse_start_port(sys.argv[1:])
    port = find_free_port(start_port)

    os.chdir(ROOT_DIR)
    print(f"[+] BBUAA course browser will start at: http://127.0.0.1:{port}/")

    command = [sys.executable, "-m", "assemble.server", "--port", str(port), *extra_args]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
