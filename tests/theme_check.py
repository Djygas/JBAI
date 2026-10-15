#!/usr/bin/env python3
"""Автопроверка трёх тем: нет горизонтального переполнения, нет ошибок в консоли,
блок кода отрендерился, ответ дошёл, палитра темы реально применилась.

Стенд должен быть уже поднят: python3 tests/themes_shot.py (поднимает nginx+backend+stub)
Запуск: python3 tests/theme_check.py
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

import themes_shot as stand  # noqa: E402  (лежит рядом, в tests/)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "screenshots"
PORT, USER, PWD = 8101, "tester", "secret123"
THEMES = ["business", "hacker", "jb"]
EXPECT_BG = {"business": "rgb(244, 246, 251)", "hacker": "rgb(5, 7, 10)", "jb": "rgb(8, 5, 15)"}
EXPECT_READY = {"business": "готов", "hacker": "state: готов", "jb": "на связи"}

fails = []


def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


if not stand.stack_up():
    print("стенд не поднят — запускаю (nginx + backend + стенд-модель)…")
    stand.start_stack()

with sync_playwright() as p:
    b = p.chromium.launch()
    for theme in THEMES:
        print(f"[{theme}]")
        ctx = b.new_context(viewport={"width": 1440, "height": 900},
                            http_credentials={"username": USER, "password": PWD}, locale="ru-RU")
        page = ctx.new_page()
        errors, failed_req = [], []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed_req.append(f"{r.url} {r.failure}"))

        page.goto(f"http://127.0.0.1:{PORT}/{theme}/", wait_until="load")
        page.wait_for_timeout(700)

        bg_color, bg_image = page.evaluate(
            "[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.body).backgroundImage]")
        if theme == "jb":   # фон задан градиентом, backgroundColor прозрачный
            check("radial-gradient" in bg_image, f"палитра темы применилась (фон-градиент: {bg_image[:48]}…)")
        else:
            check(bg_color == EXPECT_BG[theme], f"палитра темы применилась ({bg_color})")

        page.fill("#input", "Автоматизируй приём заявок: Telegram и сайт → таблица")
        page.click("#send")
        try:
            page.wait_for_selector(".status.busy", state="detached", timeout=25000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(500)

        check(page.eval_on_selector_all(".msg", "e => e.length") == 3, "3 сообщения (приветствие + вопрос + ответ)")
        check("Ожидаемый эффект" in page.inner_text("#chat"), "ответ ассистента дошёл целиком")
        check(page.eval_on_selector_all(".msg.assistant .bubble pre code", "e => e.length") == 1,
              "блок кода отрендерился как <pre><code>")

        ready = page.inner_text("#status").strip()
        check(ready == EXPECT_READY[theme], f"подпись статуса темы: «{ready}» (ждём «{EXPECT_READY[theme]}»)")

        ov = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check(ov <= 1, f"нет горизонтального переполнения (переполнение {ov}px)")

        cur = page.eval_on_selector(".msg.assistant .bubble", "e => getComputedStyle(e).cursor")
        check(cur == "auto", "курсор потока убран после завершения")
        check(not page.eval_on_selector(".msg.assistant .bubble", "e => e.classList.contains('cursor')"),
              "мигающий курсор снят по окончании ответа")

        check(not errors, f"консоль без ошибок ({errors[:2]})")
        check(not failed_req, f"нет упавших запросов ({failed_req[:2]})")

        (OUT / "checks").mkdir(exist_ok=True)
        page.screenshot(path=OUT / "checks" / f"{theme}_after_check.png")
        ctx.close()
    b.close()

print()
print("ИТОГО:", "все проверки пройдены" if not fails else f"{len(fails)} провал(ов): {fails}")
stand.stop_stack()
sys.exit(1 if fails else 0)
