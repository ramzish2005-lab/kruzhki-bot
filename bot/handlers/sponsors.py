"""Каналы-спонсоры: проверка подписок и разовое начисление бонусных просмотров."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import CheckSubCB, MenuCB, main_menu, sponsor_gate
from ..services.access import missing_sponsors
from .common import ensure_user

router = Router(name="sponsors")
log = logging.getLogger(__name__)


@router.callback_query(CheckSubCB.filter(F.target == "sponsors"))
async def check_sponsors(call: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    user = await ensure_user(call.from_user, db, cfg)

    if not cfg.sponsors:
        await call.answer("Список спонсоров не настроен", show_alert=True)
        return

    missing = await missing_sponsors(bot, cfg, user.user_id)
    if missing:
        left = len(missing)
        await call.answer(
            texts.GATE_SPONSORS_NOT_YET.format(left=left), show_alert=True
        )
        if call.message:
            sponsors = [(s.title, s.url) for s in cfg.sponsors]
            try:
                await call.message.edit_reply_markup(
                    reply_markup=sponsor_gate(sponsors, cfg.bonus_views)
                )
            except Exception:  # noqa: BLE001 - сообщение могло не измениться
                pass
        return

    for sponsor in cfg.sponsors:
        await db.mark_sponsor_checked(user.user_id, sponsor.chat_id)

    granted = await db.grant_bonus_once(user.user_id, cfg.bonus_views)
    user = await db.get_user(user.user_id) or user

    if granted:
        await call.answer(f"🎁 +{cfg.bonus_views} просмотров начислено!", show_alert=True)
    else:
        await call.answer("Бонус за подписки уже был получен ранее", show_alert=True)

    if call.message:
        await call.message.edit_text(
            f"✅ Все подписки подтверждены.\nДоступных просмотров: <b>{user.balance}</b>"
        )
        await call.message.answer("Выбери действие 👇", reply_markup=main_menu())


@router.callback_query(MenuCB.filter(F.action == "sponsors"))
async def show_sponsors(call: CallbackQuery, cfg: Config) -> None:
    if not cfg.sponsors:
        await call.answer("Список спонсоров не настроен", show_alert=True)
        return
    await call.answer()
    if call.message:
        sponsors = [(s.title, s.url) for s in cfg.sponsors]
        await call.message.answer(
            texts.GATE_SPONSORS_REQUIRED.format(
                bonus=cfg.bonus_views, left=len(sponsors)
            ),
            reply_markup=sponsor_gate(sponsors, cfg.bonus_views),
            disable_web_page_preview=True,
        )
