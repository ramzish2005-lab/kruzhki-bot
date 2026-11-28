"""Настройки, которые админ меняет прямо в Telegram.

Значения хранятся в таблице settings и при старте накладываются поверх .env.
Изменения применяются сразу — перезапуск не нужен.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Config
from .db import Database


class SettingError(ValueError):
    """Значение не подходит."""


@dataclass(frozen=True)
class Setting:
    key: str
    attr: str
    label: str
    kind: str  # "int" | "bool"
    minimum: int = 0
    maximum: int = 1_000_000
    hint: str = ""

    def format(self, value: Any) -> str:
        if self.kind == "bool":
            return "вкл" if value else "выкл"
        return str(value)


SETTINGS: tuple[Setting, ...] = (
    Setting(
        key="FREE_VIEWS",
        attr="free_views",
        label="Бесплатных просмотров",
        kind="int",
        maximum=10_000,
        hint="Сколько кружков новый пользователь смотрит бесплатно",
    ),
    Setting(
        key="BONUS_VIEWS",
        attr="bonus_views",
        label="Бонус за спонсоров",
        kind="int",
        maximum=10_000,
        hint="Просмотры за подписку на каналы-партнёры (0 — отключить)",
    ),
    Setting(
        key="REFERRAL_VIEWS",
        attr="referral_views",
        label="Просмотров за друга",
        kind="int",
        maximum=10_000,
        hint="Сколько получает пригласивший, когда друг подпишется на канал",
    ),
    Setting(
        key="PAY_PACK_SIZE",
        attr="pay_pack_size",
        label="Просмотров в пакете",
        kind="int",
        minimum=1,
        maximum=10_000,
        hint="Сколько просмотров даёт одна покупка",
    ),
    Setting(
        key="PAY_PACK_STARS",
        attr="pay_pack_stars",
        label="Цена пакета (звёзды)",
        kind="int",
        minimum=1,
        maximum=1_000_000,
        hint="Цена в Telegram Stars",
    ),
    Setting(
        key="PAY_PACK_RUB",
        attr="pay_pack_rub",
        label="Цена пакета (рубли)",
        kind="int",
        minimum=1,
        maximum=1_000_000,
        hint="Используется только в режиме provider",
    ),
    Setting(
        key="NOTIFY_HOURS",
        attr="notify_hours",
        label="Часов между напоминаниями",
        kind="int",
        minimum=1,
        maximum=168,
        hint="Раз в сколько часов бот сам пишет пользователям",
    ),
    Setting(
        key="FEED_INCLUDE_OWN",
        attr="feed_include_own",
        label="Показывать свои кружки",
        kind="bool",
        hint="1 — автор видит свои кружки в ленте, 0 — нет",
    ),
)

BY_KEY: dict[str, Setting] = {setting.key: setting for setting in SETTINGS}


def parse_value(setting: Setting, raw: str) -> Any:
    """Превращает ввод админа в значение нужного типа."""
    text = raw.strip().lower()

    if setting.kind == "bool":
        if text in ("1", "да", "yes", "y", "вкл", "on", "true"):
            return True
        if text in ("0", "нет", "no", "n", "выкл", "off", "false"):
            return False
        raise SettingError("Напиши 1 (включить) или 0 (выключить)")

    try:
        number = int(text)
    except ValueError as exc:
        raise SettingError("Нужно целое число") from exc

    if number < setting.minimum:
        raise SettingError(f"Минимум: {setting.minimum}")
    if number > setting.maximum:
        raise SettingError(f"Максимум: {setting.maximum}")
    return number


def to_storage(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def apply_value(cfg: Config, setting: Setting, value: Any) -> None:
    setattr(cfg, setting.attr, value)


async def load_settings(db: Database, cfg: Config) -> list[str]:
    """Накладывает сохранённые настройки поверх .env. Возвращает список ключей."""
    stored = await db.get_settings()
    applied: list[str] = []

    for key, raw in stored.items():
        setting = BY_KEY.get(key)
        if setting is None:
            continue
        try:
            apply_value(cfg, setting, parse_value(setting, raw))
            applied.append(key)
        except SettingError:
            # Испорченное значение в базе не должно ломать запуск бота.
            continue
    return applied


async def save_setting(
    db: Database, cfg: Config, key: str, raw: str, admin_id: int | None = None
) -> tuple[Setting, Any]:
    """Проверяет, сохраняет и сразу применяет настройку."""
    setting = BY_KEY.get(key)
    if setting is None:
        raise SettingError("Неизвестная настройка")

    value = parse_value(setting, raw)
    await db.set_setting(key, to_storage(value), admin_id)
    apply_value(cfg, setting, value)
    return setting, value


def current_rows(cfg: Config) -> list[tuple[Setting, Any]]:
    return [(setting, getattr(cfg, setting.attr)) for setting in SETTINGS]