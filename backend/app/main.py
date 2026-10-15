"""Точка входа FastAPI: настройки, CORS, роутеры, проверка ключа HF на старте."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, security
from .routes import chat

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("jbai")

# Падаем сразу при импорте, если ключа нет: понятная ошибка в логе вместо «тихого» 500 на запросе.
security.require_token()


@asynccontextmanager
async def lifespan(app: FastAPI):
    status = security.verify_hf_token()   # пустой HF_TOKEN -> приложение не поднимется
    log.info("Проверка ключа HF завершена: %s", status)
    yield
    log.info("Остановка")


app = FastAPI(title="Private AI Assistant", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(chat.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": config.HF_MODEL,
        "base_url": config.HF_BASE_URL,
        "warning": security.startup_warning(),
    }


@app.exception_handler(Exception)
async def unhandled(request, exc):  # pragma: no cover
    log.exception("необработанная ошибка")
    return JSONResponse({"detail": str(exc)}, status_code=500)
