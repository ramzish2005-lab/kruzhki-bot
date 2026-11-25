"""Проверка старта: конфиг, схема БД, настройки, диспетчер — без polling."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from bot.config import load_config  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.settings import load_settings  # noqa: E402


async def main() -> int:
    cfg = load_config()
    print("OK: конфиг загружен")

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "start.db")
        await db.connect()
        print("OK: схема БД создана")

        await load_settings(db, cfg)
        print("OK: настройки наложены")

        # Проверяем, что новые поля и таблицы на месте.
        user, _ = await db.touch_user(1, None, "T", cfg.free_views)
        print(f"OK: пользователь создан, баланс {user.balance}")

        code = await db.ensure_ref_code(1)
        print(f"OK: реф-код {code}")

        await db.touch_user(2, None, "F", cfg.free_views)
        await db.set_referrer(2, 1)
        result = await db.reward_referrer(2, cfg.referral_views)
        print(f"OK: награда {result}")

        await db.close()

    # Сборка диспетчера (импортирует все хендлеры).
    from run import DepsMiddleware, build_dispatcher  # noqa: F401

    with tempfile.TemporaryDirectory() as tmp2:
        db2 = Database(Path(tmp2) / "d.db")
        await db2.connect()
        dp = build_dispatcher(replace(cfg), db2)
        names = [r.name for r in dp.sub_routers]
        print(f"OK: диспетчер собран, роутеров {len(names)}: {names}")
        await db2.close()

    print("\nSTARTUP OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))