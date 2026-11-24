"""Клиент второго аккаунта: читает api_id/api_hash/телефон из .env.

Токен бота здесь НЕ используется: это отдельный вход пользователя по MTProto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class UserConfigError(RuntimeError):
    """Не заполнены переменные второго аккаунта."""


@dataclass(frozen=True)
class UserCredentials:
    api_id: int
    api_hash: str
    phone: str
    session_path: Path


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def load_user_credentials() -> UserCredentials:
    """Читает TG_API_ID / TG_API_HASH / TG_PHONE из .env."""
    api_id_raw = _env("TG_API_ID")
    api_hash = _env("TG_API_HASH")
    phone = _env("TG_PHONE")

    missing = [
        name
        for name, value in (
            ("TG_API_ID", api_id_raw),
            ("TG_API_HASH", api_hash),
            ("TG_PHONE", phone),
        )
        if not value
    ]
    if missing:
        raise UserConfigError(
            "В .env не заполнено: "
            + ", ".join(missing)
            + ".\n1) Открой https://my.telegram.org\n"
            "2) API development tools → Create new application\n"
            "3) Впиши api_id и api_hash в .env, а в TG_PHONE — номер аккаунта"
        )

    if not api_id_raw.isdigit():
        raise UserConfigError("TG_API_ID должен быть числом без пробелов и кавычек")

    session_raw = _env("TG_SESSION") or "data/userbot.session"
    session_path = Path(session_raw)
    if not session_path.is_absolute():
        session_path = BASE_DIR / session_path

    return UserCredentials(
        api_id=int(api_id_raw),
        api_hash=api_hash,
        phone=phone,
        session_path=session_path,
    )


class UserClient:
    """Обёртка над TelegramClient, чтобы не дублировать сборку клиента."""

    def __init__(self, creds: UserCredentials) -> None:
        self.creds = creds
        creds.session_path.parent.mkdir(parents=True, exist_ok=True)
        # Telethon сам дописывает .session к имени файла.
        self.client = TelegramClient(
            str(creds.session_path), creds.api_id, creds.api_hash
        )

    async def __aenter__(self) -> TelegramClient:
        await self.client.start(phone=self.creds.phone)
        return self.client

    async def __aexit__(self, *args) -> None:
        await self.client.disconnect()


def build_client() -> UserClient:
    return UserClient(load_user_credentials())
