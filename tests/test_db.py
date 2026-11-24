"""Тесты хранилища: квоты, лента без повторов, идемпотентность платежей."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.db import Database  # noqa: E402


class DbTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def make_user(self, user_id: int = 1, free_views: int = 10):
        user, is_new = await self.db.touch_user(user_id, "tester", "Тест", free_views)
        self.assertTrue(is_new)
        return user


class TestUsers(DbTestCase):
    async def test_free_views_granted_once(self):
        user = await self.make_user(free_views=10)
        self.assertEqual(user.balance, 10)
        self.assertTrue(user.free_granted)

        # Повторный заход не должен начислять просмотры снова.
        user2, is_new = await self.db.touch_user(1, "tester", "Тест", 10)
        self.assertFalse(is_new)
        self.assertEqual(user2.balance, 10)

    async def test_spend_view_decrements_and_counts(self):
        await self.make_user(free_views=2)
        self.assertTrue(await self.db.spend_view(1))
        self.assertTrue(await self.db.spend_view(1))
        self.assertFalse(await self.db.spend_view(1))

        user = await self.db.get_user(1)
        self.assertEqual(user.balance, 0)
        self.assertEqual(user.total_views, 2)

    async def test_bonus_granted_only_once(self):
        await self.make_user(free_views=0)
        self.assertTrue(await self.db.grant_bonus_once(1, 10))
        self.assertFalse(await self.db.grant_bonus_once(1, 10))
        user = await self.db.get_user(1)
        self.assertEqual(user.balance, 10)
        self.assertTrue(user.bonus_granted)


class TestVideos(DbTestCase):
    async def test_publish_flow_and_approved_counter(self):
        await self.make_user()
        video = await self.db.create_video(1, "FILEID", "UNIQ", 12)
        self.assertEqual(video.status, "pending")
        self.assertEqual(await self.db.count_pending(), 1)

        self.assertTrue(await self.db.publish_video(video.id, 999))
        self.assertEqual(await self.db.count_published(), 1)
        self.assertEqual(await self.db.count_pending(), 0)

        user = await self.db.get_user(1)
        self.assertEqual(user.submitted, 1)
        self.assertEqual(user.approved, 1)

        # Повторная модерация того же кружка невозможна.
        self.assertFalse(await self.db.publish_video(video.id, 999))

    async def test_reject_flow(self):
        await self.make_user()
        video = await self.db.create_video(1, "FILEID", "UNIQ", 12)
        self.assertTrue(await self.db.reject_video(video.id, 999, "нет"))
        self.assertFalse(await self.db.reject_video(video.id, 999, "нет"))

        user = await self.db.get_user(1)
        self.assertEqual(user.submitted, 1)
        self.assertEqual(user.approved, 0)

    async def test_feed_no_repeats_and_skips_own(self):
        await self.make_user(1, free_views=100)
        await self.make_user(2, free_views=100)

        own = await self.db.create_video(1, "OWN", "U1", 5)
        other = await self.db.create_video(2, "OTHER", "U2", 5)
        await self.db.publish_video(own.id, 999)
        await self.db.publish_video(other.id, 999)

        first = await self.db.next_video_for_user(1, include_own=False)
        self.assertIsNotNone(first)
        self.assertEqual(first.id, other.id)

        await self.db.mark_seen(1, first.id)
        second = await self.db.next_video_for_user(1, include_own=False)
        self.assertIsNone(second)

    async def test_feed_can_include_own(self):
        await self.make_user(1, free_views=100)
        own = await self.db.create_video(1, "OWN", "U1", 5)
        await self.db.publish_video(own.id, 999)

        found = await self.db.next_video_for_user(1, include_own=True)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, own.id)

    async def test_pending_not_in_feed(self):
        await self.make_user(1, free_views=100)
        video = await self.db.create_video(1, "F", "U", 5)
        self.assertIsNone(await self.db.next_video_for_user(1, include_own=True))
        self.assertEqual(video.status, "pending")


class TestPayments(DbTestCase):
    async def test_payment_is_idempotent(self):
        await self.make_user(free_views=0)

        first = await self.db.register_payment(1, "charge-1", 35, "XTR", 10)
        second = await self.db.register_payment(1, "charge-1", 35, "XTR", 10)

        self.assertTrue(first)
        self.assertFalse(second)
        user = await self.db.get_user(1)
        self.assertEqual(user.balance, 10)

    async def test_stats(self):
        await self.make_user(1, free_views=5)
        await self.db.spend_view(1)
        video = await self.db.create_video(1, "F", "U", 5)
        await self.db.publish_video(video.id, 999)
        await self.db.register_payment(1, "c-1", 50, "RUB", 10)

        stats = await self.db.stats()
        self.assertEqual(stats.users, 1)
        self.assertEqual(stats.published, 1)
        self.assertEqual(stats.views, 1)
        self.assertEqual(stats.payments, 1)
        self.assertEqual(stats.amount, 50)


class TestLikes(DbTestCase):
    async def test_toggle_like(self):
        await self.make_user()
        video = await self.db.create_video(1, "F", "U", 5)
        self.assertTrue(await self.db.toggle_like(1, video.id))
        self.assertFalse(await self.db.toggle_like(1, video.id))


if __name__ == "__main__":
    unittest.main()
