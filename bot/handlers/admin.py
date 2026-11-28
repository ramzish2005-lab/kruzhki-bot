"""Админские команды: статистика, ручная выдача просмотров, блокировка."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import texts
from ..config import Config
from ..db import Database
from .common import menu_for

router = Router(name="admin")


def _admin_only(message: Message, cfg: Config) -> bool:
    assert message.from_user is not None
    return cfg.is_admin(message.from_user.id)


@router.message(Command("stats"))
@router.message(F.text == "📈 Статистика")
async def cmd_stats(message: Message, cfg: Config, db: Database) -> None:
    if not _admin_only(message, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return
    stats = await db.stats()
    await message.answer(
        texts.ADMIN_STATS.format(
            users=stats.users,
            active=stats.active_24h,
            published=stats.published,
            pending=stats.pending,
            views=stats.views,
            payments=stats.payments,
            amount=stats.amount,
            sponsor_subs=stats.sponsor_subs,
        )
    )


@router.message(Command("give"))
async def cmd_give(
    message: Message, command: CommandObject, cfg: Config, db: Database, bot: Bot
) -> None:
    """/give <user_id> <views> — ручное начисление просмотров."""
    if not _admin_only(message, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return

    args = (command.args or "").split()
    if len(args) != 2 or not all(part.lstrip("-").isdigit() for part in args):
        await message.answer("Формат: /give <user_id> <views>")
        return

    user_id, views = int(args[0]), int(args[1])
    user = await db.get_user(user_id)
    if user is None:
        await message.answer("Пользователь не найден в базе.")
        return

    await db.add_views(user_id, views)
    updated = await db.get_user(user_id)
    await message.answer(
        f"Пользователю <code>{user_id}</code> начислено {views}. "
        f"Баланс: <b>{updated.balance if updated else '?'}</b>"
    )
    try:
        await bot.send_message(user_id, f"🎁 Тебе начислено {views} просмотров!")
    except Exception:  # noqa: BLE001
        pass


@router.message(Command("ban", "unban"))
async def cmd_ban(
    message: Message, command: CommandObject, cfg: Config, db: Database
) -> None:
    if not _admin_only(message, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return

    raw = (command.args or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("Формат: /ban <user_id> или /unban <user_id>")
        return

    blocked = command.command == "ban"
    await db.set_blocked(int(raw), blocked)
    await message.answer(
        f"Пользователь <code>{raw}</code> {'заблокирован' if blocked else 'разблокирован'}."
    )


@router.message(Command("pending"))
async def cmd_pending(message: Message, cfg: Config, db: Database) -> None:
    if not _admin_only(message, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return
    pending = await db.count_pending()
    await message.answer(f"Кружков на модерации: <b>{pending}</b>")


@router.message(Command("push_test"))
async def cmd_push_test(message: Message, cfg: Config, db: Database, bot: Bot) -> None:
    """Отправляет напоминание только тебе — для проверки текста и кнопки."""
    if not _admin_only(message, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return

    assert message.from_user is not None
    from ..services.push import notify_user

    sent = await notify_user(bot, db, cfg, message.from_user.id)
    if sent:
        await message.answer("✅ Напоминание отправлено (смотри выше).")
    else:
        await message.answer(
            "⚠️ Не отправилось: возможно, в ленте нет кружков, "
            "которые ты ещё не видел. Добавь кружок в канал и попробуй снова."
        )


@router.message(Command("push_all"))
async def cmd_push_all(message: Message, cfg: Config, db: Database, bot: Bot) -> None:
    """Разовая рассылка всем (то же, что делает цикл каждые N часов)."""
    if not _admin_only(message, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return

    from ..services.push import send_wave

    await message.answer("📤 Рассылаю напоминания…")
    sent = await send_wave(bot, db, cfg)
    await message.answer(f"✅ Доставлено: <b>{sent}</b>")


@router.message(Command("admin"))
async def cmd_admin(message: Message, cfg: Config, db: Database) -> None:
    if not _admin_only(message, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return
    assert message.from_user is not None
    user = await db.get_user(message.from_user.id)
    await message.answer(
        "Админ-команды:\n"
        "/settings — ⚙️ лимиты и цены (меняются сразу)\n"
        "/stats — статистика\n"
        "/pending — сколько на модерации\n"
        "/give <user_id> <views> — начислить просмотры\n"
        "/ban <user_id> — заблокировать\n"
        "/unban <user_id> — разблокировать",
        reply_markup=menu_for(user, cfg) if user else None,
    )
