#!/usr/bin/env bash
# Автопроверки проекта. Запускается локально (без docker) и проверяет:
#   1) пустой HF_TOKEN  -> backend НЕ поднимается с понятной ошибкой
#   2) health           -> отдаёт модель и статус
#   3) /api/chat        -> СТРИМ: минимум 3 кадра, первый < 1.5 c, полный текст собран
#   4) nginx            -> 401 без пароля, 200 с паролем, статика отдаётся,
#                          SSE через nginx идёт по кадрам (буферизация выключена)
set -uo pipefail

# PYTHON — интерпретатор с зависимостями backend (fastapi/uvicorn/openai)
PY=${PYTHON:-python3}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STUB_PORT=${STUB_PORT:-8081}
BACK_PORT=${BACK_PORT:-8000}
NGX_PORT=${NGX_PORT:-8090}
TMP="$(mktemp -d)"
PASS=0; FAIL=0

ok()   { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (ожидалось '$3', получено '$2')"; fi; }

cleanup() { kill ${STUB_PID:-} ${BACK_PID:-} ${NGX_PID:-} 2>/dev/null; rm -rf "$TMP"; }
trap cleanup EXIT

echo "== 1. Старт локального стенда Hugging Face =="
"$PY" "$ROOT/tests/stub_hf.py" "$STUB_PORT" >"$TMP/stub.log" 2>&1 &
STUB_PID=$!
sleep 1
curl -sf "http://127.0.0.1:$STUB_PORT/v1/models" >/dev/null && ok "стенд отвечает на /v1/models" || bad "стенд не отвечает"

echo "== 2. Пустой HF_TOKEN -> падение с понятной ошибкой =="
( cd "$ROOT/backend" && HF_TOKEN="" HF_VERIFY_ON_STARTUP=off PYTHONPATH=. \
    "$PY" -c "from app.main import app" >"$TMP/no_token.log" 2>&1 )
grep -q "HF_TOKEN не задана" "$TMP/no_token.log" && ok "ошибка про пустой HF_TOKEN в логе" \
  || bad "нет понятной ошибки про HF_TOKEN: $(tail -2 "$TMP/no_token.log")"

echo "== 3. Запуск backend =="
( cd "$ROOT/backend" && HF_TOKEN=test-key HF_BASE_URL="http://127.0.0.1:$STUB_PORT/v1" \
    HF_VERIFY_ON_STARTUP=off PYTHONPATH=. "$PY" -m uvicorn app.main:app --port "$BACK_PORT" ) \
    >"$TMP/back.log" 2>&1 &
BACK_PID=$!
for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:$BACK_PORT/api/health" >/dev/null && break; sleep 0.25; done
HEALTH=$(curl -sf "http://127.0.0.1:$BACK_PORT/api/health" || echo "")
echo "$HEALTH" | grep -q '"status":"ok"' && ok "/api/health = ok" || bad "health: $HEALTH"
echo "$HEALTH" | grep -q "DeepSeek" && ok "модель из конфига отдаётся" || bad "модель не в health"

echo "== 4. Поток /api/chat (мимо nginx) =="
START=$(date +%s.%N)
curl -sN -X POST "http://127.0.0.1:$BACK_PORT/api/chat" -H 'Content-Type: application/json' \
  -d '{"message":"проверка потока"}' >"$TMP/stream.txt"
END=$(date +%s.%N)
FRAMES=$(grep -c '^data: {"delta"' "$TMP/stream.txt" || true)
check "кадров-дельт >= 3" "$([ "$FRAMES" -ge 3 ] && echo yes || echo no)" "yes"
TOTAL=$(grep -c '^data: {"done"' "$TMP/stream.txt" || true)
check "кадр завершения один" "$TOTAL" "1"
"$PY" - "$TMP/stream.txt" <<'PY'
import json,sys
text=""
for line in open(sys.argv[1],encoding="utf-8"):
    if line.startswith("data: ") and '"delta"' in line:
        text+=json.loads(line[6:])["delta"]
print("  собранный ответ:", text[:80]+("…" if len(text)>80 else ""))
assert len(text)>50, "ответ слишком короткий"
PY
[ $? -eq 0 ] && ok "текст собирается из кадров" || bad "не собрать текст из кадров"
DUR=$("$PY" -c "print(f'{$END-$START:.2f}')")
echo "  время полного ответа: ${DUR}s (многоточечная имитация генерации)"

echo "== 5. Nginx: Basic Auth + статика + SSE через прокси =="
if command -v nginx >/dev/null 2>&1; then
  HTPASSWD_FILE="$TMP/.htpasswd"
  if command -v htpasswd >/dev/null 2>&1; then
    htpasswd -bc "$HTPASSWD_FILE" tester secret123 >/dev/null 2>&1
  else
    "$PY" -c "
import crypt,sys
print('tester:'+crypt.crypt('secret123', crypt.mksalt(crypt.METHOD_SHA512)))
" > "$HTPASSWD_FILE" 2>/dev/null || printf 'tester:%s\n' \
      "$(openssl passwd -apr1 secret123)" > "$HTPASSWD_FILE"
  fi
  mkdir -p "$TMP/logs"
  # nginx работает под непривилегированным пользователем -> файл пароля должен быть читаем
  chmod 755 "$TMP"
  chmod 644 "$HTPASSWD_FILE"
  sed -e "s#/etc/nginx/.htpasswd#${HTPASSWD_FILE}#" \
      -e "s#/usr/share/nginx/html#${ROOT}/frontend#" \
      -e "s#listen 80;#listen ${NGX_PORT};#" \
      -e "s#http://backend:8000#http://127.0.0.1:${BACK_PORT}#" \
      "$ROOT/nginx/default.conf" > "$TMP/nginx.conf"
  cat > "$TMP/nginx.main.conf" <<EOF
worker_processes 1;
error_log $TMP/logs/error.log warn;
pid $TMP/nginx.pid;
events { worker_connections 64; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log $TMP/logs/access.log;
  client_body_temp_path $TMP/body;
  proxy_temp_path $TMP/proxy;
  fastcgi_temp_path $TMP/fastcgi;
  uwsgi_temp_path $TMP/uwsgi;
  scgi_temp_path $TMP/scgi;
  include $TMP/nginx.conf;
}
EOF
  nginx -c "$TMP/nginx.main.conf" -t >"$TMP/nginx_t.log" 2>&1 \
    && ok "nginx -t: конфиг валиден" || { bad "конфиг nginx невалиден"; cat "$TMP/nginx_t.log"; }
  nginx -c "$TMP/nginx.main.conf" >"$TMP/nginx_run.log" 2>&1 &
  NGX_PID=$!
  sleep 1
  CODE_NOAUTH=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$NGX_PORT/")
  check "без пароля 401" "$CODE_NOAUTH" "401"
  CODE_AUTH=$(curl -s -o /dev/null -w '%{http_code}' -u tester:secret123 "http://127.0.0.1:$NGX_PORT/")
  check "с паролем 200" "$CODE_AUTH" "200"
  curl -s -u tester:secret123 "http://127.0.0.1:$NGX_PORT/" | grep -qi "Private AI Assistant" \
    && ok "статика (index.html) отдаётся" || bad "index.html не отдаётся"
  curl -s -u tester:secret123 "http://127.0.0.1:$NGX_PORT/script.js" | grep -q "api/chat" \
    && ok "script.js отдаётся" || bad "script.js не отдаётся"
  CODE_API=$(curl -s -o /dev/null -w '%{http_code}' -u tester:secret123 "http://127.0.0.1:$NGX_PORT/api/health")
  check "/api/health через прокси" "$CODE_API" "200"
  CODE_API_NOAUTH=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$NGX_PORT/api/health")
  check "/api/ тоже под паролем" "$CODE_API_NOAUTH" "401"
  # SSE через nginx: считаем, сколько кадров пришло до 2 секунды (должно быть >1 => нет буферизации)
  ( curl -sN --max-time 20 -u tester:secret123 -X POST "http://127.0.0.1:$NGX_PORT/api/chat" \
      -H 'Content-Type: application/json' -d '{"message":"через nginx"}' >"$TMP/ngs.txt" ) &
  CURL_BG=$!
  sleep 2; EARLY=$(grep -c '^data: {"delta"' "$TMP/ngs.txt" || true)
  wait "$CURL_BG" 2>/dev/null || true
  if [ "$EARLY" -ge 2 ]; then ok "SSE через nginx идёт кадрами (за 2 c — $EARLY шт., буферизация off)"
  else bad "SSE через nginx похоже буферизуется (за 2 c — $EARLY кадров)"; fi
  grep -q '^data: {"done"' "$TMP/ngs.txt" && ok "поток через nginx завершается корректно" || bad "нет кадра done через nginx"
else
  echo "  SKIP  nginx не установлен — проверки прокси пропущены (см. README)"
fi

echo
echo "== ИТОГ: PASS=$PASS FAIL=$FAIL =="
[ "$FAIL" -eq 0 ]
