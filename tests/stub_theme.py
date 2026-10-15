#!/usr/bin/env python3
"""Стенд для скриншотов тем: отдаёт реалистичный ответ (абзацы + код + список), потоком SSE.

Запуск: python3 tests/stub_theme.py 8082
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "deepseek-ai/DeepSeek-V4-Pro"

REPLY = """Разберу задачу по шагам.

1. Собираем входящие заявки из Telegram и сайта в одну таблицу.
2. Ночью скрипт сверяет оплаты и помечает расхождения.
3. Утром вы получаете сводку в рабочий чат.

Базовый каркас на Python:

```python
import asyncio, httpx

async def collect(chat_id: int):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{API}/leads", params={"chat": chat_id})
    return r.json()["items"]
```

Ожидаемый эффект: ручная работа сокращается примерно на 6 часов в неделю.
Уточните, откуда заявки приходят сейчас — соберу схему под ваш случай."""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length or 0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        # режем поток по словам — как настоящая генерация по токенам
        for line in REPLY.split("\n"):
            words = line.split(" ")
            for i, w in enumerate(words):
                piece = w + (" " if i < len(words) - 1 else "")
                chunk = {"choices": [{"delta": {"content": piece}, "index": 0, "finish_reason": None}]}
                self._chunk(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
                time.sleep(0.02)
            chunk = {"choices": [{"delta": {"content": "\n"}, "index": 0, "finish_reason": None}]}
            self._chunk(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
        self._chunk('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
        self._chunk("data: [DONE]\n\n")
        self.wfile.write(b"0\r\n\r\n")

    def _chunk(self, text):
        data = text.encode()
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8082
    print(f"theme stub on http://127.0.0.1:{port}/v1", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
