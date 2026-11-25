"""Админ-панель настроек: лимиты и цены меняются прямо в Telegram."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import SettingsCB, back_to_menu, settings_panel
from ..settings import BY_KEY, SettingError, current_rows, save_setting

router = Router(name="settings")


class EditSetting(StatesGroup):
    waiting_value = State()


def _panel_text(cfg: Config) -> str:
    return (
        "⚙️ <b>Настройки бота</b>\n\n"
        f"Бесплатных просмотров: <b>{cfg.free_views}</b>\n"
        f"Пакет: <b>{cfg.pay_pack_size}</b> просмотров "
        f"за <b>{cfg.pay_pack_stars}</b> ⭐\n\n"
        "Нажми на строку, чтобы изменить. Изменения применяются сразу."
    )


async def _show_panel(target: Message, cfg: Config) -> None:
    rows = [
        (setting.key, setting.label, setting.format(value))
        for setting, value in current_rows(cfg)
    ]
    await target.answer(_panel_text(cfg), reply_markup=settings_panel(rows))


def _is_admin(user_id: int, cfg: Config) -> bool:
    return cfg.is_admin(user_id)


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message, cfg: Config) -> None:
    assert message.from_user is not None
    if not _is_admin(message.from_user.id, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return
    await _show_panel(message, cfg)


@router.callback_query(SettingsCB.filter(F.action == "edit"))
async def cb_edit(
    call: CallbackQuery,
    callback_data: SettingsCB,
    state: FSMContext,
    cfg: Config,
) -> None:
    if not _is_admin(call.from_user.id, cfg):
        await call.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    setting = BY_KEY.get(callback_data.key)
    if setting is None:
        await call.answer("Неизвестная настройка", show_alert=True)
        return

    current = getattr(cfg, setting.attr)
    await state.set_state(EditSetting.waiting_value)
    await state.update_data(key=setting.key)
    await call.answer()

    if call.message:
        hint = f"\n<i>{setting.hint}</i>" if setting.hint else ""
        await call.message.answer(
            f"✏️ <b>{setting.label}</b>\n"
            f"Сейчас: <b>{setting.format(current)}</b>{hint}\n\n"
            f"Пришли новое значение (или /cancel для отмены)."
        )


@router.message(EditSetting.waiting_value)
async def on_new_value(
    message: Message, state: FSMContext, cfg: Config, db: Database
) -> None:
    assert message.from_user is not None
    if not _is_admin(message.from_user.id, cfg):
        await message.answer(texts.ADMIN_ONLY)
        return

    if message.text and message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("Отменено.")
        await _show_panel(message, cfg)
        return

    data = await state.get_data()
    key = data.get("key")
    setting = BY_KEY.get(key or "")
    if setting is None:
        await state.clear()
        await message.answer(texts.ERROR)
        return

    try:
        saved, value = await save_setting(
            db, cfg, setting.key, message.text or "", message.from_user.id
        )
    except SettingError as exc:
        await message.answer(f"❌ {exc}\nПришли другое значение или /cancel.")
        return

    await state.clear()
    await message.answer(
        f"✅ <b>{saved.label}</b> → <b>{saved.format(value)}</b>\n"
        "Изменение применено сразу."
    )
    await _show_panel(message, cfg)


@router.message(Command("cancel"), StateFilter(EditSetting.waiting_value))
async def cmd_cancel(message: Message, state: FSMContext, cfg: Config) -> None:
    await state.clear()
    await message.answer("Отменено.")
    await _show_panel(message, cfg)


@router.callback_query(SettingsCB.filter(F.action == "reset"))
async def cb_reset(
    call: CallbackQuery, cfg: Config, db: Database
) -> None:
    if not _is_admin(call.from_user.id, cfg):
        await call.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    for row in await db.get_settings():
        await db.delete_setting(row)

    # Перечитываем значения из .env заново.
    from ..config import load_config
    from ..settings import load_settings

    fresh = load_config()
    for setting in BY_KEY.values():
        setattr(cfg, setting.attr, getattr(fresh, setting.attr))
    await load_settings(db, cfg)

    await call.answer("Сброшено к значениям из .env")
    if call.message:
        await _show_panel(call.message, cfg)


@router.callback_query(SettingsCB.filter(F.action == "close"))
async def cb_close(call: CallbackQuery) -> None:
    await call.answer()
    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=back_to_menu())
        except Exception:  # noqa: BLE001
            pass
