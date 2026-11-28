"""Тесты напоминаний: отправка, выдача одного кружка, защита от повторов."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, User as TgUser  # noqa: E402

from bot.db import Database  # noqa: E402
from bot.handlers.push import on_push_button  # noqa: E402
from bot.keyboards import PushCB  # noqa: E402
from bot.services.push import notify_user, send_wave  # noqa: E402
from tests.test_feed_order import make_config  # noqa: E402
from tests.test_flow import FakeSession  # noqa: E402

USER_ID = 6001


class PushTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "push.db")
        await self.db.connect()
        self.cfg = make_config(Path(self._tmp.name) / "push.db")
        self.session = FakeSession()
        self.bot = Bot(token="123:token", session=self.session)
        self.sent_notes: list[str] = []

        async def fake_send_video_note(chat_id, video_note, reply_markup=None):
            self.sent_notes.append(video_note)
            return None

        self.bot.send_video_note = fake_send_video_note  # type: ignore[assignment]

    async def asyncTearDown(self) -> None:
        await self.bot.session.close()
        await self.db.close()
        self._tmp.cleanup()

    async def add_video(self, author: int = 4242, uniq: str = "U1") -> int:
        video = await self.db.create_video(author, f"FILE_{uniq}", uniq, 8)
        await self.db.publish_video(video.id, 9001)
        return video.id

    def messages(self) -> list[str]:
        return [getattr(m, "text", "") or "" for _, m in self.session.sent]

    # ------------------------------------------------------------------ push

    async def test_no_push_when_feed_is_empty(self):
        await self.db.touch_user(USER_ID, None, "U", 3)
        self.assertFalse(await notify_user(self.bot, self.db, self.cfg, USER_ID))
        self.assertEqual(self.messages(), [])

    async def test_push_sent_when_unseen_video_exists(self):
        await self.db.touch_user(USER_ID, None, "U", 3)
        await self.add_video()

        self.assertTrue(await notify_user(self.bot, self.db, self.cfg, USER_ID))
        self.assertEqual(len(self.messages()), 1)
        self.assertTrue(self.messages()[0])

    async def test_push_has_button(self):
        await self.db.touch_user(USER_ID, None, "U", 3)
        await self.add_video()
        await notify_user(self.bot, self.db, self.cfg, USER_ID)

        _, method = self.session.sent[-1]
        markup = method.reply_markup
        self.assertIsNotNone(markup, "у напоминания должна быть кнопка")
        button = markup.inline_keyboard[0][0]
        self.assertIn("push:", button.callback_data or "")

    async def test_wave_reaches_users(self):
        await self.db.touch_user(USER_ID, None, "U", 3)
        await self.db.touch_user(USER_ID + 1, None, "U2", 3)
        await self.add_video()

        sent = await send_wave(self.bot, self.db, self.cfg)
        self.assertEqual(sent, 2)

    async def test_blocked_user_skipped(self):
        await self.db.touch_user(USER_ID, None, "U", 3)
        await self.db.set_blocked(USER_ID, True)
        await self.add_video()

        self.assertEqual(await send_wave(self.bot, self.db, self.cfg), 0)

    # --------------------------------------------------------------- кнопка

    def callback(self, notification_id: int) -> CallbackQuery:
        message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=USER_ID, type="private"),
        ).as_(self.bot)
        return CallbackQuery(
            id="cb1",
            from_user=TgUser(id=USER_ID, is_bot=False, first_name="U"),
            chat_instance="ci",
            data=PushCB(notification_id=notification_id).pack(),
            message=message,
        ).as_(self.bot)

    async def test_button_sends_one_free_video(self):
        await self.db.touch_user(USER_ID, None, "U", 0)
        await self.add_video()
        notification_id = await self.db.create_notification(USER_ID, "test")

        call = self.callback(notification_id)
        await on_push_button(call, PushCB(notification_id=notification_id), self.bot, self.db, self.cfg)

        self.assertEqual(len(self.sent_notes), 1)
        user = await self.db.get_user(USER_ID)
        self.assertEqual(user.balance, 0, "просмотры не должны тратиться")

    async def test_button_works_only_once(self):
        await self.db.touch_user(USER_ID, None, "U", 0)
        await self.add_video()
        await self.add_video(uniq="U2")
        notification_id = await self.db.create_notification(USER_ID, "test")

        payload = PushCB(notification_id=notification_id)
        await on_push_button(self.callback(notification_id), payload, self.bot, self.db, self.cfg)
        await on_push_button(self.callback(notification_id), payload, self.bot, self.db, self.cfg)

        self.assertEqual(len(self.sent_notes), 1, "второй раз кружок не выдаётся")

    async def test_foreign_notification_rejected(self):
        await self.db.touch_user(USER_ID, None, "U", 0)
        await self.db.touch_user(USER_ID + 5, None, "Other", 0)
        await self.add_video()
        foreign = await self.db.create_notification(USER_ID + 5, "test")

        await on_push_button(
            self.callback(foreign), PushCB(notification_id=foreign), self.bot, self.db, self.cfg
        )

        self.assertEqual(self.sent_notes, [])


class TestPushSchedule(unittest.IsolatedAsyncioTestCase):
    """Расписание не сбрасывается при перезапуске бота."""

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "sched.db")
        await self.db.connect()
        self.cfg = make_config(Path(self._tmp.name) / "sched.db")

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def test_first_push_soon_after_start(self):
        from bot.services.push import FIRST_PUSH_DELAY, seconds_until_next

        self.assertEqual(await seconds_until_next(self.db, self.cfg), FIRST_PUSH_DELAY)

    async def test_waits_full_interval_after_push(self):
        from bot.db import iso
        from bot.services.push import LAST_PUSH_KEY, seconds_until_next

        await self.db.set_setting(LAST_PUSH_KEY, iso())
        delay = await seconds_until_next(self.db, self.cfg)

        # Сразу после отправки ждём почти весь интервал (3 часа).
        self.assertGreater(delay, 3 * 3600 - 10)
        self.assertLessEqual(delay, 3 * 3600)

    async def test_old_timestamp_means_send_now(self):
        from datetime import datetime, timedelta, timezone

        from bot.services.push import LAST_PUSH_KEY, seconds_until_next

        four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=4)
        await self.db.set_setting(LAST_PUSH_KEY, four_hours_ago.isoformat())

        self.assertEqual(await seconds_until_next(self.db, self.cfg), 0)

    async def test_interval_follows_setting(self):
        from datetime import datetime, timedelta, timezone

        from bot.services.push import LAST_PUSH_KEY, seconds_until_next

        self.cfg.notify_hours = 1
        hour_ago = datetime.now(timezone.utc) - timedelta(minutes=30)
        await self.db.set_setting(LAST_PUSH_KEY, hour_ago.isoformat())

        delay = await seconds_until_next(self.db, self.cfg)
        self.assertGreater(delay, 25 * 60)
        self.assertLessEqual(delay, 30 * 60 + 5)

    async def test_broken_timestamp_falls_back(self):
        from bot.services.push import FIRST_PUSH_DELAY, LAST_PUSH_KEY, seconds_until_next

        await self.db.set_setting(LAST_PUSH_KEY, "не дата")
        self.assertEqual(await seconds_until_next(self.db, self.cfg), FIRST_PUSH_DELAY)


if __name__ == "__main__":
    unittest.main()