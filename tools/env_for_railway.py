"""Выводит значения из .env в формате для Railway (Variables → Raw Editor).

Запуск: python tools/env_for_railway.py
Секреты печатаются в консоль — никуда не отправляй скриншот с ними.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from setup_env import current_value, load_lines  # noqa: E402

# На Railway база должна жить на volume, иначе стирается при редеплое.
RAILWAY_EXTRA = {
    "DATA_DIR": "/data",
    "DB_PATH": "bot.db",
}


def main() -> int:
    lines = load_lines()
    keys = [
        "BOT_TOKEN",
        "ADMIN_IDS",
        "MAIN_CHANNEL_ID",
        "MAIN_CHANNEL_URL",
        "SOURCE_CHANNEL_ID",
        "STORAGE_CHANNEL_ID",
        "SPONSORS",
        "FREE_VIEWS",
        "BONUS_VIEWS",
        "PAYMENT_MODE",
        "PAY_PACK_SIZE",
        "PAY_PACK_STARS",
        "PAY_PACK_RUB",
        "PROVIDER_TOKEN",
        "FEED_INCLUDE_OWN",
    ]

    print("=" * 60)
    print("  ВСТАВЬ ЭТО НА RAILWAY: Variables → Raw Editor")
    print("=" * 60)
    print()

    out: list[str] = []
    for key in keys:
        value = current_value(lines, key)
        if key in ("BOT_TOKEN", "ADMIN_IDS", "MAIN_CHANNEL_ID", "MAIN_CHANNEL_URL",
                   "SOURCE_CHANNEL_ID"):
            if not value:
                print(f"⚠️  {key} пуст — заполни в .env и запусти снова")
        out.append(f"{key}={value}")

    for key, value in RAILWAY_EXTRA.items():
        out.append(f"{key}={value}")

    print("\n".join(out))
    print()
    print("=" * 60)
    print("  TG_API_ID / TG_API_HASH / TG_PHONE на Railway не нужны.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())