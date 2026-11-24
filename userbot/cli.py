"""CLI второго аккаунта.

Команды:
  login   — разовый вход (код из Telegram + пароль 2FA)
  status  — проверить, что сессия жива
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .client import UserConfigError, build_client
from .login import login


async def status() -> int:
    try:
        uc = build_client()
    except UserConfigError as exc:
        print(f"\n❌ {exc}\n", file=sys.stderr)
        return 1

    try:
        await uc.client.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Не удалось подключиться: {exc}", file=sys.stderr)
        return 1

    if not await uc.client.is_user_authorized():
        print("\n❌ Не авторизован. Сначала выполни: python run_userbot.py login")
        await uc.client.disconnect()
        return 1

    me = await uc.client.get_me()
    name = " ".join(filter(None, [me.first_name, me.last_name])) or "?"
    print(f"\n✅ Сессия жива: {name} (@{me.username}) — id {me.id}")
    await uc.client.disconnect()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_userbot.py",
        description="Второй аккаунт Telegram (MTProto)",
    )
    parser.add_argument(
        "command",
        choices=["login", "status"],
        help="login — войти; status — проверить сессию",
    )
    args = parser.parse_args(argv)

    if args.command == "login":
        return asyncio.run(login())
    return asyncio.run(status())


if __name__ == "__main__":
    raise SystemExit(main())
