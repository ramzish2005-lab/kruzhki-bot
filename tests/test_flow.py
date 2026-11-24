"""Интеграционные тесты пользовательского пути через диспетчер aiogram.

Проверяют реальную маршрутизацию апдейтов: /start, ленту, гейт спонсоров,
начисление бонуса и обработку платежа — с фейковым Telegram API.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.exceptions import TelegramBadRequest  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    ChatFullInfo,
    ChatMemberMember,
    Message,
    Update,
    User as TgUser,
    VideoNote,
)

from bot.config import Config, Sponsor  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.handlers import admin, feed, moderation, payments, sponsors, start, submit  # noqa: E402
from run import DepsMiddleware  # noqa: E402

USER_ID = 7001
ADMIN_ID = 9001
MAIN_CHANNEL = -1001
SOURCE_CHANNEL = -3001
SPONSOR_A = -2001
SPONSOR_B = -2002


class FakeSession(BaseSession):
    """Перехватывает вызовы Telegram API и запоминает их."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self.subscribed: set[tuple[int, int]] = set()
        self.sent: list[tuple[int, object]] = []

    async def close(self) -> None:  # pragma: no cover - интерфейс
        pass

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout=None):
        self.requests.append(method)
        name = type(method).__name__

        if name == "GetMe":
            return TgUser(id=555, is_bot=True, first_name="Bot", username="test_bot")

        if name == "GetChatMember":
            chat_id, user_id = method.chat_id, method.user_id
            if (chat_id, user_id) in self.subscribed:
                return ChatMemberMember(user=TgUser(id=user_id, is_bot=False, first_name="U"))
            # Так Telegram и отвечает, если пользователь не состоит в канале.
            raise TelegramBadRequest(
                method=method, message="Bad Request: user not found"
            )

        if name in ("SendMessage", "SendVideoNote", "SendInvoice", "EditMessageText"):
            chat_id = getattr(method, "chat_id", None) or 0
            self.sent.append((chat_id, method))
            return Message(
                message_id=len(self.sent),
                date=datetime.now(timezone.utc),
                chat=Chat(id=chat_id, type="private"),
            )

        if name == "GetChat":
            return ChatFullInfo(id=method.chat_id, type="channel", title="T")

        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""


def make_config(db_path: Path) -> Config:
    return Config(
        bot_token="123:token",
        admin_ids=(ADMIN_ID,),
        main_channel_id=MAIN_CHANNEL,
        main_channel_url="https://t.me/main",
        storage_channel_id=None,
        free_views=2,
        bonus_views=3,
        sponsors=(
            Sponsor(SPONSOR_A, "https://t.me/a", "A"),
            Sponsor(SPONSOR_B, "https://t.me/b", "B"),
        ),
        pay_pack_size=10,
        pay_pack_stars=35,
        pay_pack_rub=50,
        payment_mode="stars",
        provider_token="",
        db_path=db_path,
        feed_include_own=False,
        source_channel_id=SOURCE_CHANNEL,
    )


def text_of(method) -> str:
    return getattr(method, "text", "") or ""


