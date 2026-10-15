"""Настройки приложения. Все значения — из переменных окружения (.env).

Секретов в коде нет: ключ HF_TOKEN читается только из окружения и в логи не пишется целиком.
"""
import os
import pathlib

try:  # необязательная зависимость: удобно для локального запуска без docker
    from dotenv import load_dotenv

    for candidate in (pathlib.Path(__file__).resolve().parents[2] / ".env",
                      pathlib.Path(__file__).resolve().parents[1] / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
except ImportError:  # pragma: no cover
    pass


def _bool(name: str, default: str = "off") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "on", "true", "yes")


# --- Hugging Face (OpenAI-совместимый router) ---
HF_TOKEN: str = os.environ.get("HF_TOKEN", "").strip()
HF_BASE_URL: str = os.environ.get("HF_BASE_URL", "https://router.huggingface.co/v1").rstrip("/")
HF_MODEL: str = os.environ.get("HF_MODEL", "deepseek-ai/DeepSeek-V4-Pro")
HF_TIMEOUT: float = float(os.environ.get("HF_TIMEOUT", "120"))

# Проверка ключа при старте: наличие HF_TOKEN — обязательно (иначе приложение не поднимается),
# живая проверка ключа через router — по умолчанию включена; HF_STRICT_STARTUP=on делает
# отклонённый ключ (401) фатальной ошибкой запуска.
HF_VERIFY_ON_STARTUP: bool = _bool("HF_VERIFY_ON_STARTUP", "on")
HF_STRICT_STARTUP: bool = _bool("HF_STRICT_STARTUP", "off")

# --- Прочее ---
SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
SYSTEM_PROMPT: str = os.environ.get("SYSTEM_PROMPT", (
    "Ты — личный ИИ-ассистент владельца сервера. Отвечай по-русски, кратко и по делу. "
    "Код — в блоках с указанием языка."
))
MAX_MESSAGE_CHARS: int = int(os.environ.get("MAX_MESSAGE_CHARS", "16000"))
HISTORY_LIMIT: int = int(os.environ.get("HISTORY_LIMIT", "20"))

# CORS: по умолчанию фронтенд отдаёт тот же nginx, поэтому достаточно своего origin.
ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
