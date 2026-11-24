"""Проверка подписок и правила доступа к просмотрам.

Порядок гейтов:
  1. подписка на основной канал (проверяется вживую через getChatMember);
  2. баланс просмотров > 0;
  3. если баланс пуст и бонус ещё не выдавался — подписка на каналы-спонсоры;
  4. иначе — платный пакет.
"""

from __future__ import annotations

import logging
from enum import Enum

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..config import Config
from ..db import Database, User

log = logging.getLogger(__name__)


class Gate(str, Enum):
    """Что нужно от пользователя прямо сейчас."""

    OK = "ok"
    MAIN_SUB = "main_sub"
    SPONSORS = "sponsors"
    PAYMENT = "payment"
    BLOCKED = "blocked"


async def subscription_state(bot: Bot, chat_id: int, user_id: int) -> tuple[bool, bool]:
    """(подписан, канал доступен боту).

    Второе значение нужно, чтобы отличить «пользователь не подписан» от
    «канал недоступен/удалён» — во втором случае гейт не должен блокировать.
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramAPIError as exc:
        log.warning("get_chat_member chat=%s user=%s: %s", chat_id, user_id, exc)
        return False, False

    status = getattr(member, "status", None)
    if status in ("creator", "administrator", "member"):
        return True, True
    if status == "restricted" and bool(getattr(member, "is_member", False)):
        return True, True
    return False, True


async def is_subscribed(bot: Bot, chat_id: int, user_id: int) -> bool:
    """True, если пользователь состоит в чате/канале.

    Если канал недоступен боту, возвращаем True (fail-open), чтобы поломка
    канала не блокировала всех пользователей навсегда.
    """
    ok, _reachable = await subscription_state(bot, chat_id, user_id)
    return ok


async def check_main_subscription(bot: Bot, db: Database, cfg: Config, user_id: int) -> bool:
    """Проверяет подписку на основной канал и кэширует результат в БД."""
    ok = await is_subscribed(bot, cfg.main_channel_id, user_id)
    await db.set_main_sub(user_id, ok)
    return ok


async def any_reachable_sponsor(bot: Bot, cfg: Config) -> bool:
    """Есть ли хоть один канал-спонсор, до которого бот может достучаться."""
    for sponsor in cfg.sponsors:
        try:
            await bot.get_chat(sponsor.chat_id)
        except TelegramAPIError as exc:
            log.warning("Спонсор %s недоступен: %s", sponsor.chat_id, exc)
            continue
        return True
    return False


async def missing_sponsors(bot: Bot, cfg: Config, user_id: int) -> list[int]:
    """Список id спонсоров, на которые пользователь НЕ подписан.

    Каналы, до которых бот не может достучаться (удалён, бот не админ),
    отбрасываются: иначе пользователь застрянет на гейте навсегда.
    """
    missing: list[int] = []
    for sponsor in cfg.sponsors:
        ok, reachable = await subscription_state(bot, sponsor.chat_id, user_id)
        if not reachable:
            log.warning("Спонсор %s недоступен боту, пропускаю", sponsor.chat_id)
            continue
        if not ok:
            missing.append(sponsor.chat_id)
    return missing


async def resolve_gate(bot: Bot, db: Database, cfg: Config, user: User) -> Gate:
    """Определяет текущее состояние доступа пользователя."""
    if user.blocked:
        return Gate.BLOCKED

    if not await check_main_subscription(bot, db, cfg, user.user_id):
        return Gate.MAIN_SUB

    if user.balance > 0:
        return Gate.OK

    if cfg.sponsors and cfg.bonus_views > 0 and not user.bonus_granted:
        # Спонсор считается рабочим, если бот видит канал. Иначе гейт — тупик
        # (пользователь не сможет выполнить условие никогда).
        if await any_reachable_sponsor(bot, cfg):
            return Gate.SPONSORS

    return Gate.PAYMENT
