"""Напоминания: бот сам пишет пользователям раз в несколько часов.

Каждое сообщение содержит кнопку: по нажатию пользователь получает
ровно один кружок бесплатно (одна выдача на одно сообщение).

Расписание хранится в базе (ключ last_push_at), поэтому перезапуск бота
не сбрасывает таймер: следующая волна придёт в срок.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from .. import texts
from ..config import Config
from ..db import Database, iso
from ..keyboards import push_kb

log = logging.getLogger(__name__)

# Пауза между сообщениями, чтобы не поймать flood limit от Telegram.
SEND_DELAY = 0.05

# Ключ в таблице settings: когда последний раз рассылали.
LAST_PUSH_KEY = "last_push_at"

# Первая рассылка после самого первого запуска (если ещё ни разу не слали).
FIRST_PUSH_DELAY = 60


def _interval_seconds(cfg: Config) -> int:
    return max(1, cfg.notify_hours) * 3600


async def seconds_until_next(db: Database, cfg: Config) -> int:
    """Сколько ждать до следующей волны с учётом последней отправки."""
    raw = await db.get_setting(LAST_PUSH_KEY)
    if not raw:
        return FIRST_PUSH_DELAY

    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return FIRST_PUSH_DELAY

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    remaining = _interval_seconds(cfg) - elapsed
    return max(0, int(remaining))


async def notify_user(bot: Bot, db: Database, cfg: Config, user_id: int) -> bool:
    """Отправляет одно напоминание. True — если доставлено."""
    if await db.unseen_count(user_id, cfg.feed_include_own) == 0:
        return False  # нечего показывать — не тревожим зря

    message = random.choice(texts.PUSH_MESSAGES)
    notification_id = await db.create_notification(user_id, message[:40])

    try:
        await bot.send_message(
            user_id,
            message,
            reply_markup=push_kb(notification_id),
            disable_web_page_preview=True,
        )
        return True
    except TelegramRetryAfter as exc:
        log.warning("Flood limit, ждём %s сек", exc.retry_after)
        await asyncio.sleep(exc.retry_after)
        return False
    except TelegramForbiddenError:
        # Пользователь заблокировал бота — больше не пишем.
        await db.set_blocked(user_id, True)
        return False
    except Exception as exc:  # noqa: BLE001
        log.info("Не удалось отправить напоминание %s: %s", user_id, exc)
        return False


async def send_wave(bot: Bot, db: Database, cfg: Config, limit: int = 500) -> int:
    """Один круг рассылки. Возвращает число доставленных сообщений."""
    users = await db.push_recipients(limit=limit)
    sent = 0

    for user in users:
        if await notify_user(bot, db, cfg, user.user_id):
            sent += 1
        await asyncio.sleep(SEND_DELAY)

    if sent:
        log.info("Напоминания отправлены: %s из %s", sent, len(users))
    return sent


async def notification_loop(bot: Bot, db: Database, cfg: Config) -> None:
    """Фоновый цикл: ждёт по расписанию и рассылает напоминания."""
    log.info(
        "Напоминания включены: каждые %s ч (первая — %s сек)",
        cfg.notify_hours,
        await seconds_until_next(db, cfg),
    )

    while True:
        try:
            delay = await seconds_until_next(db, cfg)
            await asyncio.sleep(delay)

            await send_wave(bot, db, cfg)
            await db.set_setting(LAST_PUSH_KEY, iso())
        except asyncio.CancelledError:
            log.info("Цикл напоминаний остановлен")
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка в цикле напоминаний: %s", exc)
            await asyncio.sleep(60)