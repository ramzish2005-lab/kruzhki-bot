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

log = logging.getLogger(__name__)


async def show_next(message: Message, bot: Bot, db: Database, cfg: Config, user_id: int) -> bool:
    """Отправляет следующий кружок. False — если показать нечего.

    Просмотр списывается ДО отправки, чтобы перезапуск бота или «Назад»
    не давали бесплатных показов, и возвращается, если файл не отправился.
    """
    video = await db.next_video_for_user(user_id, cfg.feed_include_own)
    if video is None:
        await message.answer(texts.FEED_NO_MORE, reply_markup=main_menu())
        return False

    if not await db.spend_view(user_id):
        await message.answer(texts.FEED_NEED_VIEWS)
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
