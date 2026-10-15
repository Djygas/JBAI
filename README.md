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
├── frontend-themes/           # готовые варианты оформления (одинаковая логика, разный вид)
│   ├── business/              # деловая: светлая, сайдбар, синий акцент
│   ├── hacker/                # терминал: матрица, моно-шрифт, ASCII-логотип
│   └── jb/                    # фирменная: #6a2bff · #9d00ff · #00e5ff, стекло
├── preview.html               # витрина: три темы рядом (открыть в браузере)
├── use_theme.sh               # переключение темы: bash use_theme.sh <business|hacker|jb>
├── nginx/
│   ├── Dockerfile
│   └── default.conf           # auth_basic + прокси + статика
├── tests/
│   ├── stub_hf.py             # локальный «Hugging Face»: проверка стрима без ключа
│   ├── smoke.sh               # автоматические проверки (health, auth, SSE)
│   ├── run_local.sh           # прогон автопроверок
│   ├── serve_local.sh         # локальный стек без docker (стенд + backend + nginx)
│   ├── stub_theme.py          # стенд с «живым» ответом (абзацы + код) для скриншотов тем
│   ├── themes_shot.py         # скриншоты всех тем: десктоп + мобильный вид
│   ├── theme_check.py         # автопроверка тем (30 проверок: переполнение, консоль, поток)
│   └── ui_check.py            # проверка интерфейса в браузере + скриншоты
├── docker-compose.yml
├── setup.sh                   # первичная настройка на VPS
├── .env.example
└── README.md
```

## Быстрый старт на VPS

Требуется Ubuntu/Debian с установленным Docker и docker compose plugin.

```bash
# 1. забрать проект
git clone https://github.com/<ваш-аккаунт>/private-ai-assistant.git
cd private-ai-assistant

# 2. ключ и пароль + запуск — одной командой
bash setup.sh          # сам создаст .env, попросит HF_TOKEN и логин/пароль, поднимет контейнеры

# открыть в браузере: http://<IP-сервера>   -> браузер спросит логин/пароль
```

Вручную (если не хотите скрипт):

```bash
cp .env.example .env && nano .env      # впишите HF_TOKEN=hf_...
sudo apt install -y apache2-utils
sudo htpasswd -c "$PWD/nginx/.htpasswd" ваш_логин    # затем без -c: sudo htpasswd "$PWD/nginx/.htpasswd" второй_логин
sudo chmod 644 nginx/.htpasswd         # чтобы nginx в контейнере смог прочитать файл
docker compose up -d --build
```

Логи и проверка:

```bash
docker compose logs -f backend          # видно, что HF_TOKEN найден (маска) и ключ принят
docker exec -it private-ai-backend printenv HF_TOKEN | head -c 12   # ключ дошёл до контейнера
curl -u логин:пароль http://127.0.0.1/api/health
```

## Оформление: три готовые темы

Внешний вид меняется отдельно от логики: во всех темах один и тот же `script.js` (поток SSE, история, стоп, очистка),
различаются только `index.html` + `style.css`. Тема может переопределить подписи статуса через
`window.JBAI_LABELS` (например, терминал пишет `state: готов`).

| Тема | Вид | Когда уместна |
|---|---|---|
| `business` | светлый кабинет: сайдбар с разделами, синий акцент, аккуратные пузыри | работа с клиентами, бизнес-задачи, «офисная» подача |
| `hacker` | терминал: моно-шрифт, матричный фон, сканлайны, ASCII-логотип, приглашение `root@jbai:~$` | личное использование, техно-подача, для своих |
| `jb` | фирменная: `#6a2bff · #9d00ff · #00e5ff`, стекло, свечение, блок проектов | публичная страница-витрина проектов JBVPN / JBAI / автоматизация |

Посмотреть все три рядом: откройте `preview.html` (три уменьшенные копии со ссылками на полный размер).

Переключить активную тему:

```bash
bash use_theme.sh business     # или: hacker | jb
docker compose up -d --build nginx     # если статика уже в образе; при volume-монтировании достаточно обновить страницу
```

Скриншоты (десктоп 1440×900 и мобильный 390×844):

