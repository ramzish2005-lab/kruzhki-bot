"""Реферальная система: ссылка, привязка друга, награда после подписки.

Схема:
  * пользователь получает ссылку вида https://t.me/bot?start=ref_КОД;
  * друг открывает её, бот запоминает, кто пригласил;
  * как только друг подписывается на новостной канал, пригласивший
    получает REFERRAL_VIEWS просмотров — ровно один раз за друга.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..config import Config
from ..db import Database, User
from ..keyboards import MenuCB, main_menu
from ..services.access import check_main_subscription
from .common import ensure_user, menu_for

router = Router(name="referrals")
log = logging.getLogger(__name__)

REF_PREFIX = "ref_"


def build_link(cfg: Config, code: str) -> str:
    if cfg.bot_username:
        return f"https://t.me/{cfg.bot_username}?start={REF_PREFIX}{code}"
    return f"<code>{REF_PREFIX}{code}</code> (укажи BOT_USERNAME в .env)"


def referral_text(user: User, cfg: Config, link: str) -> str:
    return texts.REFERRAL_TEXT.format(
        views=cfg.referral_views,
        link=link,
        count=user.referrals,
        earned=user.referrals * cfg.referral_views,
    )


async def make_link(db: Database, cfg: Config, user_id: int) -> str:
    code = await db.ensure_ref_code(user_id)
    return build_link(cfg, code)


async def apply_referral(db: Database, cfg: Config, user_id: int, payload: str) -> bool:
    """Привязывает пригласившего по payload из /start. Возвращает True, если сработало."""
    if not payload.startswith(REF_PREFIX):
        return False

    code = payload[len(REF_PREFIX):].strip()
    if not code:
        return False

    referrer = await db.find_by_ref_code(code)
    if referrer is None:
        log.info("Реферальный код %s не найден", code)
        return False

    return await db.set_referrer(user_id, referrer.user_id)


async def reward_if_subscribed(
    bot: Bot, db: Database, cfg: Config, user_id: int
) -> None:
    """Если друг подписан на канал — начисляет бонус пригласившему."""
    user = await db.get_user(user_id)
    if user is None or user.referred_by is None:
        return

    if not await check_main_subscription(bot, db, cfg, user_id):
        return

    result = await db.reward_referrer(user_id, cfg.referral_views)
    if result is None:
        return  # уже награждён за этого друга

    referrer_id, total = result

    try:
        referrer = await db.get_user(referrer_id)
        await bot.send_message(
            referrer_id,
            texts.REFERRAL_BONUS.format(
                views=cfg.referral_views,
                balance=referrer.balance if referrer else cfg.referral_views,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - пригласивший мог заблокировать бота
        log.info("Не смог уведомить пригласившего %s: %s", referrer_id, exc)

    log.info(
        "Реферал: %s пригласил %s, начислено %s (всего друзей: %s)",
        referrer_id,
        user_id,
        cfg.referral_views,
        total,
    )


@router.message(F.text == "👥 Пригласить друга")
async def cmd_referrals(message: Message, db: Database, cfg: Config) -> None:
    assert message.from_user is not None
    user = await ensure_user(message.from_user, db, cfg)
    link = await make_link(db, cfg, user.user_id)
    await message.answer(referral_text(user, cfg, link), reply_markup=menu_for(user, cfg))


@router.callback_query(MenuCB.filter(F.action == "refs"))
async def cb_referrals(call: CallbackQuery, db: Database, cfg: Config) -> None:
    user = await ensure_user(call.from_user, db, cfg)
    link = await make_link(db, cfg, user.user_id)
    await call.answer()
    if call.message:
        await call.message.answer(
            referral_text(user, cfg, link), reply_markup=main_menu()
        )