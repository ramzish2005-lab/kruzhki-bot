"""Проверка живости бота БЕЗ вмешательства в его работу.

Важно: обычный getUpdates «угоняет» апдейты у рабочего бота и вызывает
TelegramConflictError. Поэтому здесь только getMe — безопасная проверка.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from aiogram import Bot  # noqa: E402
from aiogram.exceptions import TelegramUnauthorizedError  # noqa: E402

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
        print(f"   Имя бота: {me.first_name}")
    except TelegramUnauthorizedError:
        print("❌ Токен отозван. Возьми новый у @BotFather и запусти tools/set_token.py")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Не удалось проверить токен: {exc}")
        return 1
    finally:
        await bot.session.close()

    print()
    print("Этот скрипт не мешает работе бота.")
    print("Чтобы проверить, что бот отвечает — напиши ему /start в Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))