"""Симуляция сервера Railway: пустая папка, только переменные окружения.

Ловит ошибки, которые не видны локально (нет .env, нет папки data и т.п.).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


async def main() -> int:
    problems = 0

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        os.environ["DATA_DIR"] = str(data_dir)
        os.environ["DB_PATH"] = "bot.db"

        # Как на Railway: переменные приходят из окружения, .env может не быть.
        for key in ("BOT_TOKEN", "ADMIN_IDS", "MAIN_CHANNEL_ID", "MAIN_CHANNEL_URL"):
            if not os.getenv(key):
                os.environ[key] = {
                    "BOT_TOKEN": "123456:TEST",
                    "ADMIN_IDS": "1",
                    "MAIN_CHANNEL_ID": "-1001",
                    "MAIN_CHANNEL_URL": "https://t.me/x",
                }[key]

        from importlib import reload

        import bot.config as config_module

        reload(config_module)

        try:
            cfg = config_module.load_config()
            print(f"OK: конфиг загружен, база будет в {cfg.db_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: конфиг не загрузился: {exc}")
            return 1

        # Ключевая проверка: создастся ли папка и схема.
        from bot.db import Database

        db = Database(cfg.db_path)
        try:
            await db.connect()
            print(f"OK: база создана: {cfg.db_path.exists()}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: база не создалась: {exc}")
            problems += 1
            return problems

        from bot.settings import load_settings

        await load_settings(db, cfg)
        print("OK: настройки загружены")

        user, _ = await db.touch_user(1, None, "T", cfg.free_views)
        print(f"OK: пользователь создан (баланс {user.balance})")

        await db.close()

        # Сборка диспетчера — импортирует ВСЕ хендлеры и сервисы.
        from run import build_dispatcher

        db2 = Database(Path(tmp) / "d.db")
        await db2.connect()
        try:
            dp = build_dispatcher(cfg, db2)
            print(f"OK: диспетчер собран, роутеров {len(dp.sub_routers)}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: диспетчер не собрался: {exc}")
            import traceback

            traceback.print_exc()
            problems += 1
        finally:
            await db2.close()

    print("\nSERVER SIM OK" if problems == 0 else "\nSERVER SIM FAILED")
    return problems


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))