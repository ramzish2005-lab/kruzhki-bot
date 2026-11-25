"""Проверяет, запущен ли бот где-то ещё (Railway) или нет.

Запуск: python tools/check_running.py
Безопасно: ничего не удаляет и не меняет.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from aiogram import Bot  # noqa: E402
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError  # noqa: E402

from setup_env import current_value, load_lines  # noqa: E402


async def main() -> int:
    token = current_value(load_lines(), "BOT_TOKEN")
    if not token:
        print("❌ BOT_TOKEN не заполнен в .env")
        return 1

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        print(f"✅ Токен рабочий: @{me.username} (id {me.id})")
    except TelegramUnauthorizedError:
        print("❌ Токен НЕ работает (отозван или опечатка). Возьми новый у @BotFather.")
        await bot.session.close()
        return 1
    finally:
        pass

    try:
        # Если бот уже кем-то опрашивается (Railway), Telegram ответит 409.
        await bot.get_updates(timeout=0, limit=1)
        print("⚠️  Бот НЕ запущен ни на одном сервере (никто не опрашивает Telegram).")
        print("   → Значит на Railway он упал. Смотри Deploy Logs.")
        running = False
    except TelegramConflictError:
        print("✅ Бот РАБОТАЕТ на сервере (Railway) — он сейчас опрашивает Telegram.")
        running = True
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Не удалось проверить: {exc}")
        running = False
    finally:
        await bot.session.close()

    print()
    if running:
        print("Всё хорошо. Напиши боту /start в Telegram.")
    return 0 if running else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))