class FlowTestCase(unittest.IsolatedAsyncioTestCase):
    """Один Dispatcher на класс: роутеры — модульные синглтоны.

    Переключаем зависимости между тестами через middleware, чтобы у каждого
    теста была своя чистая база.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._cls_tmp = tempfile.TemporaryDirectory()
        placeholder = Path(cls._cls_tmp.name) / "placeholder.db"
        cls.middleware = DepsMiddleware(make_config(placeholder), Database(placeholder))
        cls.dp = Dispatcher()
        cls.dp.update.middleware(cls.middleware)
        for router in (
            admin.router,
            moderation.router,
            payments.router,
            sponsors.router,
            submit.router,
            feed.router,
            start.router,
        ):
            cls.dp.include_router(router)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cls_tmp.cleanup()

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "flow.db")
        await self.db.connect()
        self.cfg = make_config(Path(self._tmp.name) / "flow.db")

        # Подключаем свежие зависимости к уже собранному диспетчеру.
        self.middleware.cfg = self.cfg
        self.middleware.db = self.db

        self.session = FakeSession()
        self.bot = Bot(token="123:token", session=self.session)
        self.dp = type(self).dp
        self._update_id = 0

    async def asyncTearDown(self) -> None:
        await self.bot.session.close()
        await self.db.close()
        self._tmp.cleanup()

    # ------------------------------------------------------------- helpers

    def _update(self, **kwargs) -> Update:
        self._update_id += 1
        return Update(update_id=self._update_id, **kwargs)

    def _message(
        self,
        text: str | None = None,
        video_note: VideoNote | None = None,
        successful_payment=None,
    ) -> Message:
        return Message(
            message_id=self._update_id + 1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=USER_ID, type="private"),
            from_user=TgUser(id=USER_ID, is_bot=False, first_name="Вася", username="vasya"),
            text=text,
            video_note=video_note,
            successful_payment=successful_payment,
        )

    def _callback(self, data: str, admin: bool = False) -> CallbackQuery:
        user_id = ADMIN_ID if admin else USER_ID
        return CallbackQuery(
            id=f"cb{self._update_id}",
            from_user=TgUser(id=user_id, is_bot=False, first_name="U"),
            chat_instance="ci",
            data=data,
            message=Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=user_id, type="private"),
            ),
        )

    async def send_text(self, text: str) -> None:
        await self.dp.feed_update(self.bot, self._update(message=self._message(text=text)))

    async def send_callback(self, data: str, admin: bool = False) -> None:
        callback = self._callback(data, admin=admin)
        await self.dp.feed_update(self.bot, self._update(callback_query=callback))

    def texts_sent(self) -> list[str]:
        return [text_of(m) for _, m in self.session.sent]

    def video_notes_sent(self) -> list:
        return [m for _, m in self.session.sent if type(m).__name__ == "SendVideoNote"]

    async def publish_sample(self, author_id: int = 4242) -> int:
        video = await self.db.create_video(author_id, "FILE_ID_1", "UNIQ_1", 10)
        await self.db.publish_video(video.id, ADMIN_ID)
        return video.id

    # --------------------------------------------------------------- tests

    async def test_start_requires_main_subscription(self):
        await self.send_text("/start")

        self.assertTrue(
            any("подпишись на наш канал" in t for t in self.texts_sent()),
            self.texts_sent(),
        )
        user = await self.db.get_user(USER_ID)
        self.assertFalse(user.main_sub_ok)
        self.assertEqual(user.balance, 2)  # бесплатные начислены при регистрации

    async def test_feed_shows_video_and_spends_view(self):
        await self.db.touch_user(USER_ID, "vasya", "Вася", 2)
        self.session.subscribed.add((MAIN_CHANNEL, USER_ID))
        await self.publish_sample()

        await self.send_text("▶️ Смотреть кружки")

        notes = self.video_notes_sent()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].video_note, "FILE_ID_1")

        user = await self.db.get_user(USER_ID)
        self.assertEqual(user.balance, 1)
        self.assertEqual(user.total_views, 1)

    async def test_feed_blocked_without_main_subscription(self):
        await self.db.touch_user(USER_ID, "vasya", "Вася", 2)
        await self.publish_sample()

        await self.send_text("▶️ Смотреть кружки")

        self.assertEqual(self.video_notes_sent(), [])
        self.assertTrue(any("Доступ только для подписчиков" in t for t in self.texts_sent()))

    async def test_unsubscribed_user_loses_access_on_start(self):
        """Отписка должна закрывать доступ, даже если раньше он был открыт."""
        await self.db.touch_user(USER_ID, "vasya", "Вася", 2)
        self.session.subscribed.add((MAIN_CHANNEL, USER_ID))
        await self.send_text("/start")

        # Подписка была — доступ открыт.
        self.assertTrue(any("Доступ открыт" in t for t in self.texts_sent()))
        self.assertTrue((await self.db.get_user(USER_ID)).main_sub_ok)

        # Пользователь отписался и снова жмёт /start.
        self.session.subscribed.clear()
        self.session.sent.clear()
        await self.send_text("/start")

        self.assertTrue(any("подпишись на наш канал" in t for t in self.texts_sent()))
        self.assertFalse((await self.db.get_user(USER_ID)).main_sub_ok)

    async def test_sponsor_gate_grants_bonus_once(self):
        from bot.keyboards import CheckSubCB

        await self.db.touch_user(USER_ID, "vasya", "Вася", 0)
        self.session.subscribed.update(
            {(MAIN_CHANNEL, USER_ID), (SPONSOR_A, USER_ID), (SPONSOR_B, USER_ID)}
        )

        await self.send_callback(CheckSubCB(target="sponsors").pack())

        user = await self.db.get_user(USER_ID)
        self.assertEqual(user.balance, 3)
        self.assertTrue(user.bonus_granted)

        await self.send_callback(CheckSubCB(target="sponsors").pack())

        user = await self.db.get_user(USER_ID)
        self.assertEqual(user.balance, 3)

    async def test_payment_credits_views(self):
        from aiogram.types import SuccessfulPayment

        await self.db.touch_user(USER_ID, "vasya", "Вася", 0)

        payment = SuccessfulPayment(
            currency="XTR",
            total_amount=35,
            invoice_payload=f"views:{USER_ID}:10",
            telegram_payment_charge_id="charge-xyz",
            provider_payment_charge_id="prov-1",
        )
        message = self._message(successful_payment=payment)
        await self.dp.feed_update(self.bot, self._update(message=message))

        user = await self.db.get_user(USER_ID)
        self.assertEqual(user.balance, 10)
        self.assertTrue(any("Оплата получена" in t for t in self.texts_sent()))

    async def test_submit_video_note_reaches_admin(self):
        await self.db.touch_user(USER_ID, "vasya", "Вася", 2)
        note = VideoNote(file_id="NEW_NOTE", file_unique_id="UQ", length=240, duration=10)

        await self.dp.feed_update(self.bot, self._update(message=self._message(video_note=note)))

        admin_sent = [m for chat_id, m in self.session.sent if chat_id == ADMIN_ID]
        self.assertTrue(admin_sent, "админ не получил кружок")
        self.assertEqual(await self.db.count_pending(), 1)

    async def test_admin_approve_publishes_to_feed(self):
        from bot.keyboards import ModerationCB

        await self.db.touch_user(USER_ID, "vasya", "Вася", 2)
        video = await self.db.create_video(USER_ID, "NOTE", "UQ", 10)

        await self.send_callback(ModerationCB(action="ok", item_id=video.id).pack(), admin=True)

        self.assertEqual(await self.db.count_published(), 1)
        self.assertEqual(await self.db.count_pending(), 0)

    async def test_non_admin_cannot_approve(self):
        from bot.keyboards import ModerationCB

        video = await self.db.create_video(USER_ID, "NOTE", "UQ", 10)

        await self.send_callback(ModerationCB(action="ok", item_id=video.id).pack(), admin=False)

        self.assertEqual(await self.db.count_published(), 0)
        self.assertEqual(await self.db.count_pending(), 1)


if __name__ == "__main__":
    unittest.main()
