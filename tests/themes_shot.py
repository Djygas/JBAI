#!/usr/bin/env python3
"""Скриншоты трёх тем JBAI через реальный стек: nginx (Basic Auth) -> backend -> стенд.

Запуск (из корня проекта):  python3 tests/themes_shot.py
Результат: /opt/workspace/private-ai-assistant/screenshots/*.png
"""
import os
import pathlib
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
THEMES = ["business", "hacker", "jb"]
OUT = ROOT / "screenshots"
D = pathlib.Path("/tmp/jbai_themes")
PORT = 8101
USER, PWD = "tester", "secret123"
PY = os.environ.get("PYTHON", "python3")


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=False,
                          capture_output=True, text=True, **kw)


def free_port(port: int) -> None:
    """Освободить порт от nginx прошлого прогона (в контейнере нет fuser/lsof)."""
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
        except OSError:
            continue
        if "nginx" in cmdline and str(D) in cmdline:
            sh(f"kill -9 {entry.name}")


def start_stack():
    D.mkdir(parents=True, exist_ok=True)
    (D / "logs").mkdir(exist_ok=True)
    sh("pkill -f stub_theme.py; pkill -f 'uvicorn app.main'; pkill -f themes.conf")
    free_port(PORT)                     # освободить порт от nginx прошлого прогона
    time.sleep(1.2)

    with open(D / "stub.log", "w") as f:
        subprocess.Popen([PY, str(ROOT / "tests/stub_theme.py"), "8082"], stdout=f, stderr=f)
    env = {**os.environ, "HF_TOKEN": "dev-key", "HF_BASE_URL": "http://127.0.0.1:8082/v1",
           "HF_VERIFY_ON_STARTUP": "off", "PYTHONPATH": "."}
    with open(D / "backend.log", "w") as f:
        subprocess.Popen([PY, "-m", "uvicorn", "app.main:app", "--port", "8004"],
                         cwd=ROOT / "backend", env=env, stdout=f, stderr=f)

    sh(f'htpasswd -bc {D}/.htpasswd {USER} {PWD}')
    os.chmod(D / ".htpasswd", 0o644)

    loc = "".join(
        f"    location /{t}/ {{ alias {ROOT}/frontend-themes/{t}/; index index.html; }}\n"
        for t in THEMES
    )
    (D / "themes.conf").write_text(f"""server {{
    listen {PORT};
    server_name _;
    auth_basic "JBAI";
    auth_basic_user_file {D}/.htpasswd;

{loc}
    location /api/ {{
        proxy_pass http://127.0.0.1:8004/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_buffering off;
        gzip off;
    }}
}}
""")
    (D / "nginx.main.conf").write_text(f"""worker_processes 1;
error_log {D}/logs/error.log warn;
pid {D}/nginx.pid;
events {{ worker_connections 64; }}
http {{
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log {D}/logs/access.log;
  client_body_temp_path {D}/body;
  proxy_temp_path {D}/proxy;
  fastcgi_temp_path {D}/fastcgi;
  uwsgi_temp_path {D}/uwsgi;
  scgi_temp_path {D}/scgi;
  include {D}/themes.conf;
}}
""")
    t = sh(f"nginx -c {D}/nginx.main.conf -t")
    if t.returncode != 0:
        print("NGINX CONFIG ERROR:", t.stderr or t.stdout)
        sys.exit(1)
    r = sh(f"nginx -c {D}/nginx.main.conf")
    print("nginx:", (r.stderr or r.stdout or "started").strip())

    for _ in range(60):
        h = sh(f"curl -sf -u {USER}:{PWD} http://127.0.0.1:{PORT}/api/health")
        if h.returncode == 0 and h.stdout.strip():
            print("stack up:", h.stdout.strip()[:120])
            return
        time.sleep(0.25)
    print("stack did not come up; backend log:")
    print((D / "backend.log").read_text()[-1500:])
    sys.exit(1)


def stop_stack():
    sh(f"kill $(cat {D}/nginx.pid) 2>/dev/null; pkill -f stub_theme.py; pkill -f 'uvicorn app.main'")


def stack_up():
    h = sh(f"curl -sf -u {USER}:{PWD} http://127.0.0.1:{PORT}/api/health")
    return h.returncode == 0 and h.stdout.strip()


def main():
    OUT.mkdir(exist_ok=True)
    start_stack()
    shots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none"])
        for theme in THEMES:
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                device_scale_factor=2,
                http_credentials={"username": USER, "password": PWD},
                locale="ru-RU",
            )
            page = ctx.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/{theme}/", wait_until="load")
            page.wait_for_timeout(900)

            page.fill("#input", "Автоматизируй приём заявок: Telegram и сайт → таблица, "
                                "утренняя сводка по оплатам")
            page.click("#send")
            try:
                page.wait_for_selector(".status.busy", state="attached", timeout=8000)
                page.wait_for_selector(".status.busy", state="detached", timeout=25000)
            except Exception as e:  # noqa: BLE001
                print(f"  [{theme}] warning: {e}")
            page.wait_for_timeout(700)

            msgs = page.eval_on_selector_all(".msg", "els => els.length")
            text = page.inner_text("#chat")[-200:]
            page.screenshot(path=OUT / f"theme_{theme}_desktop.png")

            m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                    http_credentials={"username": USER, "password": PWD}, locale="ru-RU")
            mp = m.new_page()
            mp.goto(f"http://127.0.0.1:{PORT}/{theme}/", wait_until="load")
            mp.wait_for_timeout(700)
            mp.fill("#input", "Как автоматизировать отчёты?")
            mp.click("#send")
            try:
                mp.wait_for_selector(".status.busy", state="detached", timeout=20000)
            except Exception:  # noqa: BLE001
                pass
            mp.wait_for_timeout(600)
            mp.screenshot(path=OUT / f"theme_{theme}_mobile.png")
            m.close()

            shots.append(theme)
            print(f"  [{theme}] msg={msgs} tail={text!r}")
            ctx.close()
        browser.close()

    sh(f"kill $(cat {D}/nginx.pid) 2>/dev/null")
    print("screenshots:", sorted(x.name for x in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
