"""Общие помощники для хендлеров: регистрация пользователя и показ гейтов."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import CallbackQuery, Message, User as TgUser

from ..config import Config
from ..db import Database, User
from ..keyboards import reply_menu
from ..services.access import Gate, resolve_gate
from ..services.gates import price_label, send_gate

__all__ = [
    "ensure_user",
    "gate_for",
    "menu_for",
    "price_label",
    "require_access_callback",
    "require_access_message",
    "send_gate",
    "status_text",
]


async def ensure_user(from_user: TgUser, db: Database, cfg: Config) -> User:
    """Регистрирует пользователя при первом обращении и обновляет профиль."""
    user, _is_new = await db.touch_user(
        user_id=from_user.id,
        username=from_user.username,
        first_name=from_user.first_name,
        free_views=cfg.free_views,
    )
    return user


async def gate_for(from_user: TgUser, bot: Bot, db: Database, cfg: Config) -> tuple[User, Gate]:
    user = await ensure_user(from_user, db, cfg)
    gate = await resolve_gate(bot, db, cfg, user)
    return user, gate


async def require_access_message(
    message: Message, bot: Bot, db: Database, cfg: Config
) -> User | None:
    """Возвращает пользователя, если доступ открыт, иначе показывает гейт."""
    assert message.from_user is not None
    user, gate = await gate_for(message.from_user, bot, db, cfg)
    if gate is not Gate.OK:
        await send_gate(bot, message.chat.id, cfg, gate)
        return None
    return user


async def require_access_callback(
    call: CallbackQuery, bot: Bot, db: Database, cfg: Config
) -> User | None:
    """То же для callback-кнопок."""
    user, gate = await gate_for(call.from_user, bot, db, cfg)
    if gate is not Gate.OK:
        await send_gate(bot, call.message.chat.id if call.message else call.from_user.id, cfg, gate)
        await call.answer()
        return None
    return user


def status_text(user: User, cfg: Config) -> str:
    return (
        f"👤 {user.display_name}\n"
        f"Доступных просмотров: <b>{user.balance}</b>\n"
        f"Всего просмотрено: <b>{user.total_views}</b>\n"
        f"Отправлено кружков: <b>{user.submitted}</b> (принято: <b>{user.approved}</b>)\n"
        f"Приглашено друзей: <b>{user.referrals}</b>\n\n"
        f"Лимит: {cfg.free_views} бесплатных, +{cfg.referral_views} за друга, "
        f"далее пакеты по {cfg.pay_pack_size}."
    )


def menu_for(user: User, cfg: Config):
    return reply_menu(is_admin=cfg.is_admin(user.user_id))
