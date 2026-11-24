"""Точка входа CLI второго аккаунта Telegram.

Примеры:
  python run_userbot.py login
  python run_userbot.py status
"""

from __future__ import annotations

import sys

from userbot.cli import main

if __name__ == "__main__":
    sys.exit(main())
