"""Тест порядка проверок в ленте: доступ -> наличие кружков -> списание."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402
from aiogram.types import Chat, Message, User as TgUser  # noqa: E402

from bot.config import Config  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.services.feed import show_next  # noqa: E402
from tests.test_flow import FakeSession  # noqa: E402

USER_ID = 5001
MAIN_CHANNEL = -1001


def make_config(db_path: Path, free_views: int = 3) -> Config:
    return Config(
        bot_token="123:token",
        admin_ids=(9001,),
        main_channel_id=MAIN_CHANNEL,
        main_channel_url="https://t.me/main",
        storage_channel_id=None,
        free_views=free_views,
        bonus_views=0,
        sponsors=(),
        pay_pack_size=5,
        pay_pack_stars=20,
        pay_pack_rub=50,
        payment_mode="stars",
        provider_token="",
        db_path=db_path,
        feed_include_own=False,
        source_channel_id=None,
        referral_views=2,
        bot_username="test_bot",
    )


class TestFeedOrder(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "feed.db")
        await self.db.connect()
        self.cfg = make_config(Path(self._tmp.name) / "feed.db")

        self.session = FakeSession()
        self.session.subscribed.add((MAIN_CHANNEL, USER_ID))
        self.bot = Bot(token="123:token", session=self.session)

        # aiogram не даёт звать send_video_note напрямую — подменяем на запись.
        self.sent_notes: list[tuple[int, str]] = []

        async def fake_send_video_note(chat_id: int, video_note: str, reply_markup=None):
            self.sent_notes.append((chat_id, video_note))
            return None

        self.bot.send_video_note = fake_send_video_note  # type: ignore[assignment]

        self.message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=USER_ID, type="private"),
            from_user=TgUser(id=USER_ID, is_bot=False, first_name="Вася"),
            text="▶️ Смотреть кружки",
        ).as_(self.bot)

    async def asyncTearDown(self) -> None:
        await self.bot.session.close()
        await self.db.close()
        self._tmp.cleanup()

    def texts(self) -> list[str]:
        return [getattr(m, "text", "") or "" for _, m in self.session.sent]

    def buttons(self) -> str:
        """Текст кнопок инлайн-клавиатур — варианты «друг / купить» живут там."""
        parts: list[str] = []
        for _, method in self.session.sent:
            markup = getattr(method, "reply_markup", None)
            if markup is None:
                continue
            for row in getattr(markup, "inline_keyboard", []):
                for button in row:
                    parts.append(getattr(button, "text", "") or "")
        return " ".join(parts)

    async def test_zero_views_with_empty_feed_shows_gate_not_empty_message(self):
        """Твой случай: кружков нет И просмотры кончились -> гейт, а не «все посмотрел»."""
        await self.db.touch_user(USER_ID, "v", "Вася", 0)

        ok = await show_next(self.message, self.bot, self.db, self.cfg, USER_ID)

        self.assertFalse(ok)
        combined = " ".join(self.texts())
        buttons = self.buttons()
        self.assertIn("Пригласи друга", combined)
        self.assertIn("Пригласить друга", buttons)
        self.assertIn("Купить", buttons)
        self.assertNotIn("нет кружков", combined)

    async def test_views_left_but_empty_feed(self):
        """Есть просмотры, но лента пустая -> сообщение про пустую ленту, без списания."""
        await self.db.touch_user(USER_ID, "v", "Вася", 3)

        await show_next(self.message, self.bot, self.db, self.cfg, USER_ID)

        combined = " ".join(self.texts())
        self.assertIn("нет кружков", combined)
        user = await self.db.get_user(USER_ID)
        self.assertEqual(user.balance, 3, "просмотр не должен списываться")

    async def test_empty_feed_does_not_show_paywall(self):
        await self.db.touch_user(USER_ID, "v", "Вася", 3)

        await show_next(self.message, self.bot, self.db, self.cfg, USER_ID)

        self.assertNotIn("Бесплатные просмотры закончились", " ".join(self.texts()))

    async def test_has_video_and_views_shows_video(self):
        await self.db.touch_user(USER_ID, "v", "Вася", 3)
        video = await self.db.create_video(4242, "FILE", "UNIQ", 8)
        await self.db.publish_video(video.id, 9001)

        ok = await show_next(self.message, self.bot, self.db, self.cfg, USER_ID)

        self.assertTrue(ok)
        self.assertEqual(len(self.sent_notes), 1)
        self.assertEqual(self.sent_notes[0][1], "FILE")
        user = await self.db.get_user(USER_ID)
        self.assertEqual(user.balance, 2)

    async def test_not_subscribed_shows_sub_gate_first(self):
        """Без подписки гейт подписки важнее любых других сообщений."""
        self.session.subscribed.clear()
        await self.db.touch_user(USER_ID, "v", "Вася", 0)

        await show_next(self.message, self.bot, self.db, self.cfg, USER_ID)

        combined = " ".join(self.texts())
        self.assertIn("подписчиков канала", combined)
        self.assertNotIn("Пригласи друга", combined)

    async def test_blocked_user_gets_error(self):
        await self.db.touch_user(USER_ID, "v", "Вася", 3)
        await self.db.set_blocked(USER_ID, True)

        await show_next(self.message, self.bot, self.db, self.cfg, USER_ID)

        self.assertTrue(self.texts())


if __name__ == "__main__":
    unittest.main()