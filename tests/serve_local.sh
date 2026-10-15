#!/usr/bin/env bash
# Поднимает локальный стек для проверки UI без docker:
#   стенд HF (8081) -> backend (8000) -> nginx с Basic Auth (8090)
# Логин/пароль: tester / secret123
# Останавливать:  kill "$(cat /tmp/jbai_dev/nginx.pid)" и процессы python (см. run_local.sh).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
D=/tmp/jbai_dev
mkdir -p "$D/logs"

pkill -f "stub_hf.py" 2>/dev/null || true
# подчистить прежний dev-nginx (иначе порт занят)
[ -f /tmp/jbai_dev/nginx.pid ] && kill "$(cat /tmp/jbai_dev/nginx.pid)" 2>/dev/null || true
pkill -f "nginx -c /tmp" 2>/dev/null || true
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

"$PY" "$ROOT/tests/stub_hf.py" 8081 >"$D/stub.log" 2>&1 &
echo $! > "$D/stub.pid"

( cd "$ROOT/backend" && HF_TOKEN=dev-key HF_BASE_URL=http://127.0.0.1:8081/v1 HF_VERIFY_ON_STARTUP=off \
    PYTHONPATH=. "$PY" -m uvicorn app.main:app --port 8000 ) >"$D/backend.log" 2>&1 &
echo $! > "$D/backend.pid"

htpasswd -bc "$D/.htpasswd" tester secret123 >/dev/null 2>&1
chmod 644 "$D/.htpasswd"; chmod 755 "$D"

sed -e "s#/etc/nginx/.htpasswd#$D/.htpasswd#" \
    -e "s#/usr/share/nginx/html#$ROOT/frontend#" \
    -e "s#listen 80;#listen 8090;#" \
    -e "s#http://backend:8000#http://127.0.0.1:8000#" \
    "$ROOT/nginx/default.conf" > "$D/app.conf"

cat > "$D/nginx.main.conf" <<EOF
worker_processes 1;
error_log $D/logs/error.log warn;
pid $D/nginx.pid;
events { worker_connections 64; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log $D/logs/access.log;
  client_body_temp_path $D/body;
  proxy_temp_path $D/proxy;
  fastcgi_temp_path $D/fastcgi;
  uwsgi_temp_path $D/uwsgi;
  scgi_temp_path $D/scgi;
  include $D/app.conf;
}
EOF

nginx -c "$D/nginx.main.conf" -t && nginx -c "$D/nginx.main.conf"

for _ in $(seq 1 40); do curl -sf -u tester:secret123 http://127.0.0.1:8090/api/health >/dev/null && break; sleep 0.25; done

echo "UI:      http://127.0.0.1:8090/   (логин tester / пароль secret123)"
echo "backend: http://127.0.0.1:8000/api/health"
curl -s -u tester:secret123 http://127.0.0.1:8090/api/health; echo
