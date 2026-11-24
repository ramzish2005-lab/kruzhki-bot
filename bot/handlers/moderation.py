"""Модерация: админ принимает или отклоняет кружок.

Принятый кружок копируется в канал-хранилище (если задан) и попадает в ленту.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import ModerationCB

router = Router(name="moderation")
log = logging.getLogger(__name__)


async def _is_admin(call: CallbackQuery, cfg: Config) -> bool:
    if cfg.is_admin(call.from_user.id):
        return True
    await call.answer(texts.ADMIN_ONLY, show_alert=True)
    return False


@router.callback_query(ModerationCB.filter(F.action == "ok"))
async def approve(
    call: CallbackQuery, callback_data: ModerationCB, bot: Bot, db: Database, cfg: Config
) -> None:
    if not await _is_admin(call, cfg):
        return

    video = await db.get_video(callback_data.item_id)
    if video is None:
        await call.answer("Кружок не найден", show_alert=True)
        return

    if not await db.publish_video(video.id, call.from_user.id):
        await call.answer(texts.MODERATION_ALREADY, show_alert=True)
        return

    if cfg.storage_channel_id:
        try:
            stored = await bot.send_video_note(
                chat_id=cfg.storage_channel_id,
                video_note=video.file_id,
            )
            await db.set_storage_message(video.id, stored.message_id)
        except TelegramBadRequest as exc:
            log.warning("Не удалось сохранить кружок в хранилище: %s", exc)

    await call.answer(texts.MODERATION_DONE_APPROVE.format(public_id=video.public_id))
    if call.message:
        await _finalize(call, texts.MODERATION_APPROVED, video.public_id)

    try:
        await bot.send_message(
            video.author_id,
            f"🎉 Твой кружок прошёл проверку и уже в ленте! (#{video.public_id})",
        )
    except Exception as exc:  # noqa: BLE001
        log.info("Не смог уведомить автора %s: %s", video.author_id, exc)


@router.callback_query(ModerationCB.filter(F.action == "no"))
async def reject(
    call: CallbackQuery, callback_data: ModerationCB, bot: Bot, db: Database, cfg: Config
) -> None:
    if not await _is_admin(call, cfg):
        return

    video = await db.get_video(callback_data.item_id)
    if video is None:
        await call.answer("Кружок не найден", show_alert=True)
        return

    if not await db.reject_video(video.id, call.from_user.id, None):
        await call.answer(texts.MODERATION_ALREADY, show_alert=True)
        return

    await call.answer(texts.MODERATION_DONE_REJECT.format(public_id=video.public_id))
    if call.message:
        await _finalize(call, texts.MODERATION_REJECTED, video.public_id)

    try:
        await bot.send_message(
            video.author_id,
            "😔 Кружок не прошёл проверку. Можно прислать другой.",
        )
    except Exception as exc:  # noqa: BLE001
        log.info("Не смог уведомить автора %s: %s", video.author_id, exc)


async def _finalize(call: CallbackQuery, verdict: str, public_id: str) -> None:
    """Убирает кнопки у сообщения модерации, чтобы нельзя было нажать дважды."""
    message = call.message
    if message is None:
        return
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    try:
        await message.reply(f"{verdict} — <code>{public_id}</code>")
    except TelegramBadRequest:
        pass
