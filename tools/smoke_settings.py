"""Проверка админ-панели без сети: роутер, клавиатура, применение настроек."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from bot.db import Database  # noqa: E402
from bot.handlers import settings as settings_handler  # noqa: E402
from bot.keyboards import SettingsCB, settings_panel  # noqa: E402
from bot.settings import BY_KEY, current_rows, load_settings, save_setting  # noqa: E402
from tests.test_access import make_config  # noqa: E402


async def main() -> None:
    # 1. Роутер собрался и слушает нужные события.
    assert settings_handler.router.name == "settings"
    print("OK: роутер настроек подключён")

    # 2. Клавиатура строится по всем настройкам.
    cfg = make_config()
    rows = [(s.key, s.label, s.format(v)) for s, v in current_rows(cfg)]
    kb = settings_panel(rows)
    buttons = sum(len(row) for row in kb.inline_keyboard)
    assert buttons == len(rows) + 2, f"ожидали {len(rows) + 2} кнопок, получили {buttons}"
    print(f"OK: панель нарисована, кнопок {buttons}")

    # 3. Callback кодируется и декодируется.
    cb = SettingsCB(action="edit", key="FREE_VIEWS")
    assert SettingsCB.unpack(cb.pack()) == cb
    print("OK: callback настроек работает")

    # 4. Изменение применяется к живому конфигу.
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "s.db")
        await db.connect()

        await save_setting(db, cfg, "FREE_VIEWS", "7", 1)
        assert cfg.free_views == 7
        print("OK: FREE_VIEWS меняется сразу (7)")

        await save_setting(db, cfg, "PAY_PACK_STARS", "42", 1)
        assert cfg.pay_pack_stars == 42
        print("OK: PAY_PACK_STARS меняется сразу (42)")

        # 5. После «перезапуска» значение берётся из базы.
        fresh = make_config()
        await load_settings(db, fresh)
        assert fresh.free_views == 7 and fresh.pay_pack_stars == 42
        print("OK: настройки переживают перезапуск")

        await db.close()

    # 6. Все ключи панели существуют в конфиге.
    for key, setting in BY_KEY.items():
        assert hasattr(cfg, setting.attr), f"{key}: нет поля {setting.attr} в Config"
    print(f"OK: все {len(BY_KEY)} настроек привязаны к Config")

    print("\nSETTINGS SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())