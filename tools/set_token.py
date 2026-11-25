"""Меняет токен бота в .env и печатает готовый блок для Railway.

Запуск: python tools/set_token.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from setup_env import ENV_PATH, load_lines, set_value  # noqa: E402

RAILWAY_KEYS = [
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


def read_token() -> str:
    print()
    print("1) Открой @BotFather в Telegram")
    print("2) /mybots → твой бот → API Token → Revoke current token")
    print("3) Скопируй новый токен (вида 123456789:AAH...)")
    print()
    print("Вставь токен сюда и нажми Enter:")
    sys.stdout.write("> ")
    sys.stdout.flush()
    return input().strip()


def main() -> int:
    token = read_token()

    if ":" not in token or not token.split(":", 1)[0].isdigit():
        print("\n❌ Это не похоже на токен. Он должен быть вида 123456789:AAH...")
        return 1

    lines = set_value(load_lines(), "BOT_TOKEN", token)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n✅ Токен записан в .env")

    values = {key: "" for key in RAILWAY_KEYS}
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            if key in values:
                values[key] = value.strip()

    block = [f"{key}={value}" for key, value in values.items()]
    block += ["DATA_DIR=/data", "DB_PATH=bot.db"]
    text = "\n".join(block)

    out_file = BASE_DIR / "railway_vars.txt"
    out_file.write_text(text + "\n", encoding="utf-8")

    print("\n" + "=" * 58)
    print("  ЭТО ВСТАВЬ НА RAILWAY (Variables → Raw Editor)")
    print("=" * 58)
    print(text)
    print("=" * 58)
    print(f"\nЭтот же текст сохранён в файл:\n  {out_file}")
    print("Его можно открыть блокнотом и скопировать целиком.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())