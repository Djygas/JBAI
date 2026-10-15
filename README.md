# Private AI Assistant

Личный приватный ИИ-чат: **FastAPI + Hugging Face router (OpenAI-совместимый) + Nginx с Basic Auth**, запуск в Docker одной командой.

Проект рассчитан **на одного пользователя**: никакой регистрации, балансов и подсчёта токенов — только ключ на входе (Basic Auth) и приватный чат.

```
frontend (static)  ->  nginx :80  --(Basic Auth, /api/ proxy, SSE без буферизации)-->  backend :8000  ->  router.huggingface.co
```

## Структура

```
private-ai-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI: CORS, роутеры, проверка ключа на старте
│   │   ├── config.py          # настройки из переменных окружения
│   │   ├── security.py        # проверка HF_TOKEN (пустой -> падение с понятной ошибкой)
│   │   └── routes/chat.py     # POST /api/chat -> SSE-стрим
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js              # fetch + разбор SSE, без секретов
├── nginx/
│   ├── Dockerfile
│   └── default.conf           # auth_basic + прокси + статика
├── tests/
│   ├── stub_hf.py             # локальный «Hugging Face»: проверка стрима без ключа
│   ├── smoke.sh               # автоматические проверки (health, auth, SSE)
│   └── screens.py             # скриншоты интерфейса (playwright)
├── docker-compose.yml
├── .env.example
└── README.md
```

## Быстрый старт на VPS

Требуется Ubuntu/Debian с установленным Docker и docker compose plugin.

```bash
# 1. забрать проект
git clone https://github.com/<ваш-аккаунт>/private-ai-assistant.git
cd private-ai-assistant

# 2. настройки и ключ
cp .env.example .env
nano .env          # впишите HF_TOKEN=hf_... (https://huggingface.co/settings/tokens)

# 3. пароль для входа в веб-интерфейс (Basic Auth)
sudo apt install -y apache2-utils
sudo htpasswd -c "$PWD/nginx/.htpasswd" ваш_логин     # один раз, затем без -c: sudo htpasswd "$PWD/nginx/.htpasswd" второй_логин

# 4. поднять
docker compose up -d --build

# 5. открыть в браузере
#    http://<IP-сервера>   -> браузер спросит логин/пароль из шага 3
```

Логи и проверка:

```bash
docker compose logs -f backend          # видно, что HF_TOKEN найден (маска) и ключ принят
docker exec -it private-ai-backend printenv HF_TOKEN | head -c 12   # ключ дошёл до контейнера
curl -u логин:пароль http://127.0.0.1/api/health
```

## Обновление

```bash
git pull && docker compose up -d --build
```

## Разработка без Docker

Нужны `python3.12` и `nginx` локально (или проверяйте всё через compose).

```bash
# 1) стенд вместо Hugging Face (стримит ответ без ключа)
cd tests && python3 stub_hf.py 8081 &      # /v1/chat/completions

# 2) бэкенд с ключом-заглушкой, но на локальный роутер
cd ../backend
HF_TOKEN=test-key HF_BASE_URL=http://127.0.0.1:8081/v1 HF_VERIFY_ON_STARTUP=off \
  python3 -m uvicorn app.main:app --port 8000

# 3) проверка потока
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"привет"}'
```

Проверка полного стека (nginx с Basic Auth) выполняется скриптом:

```bash
bash tests/smoke.sh
```

## Чеклист приёмки

- [x] `docker compose up --build` на чистой Ubuntu поднимает проект
- [x] браузер запрашивает логин/пароль (Basic Auth на все запросы, включая /api/)
- [x] интерфейс чата загружается после авторизации
- [x] сообщения приходят потоком (SSE), а не одним куском после паузы
- [x] `docker exec -it private-ai-backend printenv HF_TOKEN` показывает ключ
- [x] `.htpasswd` и `.env` отсутствуют в git-истории (см. `.gitignore`, каталог `nginx/.gitignore`)

## Приватный репозиторий на GitHub

```bash
git init -b main
git add .
git commit -m "private AI assistant: fastapi + hf router + nginx basic auth"
# создать на github.com НОВЫЙ ПРИВАТНЫЙ репозиторий private-ai-assistant (без README/.gitignore)
git remote add origin git@github.com:<ваш-аккаунт>/private-ai-assistant.git
git push -u origin main
```

Проверить, что секретов нет в истории:

```bash
git log --all --name-only | grep -E '\.env|htpasswd' || echo "секретов в истории нет"
```

## Полезно знать

- **Порт 80 занят** (nginx на хосте) — поменяйте в `docker-compose.yml` на `"8080:80"` и открывайте `http://IP:8080`.
- **Ответ «залипает» и приходит целиком в конце** — значит где-то включена буферизация: в конфиге nginx уже стоит `proxy_buffering off`, плюс backend отдаёт `X-Accel-Buffering: no`. Если добавляете внешний reverse-proxy (Cloudflare/Traefik) — отключите буферизацию и там.
- **401 / «Ключ HF_TOKEN отклонён»** — ключ отозван или без прав на Inference Providers. Поправьте `.env` и `docker compose up -d`.
- **Контейнер не стартует с ошибкой про HF_TOKEN** — так и задумано: без ключа приложение не поднимается (см. `backend/app/security.py`). Проверьте, что `.env` рядом с `docker-compose.yml` и в нём заполнен `HF_TOKEN`.
- **`version` is obsolete** — предупреждение docker compose о ключе `version: "3.8"`; оставлен намеренно для совместимости со старыми установками, работе не мешает.
- **HTTPS** — Basic Auth по http передаёт пароль в открытом виде. Для доступа из интернета поставьте перед контейнером TLS (Caddy/Traefik) или подключите Let's Encrypt к nginx.
- Модель меняется одной строкой в `.env` (`HF_MODEL`) — список доступных: `curl -H "Authorization: Bearer $HF_TOKEN" https://router.huggingface.co/v1/models`.
