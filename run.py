"""Точка входа: сборка бота, middleware с зависимостями, запуск polling."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent, TelegramObject
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from bot.config import Config, ConfigError, load_config
from bot.db import Database
from bot.handlers import (
    admin,
    feed,
    ingest,
    moderation,
    payments,
    push as push_handler,
    referrals,
    settings as settings_handler,
    sponsors,
    start,
    submit,
)
from bot.services.push import notification_loop
from bot.settings import load_settings

log = logging.getLogger(__name__)


class DepsMiddleware(BaseMiddleware):
    """Прокидывает cfg и db в каждый хендлер как именованные аргументы."""

    def __init__(self, cfg: Config, db: Database) -> None:
        self.cfg = cfg
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["cfg"] = self.cfg
        data["db"] = self.db
        return await handler(event, data)


async def on_error(event: ErrorEvent) -> bool:
    """Логирует любое исключение в хендлерах, чтобы бот не падал."""
    log.exception("Ошибка при обработке апдейта: %s", event.exception)
    return True


def build_dispatcher(cfg: Config, db: Database) -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(DepsMiddleware(cfg, db))
    dp.callback_query.middleware(CallbackAnswerMiddleware())

    # Порядок важен: админ/модерация раньше пользовательских хендлеров.
    dp.include_router(admin.router)
    dp.include_router(settings_handler.router)
    dp.include_router(referrals.router)
    dp.include_router(push_handler.router)
    dp.include_router(moderation.router)
    dp.include_router(payments.router)
    dp.include_router(sponsors.router)
    dp.include_router(ingest.router)
    dp.include_router(submit.router)
    dp.include_router(feed.router)
    dp.include_router(start.router)
    return dp


async def check_bot_rights(bot: Bot, cfg: Config) -> None:
    """Предупреждает о каналах, где бот не админ: без этого подписка не проверяется."""
    targets: list[tuple[str, int]] = [("новостной канал", cfg.main_channel_id)]
    if cfg.source_channel_id:
        targets.append(("канал с кружками", cfg.source_channel_id))
    if cfg.storage_channel_id:
        targets.append(("хранилище", cfg.storage_channel_id))
    targets.extend((f"спонсор «{s.title}»", s.chat_id) for s in cfg.sponsors)

    for label, chat_id in targets:
        try:
            me = await bot.get_me()
            member = await bot.get_chat_member(chat_id=chat_id, user_id=me.id)
        except Exception as exc:  # noqa: BLE001
            log.warning("⚠️  %s (%s): нет доступа — %s", label, chat_id, exc)
            continue
        if member.status not in ("administrator", "creator"):
            log.warning(
                "⚠️  %s (%s): бот не админ (статус %s) — проверка подписки не сработает",
                label,
                chat_id,
                member.status,
            )
        else:
            log.info("✅ %s (%s): права админа есть", label, chat_id)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    try:
        cfg = load_config()
    except ConfigError as exc:
        log.error("Конфигурация не загружена: %s", exc)
        sys.exit(1)

    db = Database(cfg.db_path)
    await db.connect()
    log.info("База данных: %s", cfg.db_path)

    applied = await load_settings(db, cfg)
    if applied:
        log.info("Настройки из базы: %s", ", ".join(applied))
    log.info(
        "Тариф: %s бесплатных, пакет %s за %s ⭐",
        cfg.free_views,
        cfg.pay_pack_size,
        cfg.pay_pack_stars,
    )

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(cfg, db)
    dp.errors.register(on_error)

    try:
        me = await bot.get_me()
        log.info("Бот запущен: @%s", me.username)
        await check_bot_rights(bot, cfg)
        await bot.delete_webhook(drop_pending_updates=True)

        # Фоновый цикл напоминаний: бот сам пишет пользователям.
        push_task = asyncio.create_task(notification_loop(bot, db, cfg))

        try:
            await dp.start_polling(
                bot, allowed_updates=dp.resolve_used_update_types()
            )
        finally:
            push_task.cancel()
            try:
                await push_task
            except asyncio.CancelledError:
                pass
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
