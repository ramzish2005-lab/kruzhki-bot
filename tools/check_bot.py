"""Проверка живого бота: токен, канал, права админа.

Запуск: python tools/check_bot.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402

from bot.config import ConfigError, load_config  # noqa: E402


async def main() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"❌ {exc}")
        return 1

    bot = Bot(token=cfg.bot_token)
    ok = True
    try:
        me = await bot.get_me()
        print(f"✅ Бот: @{me.username} (id {me.id})")

        checks: list[tuple[str, int | None]] = [
            ("НОВОСТНОЙ канал (подписка)", cfg.main_channel_id),
            ("КАНАЛ С КРУЖКАМИ (автозалив)", cfg.source_channel_id),
        ]

        for label, chat_id in checks:
            if chat_id is None:
                print(f"⚠️  {label}: не указан в .env")
                continue
            try:
                chat = await bot.get_chat(chat_id)
                member = await bot.get_chat_member(chat_id, me.id)
            except Exception as exc:  # noqa: BLE001
                print(f"❌ {label} ({chat_id}): недоступен — {exc}")
                print("   Проверь ID и добавь бота в канал.")
                ok = False
                continue

            title = getattr(chat, "title", "?")
            if member.status in ("administrator", "creator"):
                print(f"✅ {label}: «{title}» — бот админ ({member.status})")
            else:
                print(f"❌ {label}: «{title}» — бот НЕ админ (статус {member.status})")
                print("   Без прав админа проверка подписки и автозалив не работают.")
                ok = False
    finally:
        await bot.session.close()

    print("\nВсё в порядке." if ok else "\nЕсть проблемы — смотри ❌ выше.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))