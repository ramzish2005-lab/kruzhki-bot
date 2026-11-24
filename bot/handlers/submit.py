"""Приём кружков от пользователей и отправка на модерацию."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import MenuCB, moderation_kb, reply_menu
from .common import ensure_user, menu_for

router = Router(name="submit")
log = logging.getLogger(__name__)

MAX_DURATION = 60  # лимит Telegram для видеосообщений, секунды
SUBMIT_BUTTONS = {"📤 Отправить кружок"}


@router.message(F.text.in_(SUBMIT_BUTTONS))
async def ask_video_message(message: Message, db: Database, cfg: Config) -> None:
    assert message.from_user is not None
    user = await ensure_user(message.from_user, db, cfg)
    await message.answer(texts.SUBMIT_ASK, reply_markup=menu_for(user, cfg))


@router.callback_query(MenuCB.filter(F.action == "submit"))
async def ask_video_callback(call: CallbackQuery, db: Database, cfg: Config) -> None:
    user = await ensure_user(call.from_user, db, cfg)
    await call.answer()
    if call.message:
        await call.message.answer(texts.SUBMIT_ASK, reply_markup=menu_for(user, cfg))


@router.message(F.video_note)
async def on_video_note(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    assert message.from_user is not None and message.video_note is not None
    user = await ensure_user(message.from_user, db, cfg)

    if user.blocked:
        await message.answer(texts.ERROR)
        return

    note = message.video_note
    if note.duration > MAX_DURATION:
        await message.answer(texts.SUBMIT_TOO_LONG.format(seconds=MAX_DURATION))
        return

    video = await db.create_video(
        author_id=user.user_id,
        file_id=note.file_id,
        file_unique_id=note.file_unique_id,
        duration=note.duration,
    )

    caption = texts.MODERATION_CAPTION.format(
        author=user.display_name,
        public_id=video.public_id,
        user_id=user.user_id,
    )
    delivered = 0
    for admin_id in cfg.admin_ids:
        try:
            await bot.send_video_note(
                chat_id=admin_id,
                video_note=note.file_id,
                reply_markup=moderation_kb(video.id),
            )
            await bot.send_message(admin_id, caption, reply_markup=moderation_kb(video.id))
            delivered += 1
        except Exception as exc:  # noqa: BLE001 - админ мог не начать диалог
            log.warning("Не удалось отправить кружок админу %s: %s", admin_id, exc)

    if delivered == 0:
        await message.answer(
            "Не удалось отправить кружок на проверку. Попробуй позже."
        )
        return

    await message.answer(
        texts.SUBMIT_ACCEPTED,
        reply_markup=reply_menu(is_admin=cfg.is_admin(user.user_id)),
    )


@router.message(F.video | F.animation | F.document | F.photo)
async def on_wrong_media(message: Message) -> None:
    await message.answer(texts.SUBMIT_WRONG_TYPE)
