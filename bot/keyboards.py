"""Инлайн-клавиатуры и типизированные callback-данные."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


class MenuCB(CallbackData, prefix="menu"):
    action: str  # feed | submit | status | help


class CheckSubCB(CallbackData, prefix="sub"):
    target: str  # main | sponsors


class FeedCB(CallbackData, prefix="feed"):
    action: str  # next | like | stop
    item_id: int = 0


class ModerationCB(CallbackData, prefix="mod"):
    action: str  # ok | no
    item_id: int


class PayCB(CallbackData, prefix="pay"):
    size: int


class SponsorCB(CallbackData, prefix="sponsor"):
    index: int


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Смотреть кружки", callback_data=MenuCB(action="feed"))
    builder.button(text="📤 Отправить кружок", callback_data=MenuCB(action="submit"))
    builder.button(text="📊 Мои просмотры", callback_data=MenuCB(action="status"))
    builder.adjust(2, 1)
    return builder.as_markup()


def reply_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="▶️ Смотреть кружки")],
        [KeyboardButton(text="📤 Отправить кружок"), KeyboardButton(text="📊 Мои просмотры")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="📈 Статистика")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def sub_gate(url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📣 Подписаться на канал", url=url))
    builder.row(
        InlineKeyboardButton(
            text="✅ Проверить подписку", callback_data=CheckSubCB(target="main").pack()
        )
    )
    return builder.as_markup()


def sponsor_gate(sponsors: list[tuple[str, str]], bonus: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, (title, url) in enumerate(sponsors):
        builder.row(
            InlineKeyboardButton(text=f"📣 {title}", url=url),
            InlineKeyboardButton(
                text="✅", callback_data=SponsorCB(index=index).pack()
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text=f"🎁 Проверить и получить +{bonus}",
            callback_data=CheckSubCB(target="sponsors").pack(),
        )
    )
    return builder.as_markup()


def pay_gate(size: int, price_label: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"💳 Купить {size} просмотров — {price_label}",
            callback_data=PayCB(size=size).pack(),
        )
    )
    return builder.as_markup()


def feed_kb(item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Дальше", callback_data=FeedCB(action="next", item_id=item_id).pack())
    builder.button(text="❤️ Нравится", callback_data=FeedCB(action="like", item_id=item_id).pack())
    builder.button(text="⏹ Стоп", callback_data=FeedCB(action="stop", item_id=item_id).pack())
    builder.adjust(2, 1)
    return builder.as_markup()


def moderation_kb(item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Принять", callback_data=ModerationCB(action="ok", item_id=item_id).pack()
    )
    builder.button(
        text="❌ Отклонить", callback_data=ModerationCB(action="no", item_id=item_id).pack()
    )
    builder.adjust(2)
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data=MenuCB(action="status").pack())
    return builder.as_markup()
