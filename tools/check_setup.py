"""Проверяет, заполнены ли обязательные поля в .env.

Код возврата 0 — всё на месте, 1 — нужен мастер настройки.
Запускается из start.bat перед мастером.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from setup_env import current_value, load_lines  # noqa: E402

REQUIRED = (
    "BOT_TOKEN",
    "ADMIN_IDS",
    "MAIN_CHANNEL_ID",
    "MAIN_CHANNEL_URL",
    "SOURCE_CHANNEL_ID",
)


def main() -> int:
    lines = load_lines()
    missing = [key for key in REQUIRED if not current_value(lines, key)]

    if not missing:
        print("✅ Настройки заполнены.")
        return 0

    print("⚠️  Не заполнено: " + ", ".join(missing))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())