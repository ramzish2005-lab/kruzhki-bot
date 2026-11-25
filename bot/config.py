"""Загрузка и валидация конфигурации из .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class ConfigError(RuntimeError):
    """Конфигурация заполнена неверно."""


@dataclass(frozen=True)
class Sponsor:
    """Рекламный канал, на который нужно подписаться за бонусные просмотры."""

    chat_id: int
    url: str
    title: str


@dataclass
class Config:
    """Настройки бота.

    Не frozen: часть значений (лимиты, цены) админ меняет прямо в Telegram,
    и изменения должны действовать сразу, без перезапуска.
    """
    bot_token: str
    admin_ids: tuple[int, ...]
    main_channel_id: int
    main_channel_url: str
    storage_channel_id: int | None
    free_views: int
    bonus_views: int
    sponsors: tuple[Sponsor, ...]
    pay_pack_size: int
    pay_pack_stars: int
    pay_pack_rub: int
    payment_mode: str
    provider_token: str
    db_path: Path
    feed_include_own: bool
    source_channel_id: int | None = None

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _required(name: str) -> str:
    value = _env(name)
    if value is None:
        raise ConfigError(f"Не задана переменная {name} в .env (см. .env.example)")
    return value


def _int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должна быть целым числом, получено: {raw!r}") from exc


def _parse_id_list(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return ()
    result: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.append(int(chunk))
        except ValueError as exc:
            raise ConfigError(f"Ожидался числовой id, получено: {chunk!r}") from exc
    return tuple(result)


def _parse_sponsors(raw: str | None) -> tuple[Sponsor, ...]:
    if not raw:
        return ()
    sponsors: list[Sponsor] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [part.strip() for part in chunk.split("|")]
        if len(parts) not in (2, 3):
            raise ConfigError(
                "Формат SPONSORS: id|https://t.me/link|Название, элементы через запятую"
            )
        try:
            chat_id = int(parts[0])
        except ValueError as exc:
            raise ConfigError(f"id канала-спонсора должен быть числом: {parts[0]!r}") from exc
        title = parts[2] if len(parts) == 3 else f"Канал {len(sponsors) + 1}"
        sponsors.append(Sponsor(chat_id=chat_id, url=parts[1], title=title))
    return tuple(sponsors)


def load_config() -> Config:
    payment_mode = (_env("PAYMENT_MODE") or "stars").lower()
    if payment_mode not in ("stars", "provider"):
        raise ConfigError("PAYMENT_MODE должен быть 'stars' или 'provider'")

    provider_token = _env("PROVIDER_TOKEN") or ""
    if payment_mode == "provider" and not provider_token:
        raise ConfigError("Для PAYMENT_MODE=provider нужен PROVIDER_TOKEN")

    db_path = Path(_env("DB_PATH") or "data/bot.db")
    if not db_path.is_absolute():
        # На хостинге (Railway) удобно монтировать volume в /data.
        root = Path(_env("DATA_DIR") or BASE_DIR)
        db_path = root / db_path

    admin_ids = _parse_id_list(_env("ADMIN_IDS"))
    if not admin_ids:
        raise ConfigError("ADMIN_IDS пуст: укажите свой Telegram id, иначе модерация недоступна")

    storage_raw = _env("STORAGE_CHANNEL_ID")
    source_raw = _env("SOURCE_CHANNEL_ID")

    return Config(
        bot_token=_required("BOT_TOKEN"),
        admin_ids=admin_ids,
        main_channel_id=int(_required("MAIN_CHANNEL_ID")),
        main_channel_url=_required("MAIN_CHANNEL_URL"),
        storage_channel_id=int(storage_raw) if storage_raw else None,
        free_views=_int("FREE_VIEWS", 10),
        bonus_views=_int("BONUS_VIEWS", 10),
        sponsors=_parse_sponsors(_env("SPONSORS")),
        pay_pack_size=_int("PAY_PACK_SIZE", 10),
        pay_pack_stars=_int("PAY_PACK_STARS", 35),
        pay_pack_rub=_int("PAY_PACK_RUB", 50),
        payment_mode=payment_mode,
        provider_token=provider_token,
        db_path=db_path,
        feed_include_own=(_env("FEED_INCLUDE_OWN") or "0") in ("1", "true", "yes"),
        source_channel_id=int(source_raw) if source_raw else None,
    )
