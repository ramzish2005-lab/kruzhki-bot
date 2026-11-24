"""Тесты правил доступа: порядок гейтов free -> sponsors -> payment."""

from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Config, Sponsor  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.services.access import Gate, resolve_gate  # noqa: E402


class FakeMember:
    def __init__(self, status: str, is_member: bool | None = None) -> None:
        self.status = status
        self.is_member = is_member


class FakeChat:
    """Минимальный чат: нужен только факт, что канал существует."""

    def __init__(self, chat_id: int) -> None:
        self.id = chat_id
        self.title = f"chat{chat_id}"


class FakeBot:
    """Подменяет get_chat_member: отвечает по словарю подписок."""

    def __init__(self, subscribed: Iterable[int], known_chats: Iterable[int] = ()) -> None:
        self.subscribed = set(subscribed)
        self.known_chats = set(known_chats)
        self.calls: list[tuple[int, int]] = []

    async def get_chat_member(self, chat_id: int, user_id: int):
        self.calls.append((chat_id, user_id))
        if chat_id in self.subscribed:
            return FakeMember("member")
        return FakeMember("left")

    async def get_chat(self, chat_id: int):
        """Канал доступен, только если бот в нём состоит (как в реальности)."""
        if chat_id in self.subscribed or chat_id in self.known_chats:
            return FakeChat(chat_id)
        from aiogram.exceptions import TelegramBadRequest

        raise TelegramBadRequest(method=None, message="chat not found")


def make_config(**overrides) -> Config:
    base = Config(
        bot_token="123:token",
        admin_ids=(1,),
        main_channel_id=-1001,
        main_channel_url="https://t.me/main",
        storage_channel_id=None,
        free_views=10,
        bonus_views=10,
        sponsors=(
            Sponsor(chat_id=-2001, url="https://t.me/s1", title="S1"),
            Sponsor(chat_id=-2002, url="https://t.me/s2", title="S2"),
        ),
        pay_pack_size=10,
        pay_pack_stars=35,
        pay_pack_rub=50,
        payment_mode="stars",
        provider_token="",
        db_path=Path("data/test.db"),
        feed_include_own=False,
    )
    return replace(base, **overrides)


class GateTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        await self.db.connect()
        self.cfg = make_config()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def user(self, free_views: int = 10):
        user, _ = await self.db.touch_user(7, "u", "U", free_views)
        return user


class TestResolveGate(GateTestCase):
    async def test_no_main_sub_blocks_everything(self):
        bot = FakeBot(subscribed=[])  # нигде не подписан
        user = await self.user(free_views=10)
        self.assertIs(await resolve_gate(bot, self.db, self.cfg, user), Gate.MAIN_SUB)

    async def test_main_sub_with_balance_is_ok(self):
        bot = FakeBot(subscribed=[-1001])
        user = await self.user(free_views=10)
        self.assertIs(await resolve_gate(bot, self.db, self.cfg, user), Gate.OK)

    async def test_empty_balance_without_bonus_asks_sponsors(self):
        # Спонсоры рабочие (бот их видит), пользователь подписан только на новостной.
        bot = FakeBot(subscribed=[-1001], known_chats=[-1001, -2001, -2002])
        user = await self.user(free_views=0)
        self.assertIs(await resolve_gate(bot, self.db, self.cfg, user), Gate.SPONSORS)

    async def test_broken_sponsors_do_not_trap_user(self):
        """Если все каналы-спонсоры недоступны, пользователь идёт к оплате."""
        bot = FakeBot(subscribed=[-1001], known_chats=[-1001])
        user = await self.user(free_views=0)
        self.assertIs(await resolve_gate(bot, self.db, self.cfg, user), Gate.PAYMENT)

    async def test_no_bonus_when_bonus_views_zero(self):
        """BONUS_VIEWS=0: спонсоры настроены, но бонуса нет — сразу оплата."""
        cfg = make_config(bonus_views=0, sponsors=(
            Sponsor(chat_id=-2001, url="https://t.me/s1", title="S1"),
        ))
        bot = FakeBot(subscribed=[-1001], known_chats=[-1001, -2001])
        user = await self.user(free_views=5)
        for _ in range(5):
            await self.db.spend_view(7)

        user = await self.db.get_user(7)
        self.assertEqual(user.balance, 0)
        self.assertIs(await resolve_gate(bot, self.db, cfg, user), Gate.PAYMENT)

    async def test_empty_balance_after_bonus_asks_payment(self):
        bot = FakeBot(subscribed=[-1001])
        user = await self.user(free_views=0)
        await self.db.grant_bonus_once(7, 10)
        await self.db.spend_view(7)  # остаток 9
        for _ in range(9):
            await self.db.spend_view(7)

        user = await self.db.get_user(7)
        self.assertEqual(user.balance, 0)
        self.assertIs(await resolve_gate(bot, self.db, self.cfg, user), Gate.PAYMENT)

    async def test_blocked_user_gets_blocked_gate(self):
        bot = FakeBot(subscribed=[-1001])
        await self.user(free_views=10)
        await self.db.set_blocked(7, True)
        user = await self.db.get_user(7)
        self.assertIs(await resolve_gate(bot, self.db, self.cfg, user), Gate.BLOCKED)

    async def test_no_sponsors_configured_goes_straight_to_payment(self):
        cfg = make_config(sponsors=())
        bot = FakeBot(subscribed=[-1001])
        user = await self.user(free_views=0)
        self.assertIs(await resolve_gate(bot, self.db, cfg, user), Gate.PAYMENT)

    async def test_main_sub_state_is_cached(self):
        bot = FakeBot(subscribed=[-1001])
        user = await self.user(free_views=10)
        await resolve_gate(bot, self.db, self.cfg, user)
        cached = await self.db.get_user(7)
        self.assertTrue(cached.main_sub_ok)

    async def test_restricted_member_counts_as_subscribed(self):
        class RestrictedBot:
            async def get_chat_member(self, chat_id: int, user_id: int):
                return FakeMember("restricted", is_member=True)

        user = await self.user(free_views=10)
        self.assertIs(
            await resolve_gate(RestrictedBot(), self.db, self.cfg, user), Gate.OK
        )


if __name__ == "__main__":
    unittest.main()
