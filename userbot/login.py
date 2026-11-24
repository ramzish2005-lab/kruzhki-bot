"""Вход во второй аккаунт: один раз вводишь код из Telegram и пароль 2FA.

После этого создаётся файл data/userbot.session, и при следующих запусках
код вводить не нужно.
"""

from __future__ import annotations

import asyncio
import sys

from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from .client import UserConfigError, build_client


async def login() -> int:
    try:
        uc = build_client()
    except UserConfigError as exc:
        print(f"\n❌ {exc}\n", file=sys.stderr)
        return 1

    print(f"📱 Вход в аккаунт {uc.creds.phone}…")
    print(f"   Сессия: {uc.creds.session_path}")
    print("   Telegram пришлёт код. Введи его ниже.")

    try:
        client = await uc.__aenter__()
    except PhoneNumberInvalidError:
        print(
            "\n❌ Номер телефона не принят Telegram. "
            "Проверь TG_PHONE в .env (формат +79991234567).",
            file=sys.stderr,
        )
        return 1
    except SessionPasswordNeededError:
        print("\n⚠️  Нужен пароль двухфакторной аутентификации.")
        return 1
    except PhoneCodeInvalidError:
        print("\n❌ Неверный код подтверждения.", file=sys.stderr)
        return 1
    except PasswordHashInvalidError:
        print("\n❌ Неверный пароль 2FA.", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Не удалось войти: {exc}", file=sys.stderr)
        return 1

    try:
        me = await client.get_me()
        name = " ".join(filter(None, [me.first_name, me.last_name])) or "?"
        print(f"\n✅ Готово: {name} (@{me.username}) — id {me.id}")
        print("   Сессия сохранена, код больше не понадобится.")
        return 0
    finally:
        await uc.__aexit__(None, None, None)


def main() -> int:
    return asyncio.run(login())


if __name__ == "__main__":
    raise SystemExit(main())
