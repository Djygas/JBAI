#!/usr/bin/env python3
"""Локальный стенд «Hugging Face router» для проверки потока БЕЗ реального ключа.

Реализует минимум OpenAI-совместимого API:
    GET  /v1/models              -> {"data":[{"id": ...}]}
    POST /v1/chat/completions    -> SSE-поток чанков (stream=true)

Запуск:  python3 tests/stub_hf.py 8081
Затем:   HF_TOKEN=test HF_BASE_URL=http://127.0.0.1:8081/v1 HF_VERIFY_ON_STARTUP=off \
             python3 -m uvicorn app.main:app --port 8000   (из каталога backend/)
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "deepseek-ai/DeepSeek-V4-Pro"
REPLY = ("Проверка потока пройдена. Этот ответ собран из отдельных кадров SSE — "
         "значит прокси и фронтенд отдают данные по мере поступления, а не одним куском.")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # тише в консоли
        pass

    def _json(self, code: int, payload: dict) -> None:
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
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}

        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            words = REPLY.split(" ")
            try:
                for i, w in enumerate(words):
                    piece = w + (" " if i < len(words) - 1 else "")
                    chunk = {"choices": [{"delta": {"content": piece}, "index": 0, "finish_reason": None}]}
                    self._chunk(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
                    time.sleep(0.12)          # имитация генерации по токенам
                self._chunk('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
                self._chunk("data: [DONE]\n\n")
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self._json(200, {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "model": MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY},
                         "finish_reason": "stop"}],
        })

    def _chunk(self, text: str) -> None:
        data = text.encode()
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    print(f"stub HF router on http://127.0.0.1:{port}/v1  (model {MODEL})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
