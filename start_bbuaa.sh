#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

START_PORT="${1:-8765}"
shift || true

find_free_port() {
	local port="$1"
	local max_tries=200
	local try=0

	while (( try < max_tries )); do
		if python3 - <<'PY' "$port" >/dev/null 2>&1; then
import socket, sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		s.bind(("127.0.0.1", port))
PY
			echo "$port"
			return 0
		fi
		port=$((port + 1))
		try=$((try + 1))
	done

	return 1
}

PORT="$(find_free_port "$START_PORT")"
echo "[+] BBUAA 课程浏览器将启动在: http://127.0.0.1:${PORT}/"

exec python3 -m assemble.server --port "$PORT" "$@"
