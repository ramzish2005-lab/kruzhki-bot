"""Лента: показ следующего кружка, лайки, остановка."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from ..config import Config
from ..db import Database
from ..keyboards import FeedCB, MenuCB, main_menu
from ..services.feed import show_next
from .common import ensure_user, menu_for, require_access_callback, require_access_message

router = Router(name="feed")

FEED_BUTTONS = {"▶️ Смотреть кружки"}


@router.message(F.text.in_(FEED_BUTTONS))
async def start_feed(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    user = await require_access_message(message, bot, db, cfg)
    if user is None:
        return
    await show_next(message, bot, db, cfg, user.user_id)


@router.callback_query(MenuCB.filter(F.action == "feed"))
async def cb_start_feed(call: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    user = await require_access_callback(call, bot, db, cfg)
    if user is None:
        return
    await call.answer()
    if call.message:
        await show_next(call.message, bot, db, cfg, user.user_id)


@router.callback_query(FeedCB.filter(F.action == "next"))
async def cb_next(call: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    user = await require_access_callback(call, bot, db, cfg)
    if user is None:
        return
    await call.answer()
    if call.message:
        await show_next(call.message, bot, db, cfg, user.user_id)


@router.callback_query(FeedCB.filter(F.action == "like"))
async def cb_like(
    call: CallbackQuery, callback_data: FeedCB, db: Database, cfg: Config
) -> None:
    user = await ensure_user(call.from_user, db, cfg)
    if not callback_data.item_id:
        await call.answer("Не удалось определить кружок", show_alert=True)
        return
    liked = await db.toggle_like(user.user_id, callback_data.item_id)
    await call.answer("❤️ Лайк поставлен" if liked else "Лайк снят")


@router.callback_query(FeedCB.filter(F.action == "stop"))
async def cb_stop(call: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    user = await ensure_user(call.from_user, db, cfg)
    await call.answer()
    if call.message:
        await call.message.answer(
            "Остановились. Возвращайся, когда захочешь 👋",
            reply_markup=menu_for(user, cfg),
        )
        await call.message.answer("Выбери действие 👇", reply_markup=main_menu())
