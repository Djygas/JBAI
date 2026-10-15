"""Проверка ключа Hugging Face при старте приложения.

Правила:
  * HF_TOKEN пустой  -> приложение НЕ поднимается, в лог уходит понятная ошибка;
  * ключ есть, но router его отклоняет (401) -> предупреждение в лог; при HF_STRICT_STARTUP=on
    это тоже фатальная ошибка;
  * сетевые сбои при проверке не валят запуск (иначе VPS не поднимется без интернета).

Сам ключ в логи не попадает — печатается только маска вида `hf_ab…yz`.
"""
import logging

from . import config

log = logging.getLogger("jbai.security")

_startup_warning: str | None = None


class ConfigError(RuntimeError):
    """Неверная конфигурация — приложение не должно запускаться."""


def mask(token: str) -> str:
    if not token:
        return "(пусто)"
    if len(token) <= 10:
        return token[:2] + "…" + token[-2:]
    return f"{token[:5]}…{token[-3:]} (длина {len(token)})"


def require_token() -> None:
    """Fail-fast: вызывается на импорте приложения, чтобы контейнер не поднялся без ключа."""
    if not config.HF_TOKEN:
        raise ConfigError(
            "Переменная HF_TOKEN не задана. Скопируйте .env.example в .env и впишите ключ "
            "Hugging Face (hf_...) — приложение без ключа не запускается."
        )


def verify_hf_token() -> str:
    """Вызывается на старте приложения. Возвращает статус проверки."""
    global _startup_warning

    require_token()
    log.info("HF_TOKEN найден: %s", mask(config.HF_TOKEN))
    log.info("Провайдер: %s, модель по умолчанию: %s", config.HF_BASE_URL, config.HF_MODEL)

    if not config.HF_VERIFY_ON_STARTUP:
        return "skipped"

    try:
        import httpx

        r = httpx.get(
            f"{config.HF_BASE_URL}/models",
            headers={"Authorization": f"Bearer {config.HF_TOKEN}"},
            timeout=15,
        )
        if r.status_code == 401:
            msg = ("Ключ HF_TOKEN отклонён router'ом Hugging Face (401). Проверьте, что ключ "
                   "действующий и с правами на Inference Providers.")
            if config.HF_STRICT_STARTUP:
                raise ConfigError(msg)
            _startup_warning = msg
            log.warning(msg)
            return "unauthorized"
        if r.status_code >= 400:
            _startup_warning = f"router вернул HTTP {r.status_code} на проверке ключа"
            log.warning(_startup_warning)
            return f"http_{r.status_code}"
        log.info("Ключ принят router'ом: доступно моделей — %s",
                 len(r.json().get("data", [])) if r.headers.get("content-type", "").startswith("application/json") else "?")
        return "ok"
    except ConfigError:
        raise
    except Exception as e:  # сеть/таймаут — не считаем это ошибкой конфигурации
        _startup_warning = f"живая проверка ключа не выполнена: {type(e).__name__}: {e}"
        log.warning(_startup_warning)
        return "unreachable"


def startup_warning() -> str | None:
    return _startup_warning
