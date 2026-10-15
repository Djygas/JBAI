#!/usr/bin/env bash
# Первичная настройка на VPS: создаёт .env, файл пароля и поднимает контейнеры.
# Запуск:  bash setup.sh
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker не установлен. Поставьте:  curl -fsSL https://get.docker.com | sh"
  exit 1
fi

# 1. .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан .env. Впишите HF_TOKEN (https://huggingface.co/settings/tokens) и запустите setup.sh снова:"
  echo "    nano .env"
  exit 1
fi
if grep -qE '^HF_TOKEN=(hf_x|$|hf_xxx)' .env || ! grep -qE '^HF_TOKEN=hf_' .env; then
  echo "В .env не заполнен HF_TOKEN — впишите ключ (строка вида HF_TOKEN=hf_...)."
  exit 1
fi

# 2. файл пароля для Basic Auth
if [ ! -f nginx/.htpasswd ]; then
  read -rp "Логин для входа в веб-интерфейс: " LOGIN
  read -rsp "Пароль: " PASSWORD; echo
  if command -v htpasswd >/dev/null 2>&1; then
    htpasswd -bc nginx/.htpasswd "$LOGIN" "$PASSWORD"
  else
    # запасной вариант: apr1-хеш на openssl (nginx его понимает)
    printf '%s:%s\n' "$LOGIN" "$(openssl passwd -apr1 "$PASSWORD")" > nginx/.htpasswd
  fi
  chmod 644 nginx/.htpasswd
  echo "Пароль сохранён в nginx/.htpasswd (в git не попадает — см. nginx/.gitignore)."
fi

# 3. запуск
docker compose up -d --build
echo
echo "Готово. Откройте http://$(hostname -I 2>/dev/null | awk '{print $1}')/ и войдите под созданным логином."
docker compose ps