```bash
PYTHON=/path/to/venv/bin/python python3 tests/themes_shot.py   # снимает все темы -> screenshots/
python3 tests/theme_check.py                                   # 30 проверок: палитра, поток, переполнение, консоль
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

Проверка полного стека (nginx с Basic Auth) одной командой — 16 автопроверок:

```bash
PYTHON=/путь/к/python bash tests/run_local.sh     # 401/200 Basic Auth, статика, прокси, SSE без буферизации
python3 tests/serve_local.sh &                    # поднять локальный стек на :8090 (tester/secret123)
python3 tests/ui_check.py                         # открыть UI в браузере и снять скриншоты
```

## Чеклист приёмки

- [x] `docker compose up --build` на чистой Ubuntu поднимает проект
- [x] браузер запрашивает логин/пароль (Basic Auth на все запросы, включая /api/)
- [x] интерфейс чата загружается после авторизации
- [x] сообщения приходят потоком (SSE), а не одним куском после паузы
- [x] `docker exec -it private-ai-backend printenv HF_TOKEN` показывает ключ
- [x] `.htpasswd` и `.env` отсутствуют в git-истории (см. `.gitignore`, каталог `nginx/.gitignore`)
- [x] три темы оформления проходят автопроверки (`tests/theme_check.py`, 30 проверок) и переключаются `use_theme.sh`

## Репозиторий на GitHub

Проект уже лежит в приватном репозитории: **https://github.com/Djygas/JBAI** (ветка `main`).

```bash
git clone https://github.com/Djygas/JBAI.git
cd JBAI
bash setup.sh
```

Как запушить изменения самому:

```bash
git add <файлы>
git commit -m "что изменил"
git push                              # токен спросят вместо пароля (PAT со scope repo)

# новый приватный репозиторий с нуля:
git remote add origin https://github.com/<ваш-аккаунт>/<репозиторий>.git
git push -u origin main
```

Если правите `.github/workflows/*`, токену нужен ещё и scope **workflow** (иначе GitHub отклонит push
с «refusing to allow a Personal Access Token to create or update workflow»).

Проверить, что секретов нет в истории:

```bash
# в списке файлов не должно быть .env и nginx/.htpasswd (важен якорь $: .env.example — норма)
git log --all --name-only --pretty=format: | sort -u | grep -x -E '\.env|nginx/\.htpasswd' \
  && echo "ВНИМАНИЕ: секрет в истории!" || echo "PASS: секретов в истории нет"
```

## Полезно знать

- **Порт 80 занят** (nginx на хосте) — поменяйте в `docker-compose.yml` на `"8080:80"` и открывайте `http://IP:8080`.
- **Ответ «залипает» и приходит целиком в конце** — значит где-то включена буферизация: в конфиге nginx уже стоит `proxy_buffering off`, плюс backend отдаёт `X-Accel-Buffering: no`. Если добавляете внешний reverse-proxy (Cloudflare/Traefik) — отключите буферизацию и там.
- **401 / «Ключ HF_TOKEN отклонён»** — ключ отозван или без прав на Inference Providers. Поправьте `.env` и `docker compose up -d`.
- **Ответ приходит «402: закончились кредиты»** — на стороне провайдера кончились кредиты (не ошибка приложения). Либо пополнить баланс провайдера, либо сменить провайдера одной строкой: `HF_BASE_URL` + `HF_MODEL` + `HF_TOKEN` (любой OpenAI-совместимый, например OpenRouter/Groq/Gemini).
- **Контейнер не стартует с ошибкой про HF_TOKEN** — так и задумано: без ключа приложение не поднимается (см. `backend/app/security.py`). Проверьте, что `.env` рядом с `docker-compose.yml` и в нём заполнен `HF_TOKEN`.
- **`version` is obsolete** — предупреждение docker compose о ключе `version: "3.8"`; оставлен намеренно для совместимости со старыми установками, работе не мешает.
- **HTTPS** — Basic Auth по http передаёт пароль в открытом виде. Для доступа из интернета поставьте перед контейнером TLS (Caddy/Traefik) или подключите Let's Encrypt к nginx.
- Модель меняется одной строкой в `.env` (`HF_MODEL`) — список доступных: `curl -H "Authorization: Bearer $HF_TOKEN" https://router.huggingface.co/v1/models`.
