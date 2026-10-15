"""Эндпоинт /api/chat: приём сообщения и потоковый ответ модели (SSE).

Формат потока (text/event-stream), кадры:
    data: {"delta": "кусок текста"}
    data: {"done": true, "model": "..."}
    data: {"error": "текст ошибки"}
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .. import config

log = logging.getLogger("jbai.chat")
router = APIRouter(prefix="/api", tags=["chat"])

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=config.HF_BASE_URL,
            api_key=config.HF_TOKEN,
            timeout=config.HF_TIMEOUT,
        )
    return _client


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=config.MAX_MESSAGE_CHARS)
    history: list[dict] = Field(default_factory=list)


def frame(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    if not config.HF_TOKEN:
        raise HTTPException(500, "HF_TOKEN не задан — сервер не настроен")

    messages = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    for m in req.history[-config.HISTORY_LIMIT:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            messages.append({"role": m["role"], "content": m["content"][:config.MAX_MESSAGE_CHARS]})
    messages.append({"role": "user", "content": req.message})

    async def gen():
        try:
            stream = await client().chat.completions.create(
                model=config.HF_MODEL, messages=messages, stream=True, temperature=0.3,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                piece = chunk.choices[0].delta.content
                if piece:
                    yield frame({"delta": piece})
            yield frame({"done": True, "model": config.HF_MODEL})
        except Exception as e:
            log.exception("ошибка провайдера модели")
            msg = str(e) or type(e).__name__
            if "401" in msg or "Unauthorized" in msg:
                msg = "Ключ HF_TOKEN отклонён (401). Проверьте .env на сервере."
            elif "Connection error" in msg or "Connect" in msg or "Timeout" in msg or "timed out" in msg:
                msg = ("Нет связи с Hugging Face router. Проверьте интернет/DNS на сервере и "
                       f"доступность {config.HF_BASE_URL}.")
            elif "404" in msg:
                msg = (f"Модель {config.HF_MODEL} недоступна на router (404). "
                       "Проверьте название модели в .env (HF_MODEL).")
            elif "402" in msg or "remaining credits" in msg or "credits" in msg.lower():
                msg = ("На аккаунте Hugging Face закончились кредиты Inference Providers (402). "
                       "Ключ рабочий, но за вызовы моделей нужно платить: пополните баланс на "
                       "https://huggingface.co/settings/billing либо укажите в .env другой "
                       "OpenAI-совместимый провайдер (HF_BASE_URL / HF_MODEL / HF_TOKEN).")
            elif "429" in msg or "rate limit" in msg.lower():
                msg = ("Провайдер модели ограничил частоту запросов (429). Подождите немного "
                       "и повторите — либо проверьте лимиты аккаунта на huggingface.co/settings/billing.")
            yield frame({"error": msg})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # nginx не должен копить поток в буфере
        },
    )
