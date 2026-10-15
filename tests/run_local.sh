#!/usr/bin/env bash
# Локальный прогон автопроверок без docker: убирает зависшие процессы и запускает smoke.sh.
# Использование:  PYTHON=/путь/к/python bash tests/run_local.sh
set -u
pkill -f "stub_hf.py" 2>/dev/null || true
pkill -f "uvicorn app.main" 2>/dev/null || true
pkill -f "nginx -c /tmp" 2>/dev/null || true
sleep 1
export PYTHON="${PYTHON:-python3}"
exec timeout 180 bash "$(dirname "$(readlink -f "$0")")/smoke.sh"
