"""Выдача кружков в ленте: списание просмотра, отправка, счётчики."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import feed_kb, main_menu
from .access import Gate, resolve_gate
from .gates import send_gate

log = logging.getLogger(__name__)


async def show_next(message: Message, bot: Bot, db: Database, cfg: Config, user_id: int) -> bool:
    """Отправляет следующий кружок. False — если показать нечего.

    Порядок проверок важен:
      1) есть ли доступ (подписка/просмотры) — иначе показываем гейт;
      2) есть ли непросмотренный кружок;
      3) только потом списываем просмотр.

    Просмотр списывается ДО отправки, чтобы перезапуск бота или «Назад»
    не давали бесплатных показов, и возвращается, если файл не отправился.
    """
    user = await db.get_user(user_id)
    if user is None:
        await message.answer(texts.ERROR, reply_markup=main_menu())
        return False

    # 1. Сначала доступ: если просмотры кончились — предлагаем друга или покупку,
    #    а не сообщение «кружки закончились».
    gate = await resolve_gate(bot, db, cfg, user)
    if gate is not Gate.OK:
        await send_gate(bot, message.chat.id, cfg, gate)
        return False

    # 2. Есть ли что показать.
    video = await db.next_video_for_user(user_id, cfg.feed_include_own)
    if video is None:
        await message.answer(texts.FEED_EMPTY_NEW, reply_markup=main_menu())
        return False

    # 3. Списываем просмотр.
    if not await db.spend_view(user_id):
        user = await db.get_user(user_id) or user
        gate = await resolve_gate(bot, db, cfg, user)
        await send_gate(bot, message.chat.id, cfg, gate)
        return False

    try:
        await bot.send_video_note(
            chat_id=user_id,
            video_note=video.file_id,
            reply_markup=feed_kb(video.id),
        )
    except TelegramBadRequest as exc:
        log.warning("Не удалось отправить кружок %s: %s", video.public_id, exc)
        await db.add_views(user_id, 1)
        await message.answer(texts.ERROR, reply_markup=main_menu())
        return False

    await db.mark_seen(user_id, video.id)
    user = await db.get_user(user_id)
    balance = user.balance if user else 0
    await message.answer(texts.FEED_VIEWS_LEFT.format(views=balance))
    return True
