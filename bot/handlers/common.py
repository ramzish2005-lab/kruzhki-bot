"""Общие помощники для хендлеров: регистрация пользователя и показ гейтов."""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, User as TgUser

from .. import texts
from ..config import Config
from ..db import Database, User
from ..keyboards import pay_gate, reply_menu, sponsor_gate, sub_gate
from ..services.access import Gate, resolve_gate


def price_label(cfg: Config) -> str:
    if cfg.payment_mode == "provider":
        return f"{cfg.pay_pack_rub} ₽"
    return f"{cfg.pay_pack_stars} ⭐"


async def _reachable(bot: Bot, chat_id: int) -> bool:
    """Доступен ли канал боту (существует и бот его видит)."""
    try:
        await bot.get_chat(chat_id)
    except TelegramAPIError:
        return False
    return True


async def ensure_user(from_user: TgUser, db: Database, cfg: Config) -> User:
    """Регистрирует пользователя при первом обращении и обновляет профиль."""
    user, _is_new = await db.touch_user(
        user_id=from_user.id,
        username=from_user.username,
        first_name=from_user.first_name,
        free_views=cfg.free_views,
    )
    return user


async def send_gate(
    bot: Bot, chat_id: int, cfg: Config, gate: Gate
) -> None:
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
            if await _reachable(bot, sponsor.chat_id)
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
            texts.GATE_PAY_REQUIRED.format(
                size=cfg.pay_pack_size, price=price_label(cfg)
            ),
            reply_markup=pay_gate(cfg.pay_pack_size, price_label(cfg)),
        )
    else:
        await bot.send_message(chat_id, texts.ERROR)


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
        f"Отправлено кружков: <b>{user.submitted}</b> (принято: <b>{user.approved}</b>)\n\n"
        f"Лимит: {cfg.free_views} бесплатных, затем +{cfg.bonus_views} за подписки "
        f"на каналы-партнёры, далее пакеты по {cfg.pay_pack_size}."
    )


def menu_for(user: User, cfg: Config):
    return reply_menu(is_admin=cfg.is_admin(user.user_id))
