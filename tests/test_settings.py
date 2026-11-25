"""Тесты админских настроек: валидация, сохранение, применение, сброс."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.db import Database  # noqa: E402
from bot.settings import (  # noqa: E402
    BY_KEY,
    SettingError,
    current_rows,
    load_settings,
    parse_value,
    save_setting,
)
from tests.test_access import make_config  # noqa: E402


class TestSettings(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "s.db")
        await self.db.connect()
        self.cfg = make_config()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def test_free_views_can_be_changed(self):
        setting, value = await save_setting(self.db, self.cfg, "FREE_VIEWS", "25", 1)
        self.assertEqual(value, 25)
        self.assertEqual(self.cfg.free_views, 25)
        self.assertEqual(setting.key, "FREE_VIEWS")
        self.assertEqual(await self.db.get_setting("FREE_VIEWS"), "25")

    async def test_invalid_number_rejected(self):
        with self.assertRaises(SettingError):
            await save_setting(self.db, self.cfg, "FREE_VIEWS", "abc")
        # Значение не должно измениться.
        self.assertEqual(self.cfg.free_views, 10)

    async def test_negative_rejected(self):
        with self.assertRaises(SettingError):
            await save_setting(self.db, self.cfg, "PAY_PACK_SIZE", "0")
        self.assertEqual(self.cfg.pay_pack_size, 10)

    async def test_bool_setting(self):
        await save_setting(self.db, self.cfg, "FEED_INCLUDE_OWN", "1")
        self.assertTrue(self.cfg.feed_include_own)
        await save_setting(self.db, self.cfg, "FEED_INCLUDE_OWN", "0")
        self.assertFalse(self.cfg.feed_include_own)

    async def test_saved_settings_survive_reload(self):
        await save_setting(self.db, self.cfg, "PAY_PACK_STARS", "99")

        fresh = make_config()  # как при перезапуске: значения из .env
        self.assertEqual(fresh.pay_pack_stars, 35)

        applied = await load_settings(self.db, fresh)
        self.assertIn("PAY_PACK_STARS", applied)
        self.assertEqual(fresh.pay_pack_stars, 99)

    async def test_broken_stored_value_does_not_crash(self):
        await self.db.set_setting("FREE_VIEWS", "не число")
        fresh = make_config()
        await load_settings(self.db, fresh)
        self.assertEqual(fresh.free_views, 10)  # осталось из .env

    async def test_unknown_key_rejected(self):
        with self.assertRaises(SettingError):
            await save_setting(self.db, self.cfg, "HACK", "1")

    async def test_current_rows_covers_all_settings(self):
        rows = current_rows(self.cfg)
        self.assertEqual(len(rows), len(BY_KEY))
        keys = {setting.key for setting, _ in rows}
        self.assertIn("FREE_VIEWS", keys)
        self.assertIn("PAY_PACK_STARS", keys)

    async def test_reset_restores_env_values(self):
        await save_setting(self.db, self.cfg, "FREE_VIEWS", "999")
        self.assertEqual(self.cfg.free_views, 999)

        # Сброс = удалить сохранённое и перечитать .env.
        for key in await self.db.get_settings():
            await self.db.delete_setting(key)
        self.assertEqual(await self.db.get_settings(), {})

        fresh = make_config()
        await load_settings(self.db, fresh)
        self.assertEqual(fresh.free_views, 10)

    async def test_parse_value_limits(self):
        pack = BY_KEY["PAY_PACK_SIZE"]
        with self.assertRaises(SettingError):
            parse_value(pack, "0")
        self.assertEqual(parse_value(pack, "5"), 5)
        with self.assertRaises(SettingError):
            parse_value(BY_KEY["FEED_INCLUDE_OWN"], "может быть")


if __name__ == "__main__":
    unittest.main()