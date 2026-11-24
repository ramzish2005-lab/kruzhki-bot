"""Автозабор кружков из канала-источника.

Ты кидаешь кружок в свой канал (бот там админ) — бот сам ловит его и
публикует в ленту. Второй аккаунт и api_id для этого не нужны.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from ..config import Config
from ..db import Database

router = Router(name="ingest")
log = logging.getLogger(__name__)


@router.channel_post(F.video_note)
async def on_channel_video_note(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    """Кружок, отправленный в канал-источник, сразу попадает в ленту."""
    if cfg.source_channel_id is None:
        return
    if message.chat.id != cfg.source_channel_id:
        return

    note = message.video_note
    if note is None:
        return

    author = message.author_signature or message.sender_chat
    author_id = message.sender_chat.id if message.sender_chat else 0

    if await db.video_exists_by_unique_id(note.file_unique_id):
        log.info("Кружок %s уже в ленте, пропускаю", note.file_unique_id)
        return

    video = await db.create_video(
        author_id=author_id,
        file_id=note.file_id,
        file_unique_id=note.file_unique_id,
        duration=note.duration,
    )
    await db.publish_video(video.id, cfg.admin_ids[0])

    log.info("Из канала добавлен кружок #%s (%s)", video.public_id, author)

    # Подтверждение тебе: кружок реально попал в ленту.
    for admin_id in cfg.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"✅ Кружок из канала сразу в ленте (#{video.public_id})",
            )
        except Exception as exc:  # noqa: BLE001
            log.info("Не смог уведомить админа %s: %s", admin_id, exc)

    if cfg.storage_channel_id and cfg.storage_channel_id != cfg.source_channel_id:
        try:
            stored = await bot.send_video_note(
                chat_id=cfg.storage_channel_id, video_note=note.file_id
            )
            await db.set_storage_message(video.id, stored.message_id)
        except TelegramBadRequest as exc:
            log.warning("Не смог скопировать кружок в хранилище: %s", exc)