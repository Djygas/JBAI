#!/usr/bin/env python3
"""Проверка интерфейса в реальном браузере (Playwright) через nginx с Basic Auth.

Что проверяет:
  * сайт открывается только с логином/паролем (без них — 401, в браузере всплывает окно входа);
  * интерфейс чата рендерится;
  * сообщение уходит на /api/chat и ответ дорисовывается ПОТОКОВО (сначала короткий, потом длиннее);
  * сохраняет скриншоты (десктоп, мобильный, ответ модели).

Запуск:  python3 tests/ui_check.py            (нужен поднятый tests/serve_local.sh)
"""
import asyncio
import pathlib
import sys

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8090"
USER, PASSWORD = "tester", "secret123"
OUT = pathlib.Path("/tmp/jbai_shots")
PROMPT = "Коротко: что такое SSE?"


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ok = True

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])

        # 1) без логина/пароля — 401 и окно Basic Auth
        ctx_noauth = await browser.new_context()
        page = await ctx_noauth.new_page()
        resp = await page.goto(BASE, wait_until="domcontentloaded")
        print(f"  {'PASS' if resp.status == 401 else 'FAIL'}  без авторизации сервер отвечает 401 (получено {resp.status})")
        ok &= resp.status == 401
        await ctx_noauth.close()

        # 2) с логином/паролем — интерфейс
        ctx = await browser.new_context(
            http_credentials={"username": USER, "password": PASSWORD},
            viewport={"width": 1280, "height": 800},
            locale="ru-RU",
        )
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        await page.goto(BASE, wait_until="networkidle")
        title = await page.title()
        print(f"  {'PASS' if 'Private AI Assistant' in title else 'FAIL'}  заголовок страницы: {title}")
        ok &= "Private AI Assistant" in title
        await page.screenshot(path=str(OUT / "01-чат-пустой.png"))

        # 3) отправляем сообщение и следим за потоковой отрисовкой
        await page.fill("#input", PROMPT)
        await page.click("#send")
        await page.wait_for_selector(".msg.assistant:last-child .bubble")
        lengths: list[int] = []
        for _ in range(40):
            text = await page.eval_on_selector_all(
                ".msg.assistant .bubble", "els => els[els.length-1].innerText"
            )
            lengths.append(len(text))
            if await page.is_visible("#stop") is False and len(text) > 40:
                break
            await page.wait_for_timeout(150)

        grew = [i for i, n in enumerate(lengths) if n > 0]
        growing = len(set(lengths)) > 2
        print(f"  {'PASS' if grew else 'FAIL'}  ответ появился в окне (замеров с текстом: {len(grew)})")
        print(f"  {'PASS' if growing else 'FAIL'}  текст дорисовывался постепенно (уникальных длин: {len(set(lengths))})")
        ok &= bool(grew) and growing

        await page.screenshot(path=str(OUT / "02-чат-ответ-потоком.png"))
        final_text = await page.eval_on_selector_all(
            ".msg.assistant .bubble", "els => els[els.length-1].innerText"
        )
        print(f"  полученный ответ: {final_text[:90]}…")
        ok &= len(final_text) > 40

        # 4) мобильный вид
        mobile = await browser.new_context(
            http_credentials={"username": USER, "password": PASSWORD},
            viewport={"width": 390, "height": 780},
            device_scale_factor=2,
            is_mobile=True, has_touch=True, locale="ru-RU",
        )
        mpage = await mobile.new_page()
        await mpage.goto(BASE, wait_until="networkidle")
        await mpage.fill("#input", "Проверка мобильной вёрстки")
        await mpage.click("#send")
        await mpage.wait_for_timeout(1500)
        await mpage.screenshot(path=str(OUT / "03-чат-мобильный.png"))

        if errors:
            print("  FAIL  ошибки в консоли браузера:")
            for e in errors[:5]:
                print("        ", e)
            ok = False
        else:
            print("  PASS  ошибок JS/CSS в консоли нет")

        await browser.close()

    print("\nСкриншоты:", ", ".join(sorted(x.name for x in OUT.glob("*.png"))))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
