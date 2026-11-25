"""Отправка гейтов: что показать пользователю, если доступ закрыт.

Живёт в services, потому что используется и хендлерами, и лентой.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from .. import texts
from ..config import Config
from ..keyboards import no_views_gate, sponsor_gate, sub_gate
from .access import Gate

log = logging.getLogger(__name__)


def price_label(cfg: Config) -> str:
    if cfg.payment_mode == "provider":
        return f"{cfg.pay_pack_rub} ₽"
    return f"{cfg.pay_pack_stars} ⭐"


async def reachable(bot: Bot, chat_id: int) -> bool:
    """Доступен ли канал боту (существует и бот его видит)."""
    try:
        await bot.get_chat(chat_id)
    except TelegramAPIError:
        return False
    return True


async def send_gate(bot: Bot, chat_id: int, cfg: Config, gate: Gate) -> None:
    """Показывает пользователю, что нужно сделать для доступа."""
    if gate is Gate.MAIN_SUB:
        await bot.send_message(
            chat_id,
            texts.GATE_SUB_REQUIRED,
            reply_markup=sub_gate(cfg.main_channel_url),
            disable_web_page_preview=True,
        )
    elif gate is Gate.SPONSORS:
        sponsors = [
            (sponsor.title, sponsor.url)
            for sponsor in cfg.sponsors
            if await reachable(bot, sponsor.chat_id)
        ]
        if not sponsors:
            await bot.send_message(chat_id, texts.ERROR)
            return
        await bot.send_message(
            chat_id,
            texts.GATE_SPONSORS_REQUIRED.format(bonus=cfg.bonus_views, left=len(sponsors)),
            reply_markup=sponsor_gate(sponsors, cfg.bonus_views),
            disable_web_page_preview=True,
        )
    elif gate is Gate.PAYMENT:
        await bot.send_message(
            chat_id,
            texts.GATE_NO_VIEWS.format(
                referral=cfg.referral_views,
                size=cfg.pay_pack_size,
                price=price_label(cfg),
            ),
            reply_markup=no_views_gate(
                cfg.pay_pack_size, price_label(cfg), cfg.referral_views
            ),
        )
    elif gate is Gate.BLOCKED:
        await bot.send_message(chat_id, texts.ERROR)
    else:
        await bot.send_message(chat_id, texts.ERROR)