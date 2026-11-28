"""Кнопка под напоминанием: выдаёт один кружок бесплатно.

Защита от накрутки: на каждое сообщение можно получить ровно один кружок —
факт выдачи пишется в free_grants с уникальным ключом (user_id, notification_id).
"""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import PushCB, feed_kb, main_menu
from .common import ensure_user

router = Router(name="push")
log = logging.getLogger(__name__)


@router.callback_query(PushCB.filter())
async def on_push_button(
    call: CallbackQuery, callback_data: PushCB, bot: Bot, db: Database, cfg: Config
) -> None:
    user = await ensure_user(call.from_user, db, cfg)

    owner = await db.notification_owner(callback_data.notification_id)
    if owner is None or owner != user.user_id:
        await call.answer(texts.PUSH_NOT_YOURS, show_alert=True)
        return

    if not await db.claim_notification(user.user_id, callback_data.notification_id):
        await call.answer(texts.PUSH_ALREADY_USED, show_alert=True)
        return

    video = await db.next_video_for_user(user.user_id, cfg.feed_include_own)
    if video is None:
        await call.answer(texts.PUSH_EMPTY_FEED, show_alert=True)
        return

    try:
        await bot.send_video_note(
            chat_id=user.user_id,
            video_note=video.file_id,
            reply_markup=feed_kb(video.id),
        )
    except TelegramBadRequest as exc:
        log.warning("Кружок %s не отправился: %s", video.public_id, exc)
        await call.answer(texts.ERROR, show_alert=True)
        return

    await db.mark_seen(user.user_id, video.id)
    await call.answer(texts.PUSH_GRANTED)

    # Убираем кнопку, чтобы не нажимали повторно.
    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001 - сообщение могло устареть
            pass
        try:
            await call.message.answer("Смотри и оценивай 👇", reply_markup=main_menu())
        except Exception:  # noqa: BLE001
            pass