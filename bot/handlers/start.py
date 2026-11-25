"""Старт, главное меню, проверка подписки на основной канал, статус."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import CheckSubCB, MenuCB, main_menu, sub_gate
from ..services.access import check_main_subscription
from .common import ensure_user, menu_for, price_label, status_text

router = Router(name="start")


async def send_start(
    message: Message, bot: Bot, db: Database, cfg: Config, payload: str | None = None
) -> None:
    assert message.from_user is not None
    user = await ensure_user(message.from_user, db, cfg)
    name = message.from_user.first_name or "друг"

    if user.blocked:
        await message.answer(texts.ERROR)
        return

    # Новый пользователь мог прийти по реферальной ссылке.
    came_by_ref = False
    if payload:
        from .referrals import apply_referral

        came_by_ref = await apply_referral(db, cfg, user.user_id, payload)

    # Подписку проверяем при каждом /start, а не только при первом входе:
    # иначе отписавшийся пользователь сохранил бы доступ навсегда.
    subscribed = await check_main_subscription(bot, db, cfg, user.user_id)
    if not subscribed:
        await message.answer(
            texts.START.format(
                name=name,
                status=texts.STATUS_NEED_SUB,
            ),
            reply_markup=sub_gate(cfg.main_channel_url),
            disable_web_page_preview=True,
        )
        return

    # Друг подписался — начисляем бонус тому, кто его пригласил.
    from .referrals import reward_if_subscribed

    await reward_if_subscribed(bot, db, cfg, user.user_id)

    user = await db.get_user(user.user_id) or user

    if user.balance > 0:
        status = texts.STATUS_OK.format(views=user.balance)
    elif cfg.sponsors and cfg.bonus_views > 0 and not user.bonus_granted:
        status = texts.STATUS_NEED_SPONSORS.format(bonus=cfg.bonus_views)
    else:
        status = texts.STATUS_NEED_PAY.format(
            size=cfg.pay_pack_size, price=price_label(cfg)
        )

    answer = texts.START.format(name=name, status=status)

    if came_by_ref:
        from .referrals import make_link

        link = await make_link(db, cfg, user.user_id)
        answer += (
            "\n\n"
            f"{texts.REFERRAL_NEW_USER}\n\n"
            f"👥 Твоя ссылка:\n<code>{link}</code>"
        )

    await message.answer(answer, reply_markup=menu_for(user, cfg))
    await message.answer("Выбери действие 👇", reply_markup=main_menu())


@router.message(CommandStart())
async def cmd_start(
    message: Message, bot: Bot, db: Database, cfg: Config, command: CommandObject
) -> None:
    await send_start(message, bot, db, cfg, payload=command.args)


@router.message(Command("menu"))
@router.message(F.text == "🏠 Меню")
async def cmd_menu(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    await ensure_user(message.from_user, db, cfg)  # type: ignore[arg-type]
    await message.answer("Выбери действие 👇", reply_markup=main_menu())


@router.message(F.text == "📊 Мои просмотры")
async def cmd_status(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    assert message.from_user is not None
    user = await ensure_user(message.from_user, db, cfg)
    await message.answer(status_text(user, cfg), reply_markup=menu_for(user, cfg))


@router.callback_query(MenuCB.filter(F.action == "status"))
async def cb_status(call: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    user = await ensure_user(call.from_user, db, cfg)
    if call.message:
        await call.message.answer(status_text(user, cfg), reply_markup=menu_for(user, cfg))
    await call.answer()


@router.callback_query(CheckSubCB.filter(F.target == "main"))
async def cb_check_main(call: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    user = await ensure_user(call.from_user, db, cfg)
    ok = await check_main_subscription(bot, db, cfg, user.user_id)
    if not ok:
        await call.answer(texts.GATE_SUB_NOT_YET, show_alert=True)
        return

    await call.answer("Подписка подтверждена ✅")

    # Если пользователь пришёл по ссылке — начисляем бонус пригласившему.
    from .referrals import reward_if_subscribed

    await reward_if_subscribed(bot, db, cfg, user.user_id)

    user = await db.get_user(user.user_id) or user
    if call.message:
        text = (
            texts.STATUS_OK.format(views=user.balance)
            if user.balance > 0
            else texts.STATUS_NEED_SPONSORS.format(bonus=cfg.bonus_views)
        )
        try:
            await call.message.edit_text(text)
        except TelegramBadRequest:
            pass  # текст не изменился — это не ошибка
        await call.message.answer("Выбери действие 👇", reply_markup=main_menu())


@router.callback_query(MenuCB.filter(F.action == "help"))
async def cb_help(call: CallbackQuery, cfg: Config) -> None:
    await call.answer()
    if call.message:
        lines = [
            "Как это работает:",
            "1. Подписка на наш канал — обязательна.",
            f"2. {cfg.free_views} бесплатных просмотров.",
        ]
        if cfg.sponsors and cfg.bonus_views > 0:
            lines.append(
                f"3. Подписки на каналы-партнёры → +{cfg.bonus_views} просмотров."
            )
            lines.append(
                f"4. Дальше пакеты по {cfg.pay_pack_size} просмотров за "
                f"{price_label(cfg)}."
            )
        else:
            lines.append(
                f"3. Дальше пакеты по {cfg.pay_pack_size} просмотров за "
                f"{price_label(cfg)}."
            )
        lines.append("")
        lines.append(
            "Свой кружок можно прислать в любой момент — после проверки он попадёт в ленту."
        )
        await call.message.answer("\n".join(lines))
