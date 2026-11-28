"""Тесты реферальной системы: код, привязка, награда, защита от накрутки."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.db import Database  # noqa: E402
from bot.handlers.referrals import REF_PREFIX, apply_referral, build_link  # noqa: E402
from tests.test_access import make_config  # noqa: E402


class TestReferralCodes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "ref.db")
        await self.db.connect()
        self.cfg = make_config()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def make_user(self, user_id: int):
        user, _ = await self.db.touch_user(user_id, None, f"U{user_id}", 3)
        return user

    async def test_code_is_stable(self):
        await self.make_user(1)
        first = await self.db.ensure_ref_code(1)
        second = await self.db.ensure_ref_code(1)
        self.assertEqual(first, second)
        self.assertTrue(len(first) >= 6)

    async def test_codes_are_unique(self):
        codes = set()
        for user_id in range(1, 30):
            await self.make_user(user_id)
            codes.add(await self.db.ensure_ref_code(user_id))
        self.assertEqual(len(codes), 29)

    async def test_link_uses_username(self):
        cfg = make_config(bot_username="krughbot")
        link = build_link(cfg, "abc123")
        self.assertEqual(link, "https://t.me/krughbot?start=ref_abc123")

    async def test_link_accepts_username_argument(self):
        cfg = make_config(bot_username="")
        link = build_link(cfg, "abc123", "krughbot")
        self.assertEqual(link, "https://t.me/krughbot?start=ref_abc123")

    async def test_link_without_username_is_still_valid_url(self):
        cfg = make_config(bot_username="")
        link = build_link(cfg, "abc123")
        self.assertTrue(link.startswith("https://t.me/"))
        self.assertIn("ref_abc123", link)
        self.assertNotIn("укажи", link)

    async def test_username_is_resolved_and_cached(self):
        from bot.services.identity import bot_username

        cfg = make_config(bot_username="")

        class Me:
            username = "krughbot"

        class FakeBot:
            calls = 0

            async def get_me(self):
                FakeBot.calls += 1
                return Me()

        first = await bot_username(FakeBot(), cfg)
        second = await bot_username(FakeBot(), cfg)

        self.assertEqual(first, "krughbot")
        self.assertEqual(second, "krughbot")
        self.assertEqual(FakeBot.calls, 1, "getMe должен вызываться один раз")
        self.assertEqual(cfg.bot_username, "krughbot")

    async def test_apply_referral_links_users(self):
        await self.make_user(1)
        await self.make_user(2)
        code = await self.db.ensure_ref_code(1)

        applied = await apply_referral(self.db, self.cfg, 2, REF_PREFIX + code)

        self.assertTrue(applied)
        invitee = await self.db.get_user(2)
        self.assertEqual(invitee.referred_by, 1)

    async def test_second_referrer_does_not_override(self):
        await self.make_user(1)
        await self.make_user(3)
        await self.make_user(2)
        code_a = await self.db.ensure_ref_code(1)
        code_b = await self.db.ensure_ref_code(3)

        await apply_referral(self.db, self.cfg, 2, REF_PREFIX + code_a)
        await apply_referral(self.db, self.cfg, 2, REF_PREFIX + code_b)

        invitee = await self.db.get_user(2)
        self.assertEqual(invitee.referred_by, 1)  # первый победил

    async def test_self_referral_rejected(self):
        await self.make_user(1)
        code = await self.db.ensure_ref_code(1)
        applied = await apply_referral(self.db, self.cfg, 1, REF_PREFIX + code)

        self.assertFalse(applied)
        user = await self.db.get_user(1)
        self.assertIsNone(user.referred_by)

    async def test_unknown_code_ignored(self):
        await self.make_user(2)
        applied = await apply_referral(self.db, self.cfg, 2, REF_PREFIX + "nope0000")
        self.assertFalse(applied)

    async def test_bad_payload_ignored(self):
        await self.make_user(2)
        self.assertFalse(await apply_referral(self.db, self.cfg, 2, "что-то"))
        self.assertFalse(await apply_referral(self.db, self.cfg, 2, REF_PREFIX))


class TestReferralReward(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "ref.db")
        await self.db.connect()
        self.cfg = make_config()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def pair(self, views: int = 2):
        """Создаёт пригласившего (1) и друга (2), привязывает их."""
        await self.db.touch_user(1, None, "R", 3)
        await self.db.touch_user(2, None, "I", 3)
        code = await self.db.ensure_ref_code(1)
        await apply_referral(self.db, self.cfg, 2, REF_PREFIX + code)
        return views

    async def test_reward_goes_to_referrer(self):
        await self.pair()
        before = (await self.db.get_user(1)).balance

        result = await self.db.reward_referrer(2, 2)

        self.assertIsNotNone(result)
        referrer_id, total = result
        self.assertEqual(referrer_id, 1)
        self.assertEqual(total, 1)
        self.assertEqual((await self.db.get_user(1)).balance, before + 2)

    async def test_reward_once_per_friend(self):
        await self.pair()
        await self.db.reward_referrer(2, 2)
        after_first = (await self.db.get_user(1)).balance

        second = await self.db.reward_referrer(2, 2)

        self.assertIsNone(second)
        self.assertEqual((await self.db.get_user(1)).balance, after_first)

    async def test_no_reward_without_referrer(self):
        await self.db.touch_user(5, None, "Solo", 3)
        self.assertIsNone(await self.db.reward_referrer(5, 2))

    async def test_referral_counter_grows(self):
        await self.db.touch_user(1, None, "R", 3)
        await self.db.ensure_ref_code(1)

        for friend in (10, 11, 12):
            await self.db.touch_user(friend, None, f"F{friend}", 3)
            code = await self.db.ensure_ref_code(1)
            await apply_referral(self.db, self.cfg, friend, REF_PREFIX + code)
            await self.db.reward_referrer(friend, 2)

        referrer = await self.db.get_user(1)
        self.assertEqual(referrer.referrals, 3)
        self.assertEqual(referrer.balance, 3 + 6)


if __name__ == "__main__":
    unittest.main()