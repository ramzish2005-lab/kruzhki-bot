"""Тесты автозабора кружков из канала-источника."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402
from aiogram.types import Chat, Message, VideoNote  # noqa: E402

from bot.config import Config, Sponsor  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.handlers.ingest import on_channel_video_note  # noqa: E402
from tests.test_flow import FakeSession  # noqa: E402

SOURCE_CHANNEL = -3001
ADMIN_ID = 9001


def make_config(db_path: Path, source_channel_id: int | None = SOURCE_CHANNEL) -> Config:
    return Config(
        bot_token="123:token",
        admin_ids=(ADMIN_ID,),
        main_channel_id=-1001,
        main_channel_url="https://t.me/main",
        storage_channel_id=None,
        free_views=10,
        bonus_views=10,
        sponsors=(Sponsor(-2001, "https://t.me/a", "A"),),
        pay_pack_size=10,
        pay_pack_stars=35,
        pay_pack_rub=50,
        payment_mode="stars",
        provider_token="",
        db_path=db_path,
        feed_include_own=False,
        source_channel_id=source_channel_id,
    )


class TestIngest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "ingest.db")
        await self.db.connect()
        self.cfg = make_config(Path(self._tmp.name) / "ingest.db")
        self.bot = Bot(token="123:token", session=FakeSession())
        self.sent: list = self.bot.session.sent

    async def asyncTearDown(self) -> None:
        await self.bot.session.close()
        await self.db.close()
        self._tmp.cleanup()

    def _post(self, chat_id: int, note: VideoNote) -> Message:
        return Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=chat_id, type="channel", title="Source"),
            video_note=note,
        )

    async def handle(self, chat_id: int, note: VideoNote) -> None:
        await on_channel_video_note(
            message=self._post(chat_id, note), bot=self.bot, db=self.db, cfg=self.cfg
        )

    async def test_note_from_source_channel_is_published(self):
        note = VideoNote(file_id="N1", file_unique_id="U1", length=320, duration=8)
        await self.handle(SOURCE_CHANNEL, note)

        self.assertEqual(await self.db.count_published(), 1)
        self.assertEqual(await self.db.count_pending(), 0)

    async def test_note_from_other_channel_ignored(self):
        note = VideoNote(file_id="N2", file_unique_id="U2", length=320, duration=8)
        await self.handle(-999999, note)

        self.assertEqual(await self.db.count_published(), 0)

    async def test_duplicate_note_added_once(self):
        note = VideoNote(file_id="N3", file_unique_id="U3", length=320, duration=8)
        await self.handle(SOURCE_CHANNEL, note)
        await self.handle(SOURCE_CHANNEL, note)

        self.assertEqual(await self.db.count_published(), 1)

    async def test_disabled_without_source_channel(self):
        self.cfg = make_config(Path(self._tmp.name) / "ingest.db", source_channel_id=None)
        note = VideoNote(file_id="N4", file_unique_id="U4", length=320, duration=8)
        await self.handle(SOURCE_CHANNEL, note)

        self.assertEqual(await self.db.count_published(), 0)

    async def test_admin_gets_confirmation(self):
        note = VideoNote(file_id="N5", file_unique_id="U5", length=320, duration=8)
        await self.handle(SOURCE_CHANNEL, note)

        to_admin = [m for chat_id, m in self.sent if chat_id == ADMIN_ID]
        self.assertTrue(to_admin, "админ не получил подтверждение")
        self.assertIn("в ленте", getattr(to_admin[-1], "text", ""))


if __name__ == "__main__":
    unittest.main()