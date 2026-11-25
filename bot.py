"""Точка входа для хостингов, которые ищут bot.py (Railpack, Railway).

Railpack определяет Python-проект и стартовую команду по именам файлов:
main.py, app.py, start.py, bot.py, hello.py, server.py.
У нас основной файл — run.py, поэтому bot.py просто пробрасывает запуск в него.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run import main  # noqa: E402

if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass