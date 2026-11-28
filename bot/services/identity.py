"""Имя бота для ссылок: берём из .env или спрашиваем у Telegram.

BOT_USERNAME в переменных не обязателен: если он не задан, имя один раз
запрашивается через getMe и запоминается на время работы процесса.
Так ссылки никогда не ломаются из-за незаполненной настройки.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..config import Config

log = logging.getLogger(__name__)

_cache: str = ""


async def bot_username(bot: Bot, cfg: Config) -> str:
    """Username бота без @. Пустая строка, если узнать не удалось."""
    global _cache

    if cfg.bot_username:
        return cfg.bot_username.lstrip("@")
    if _cache:
        return _cache

    try:
        me = await bot.get_me()
    except TelegramAPIError as exc:
        log.warning("Не удалось получить username бота: %s", exc)
        return ""

    _cache = (me.username or "").lstrip("@")
    if _cache:
        cfg.bot_username = _cache
    return _cache