"""Оплата просмотров: Telegram Stars (XTR) или внешний провайдер.

Схема безопасная: просмотры начисляются только в successful_payment
и только один раз на charge_id (уникальный индекс в БД).
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import PayCB, main_menu
from .common import ensure_user, menu_for, price_label

router = Router(name="payments")
log = logging.getLogger(__name__)

PAYLOAD_PREFIX = "views"


def _payload(user_id: int, views: int) -> str:
    return f"{PAYLOAD_PREFIX}:{user_id}:{views}"


def _parse_payload(payload: str) -> tuple[int, int] | None:
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != PAYLOAD_PREFIX:
        return None
    if not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


@router.callback_query(PayCB.filter())
async def buy_pack(
    call: CallbackQuery, callback_data: PayCB, bot: Bot, db: Database, cfg: Config
) -> None:
    user = await ensure_user(call.from_user, db, cfg)
    views = callback_data.size or cfg.pay_pack_size
    payload = _payload(user.user_id, views)

    if cfg.payment_mode == "provider":
        # Внешний провайдер: сумма в копейках/центах минимальных единицах.
        prices = [LabeledPrice(label=f"{views} просмотров", amount=cfg.pay_pack_rub * 100)]
        currency = "RUB"
    else:
        # Telegram Stars: currency XTR, amount = число звёзд.
        prices = [LabeledPrice(label=f"{views} просмотров", amount=cfg.pay_pack_stars)]
        currency = "XTR"

    await call.answer()
    try:
        await bot.send_invoice(
            chat_id=call.from_user.id,
            title=f"{views} просмотров кружков",
            description="Пакет просмотров для ленты кружков",
            payload=payload,
            provider_token="" if cfg.payment_mode == "stars" else cfg.provider_token,
            currency=currency,
            prices=prices,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Не удалось выставить счёт: %s", exc)
        await bot.send_message(call.from_user.id, texts.ERROR)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, cfg: Config) -> None:
    parsed = _parse_payload(query.invoice_payload)
    if parsed is None or parsed[0] != query.from_user.id:
        await query.answer(ok=False, error_message=texts.ADMIN_PAYLOAD_BAD)
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    payment = message.successful_payment
    assert payment is not None and message.from_user is not None

    parsed = _parse_payload(payment.invoice_payload)
    if parsed is None:
        log.error("Некорректный payload платежа: %s", payment.invoice_payload)
        await message.answer(texts.ADMIN_PAYLOAD_BAD)
        return

    user_id, views = parsed
    created = await db.register_payment(
        user_id=user_id,
        charge_id=payment.telegram_payment_charge_id,
        amount=payment.total_amount,
        currency=payment.currency,
        views=views,
    )

    if not created:
        await message.answer(texts.PAY_ALREADY)
        return

    user = await db.get_user(user_id)
    await message.answer(
        texts.PAY_SUCCESS.format(views=views),
        reply_markup=menu_for(user, cfg) if user else main_menu(),
    )
    log.info("Платёж %s: +%s просмотров пользователю %s", payment.telegram_payment_charge_id, views, user_id)


@router.callback_query(F.data == "pay:info")
async def pay_info(call: CallbackQuery, cfg: Config) -> None:
    await call.answer()
    if call.message:
        await call.message.answer(
            f"Пакет: {cfg.pay_pack_size} просмотров — {price_label(cfg)}"
        )
