"""Импорт кружков из папки inbox прямо в ленту.

Берёт файлы .mp4/.mov, загружает их в Telegram как видеосообщения (кружки),
сохраняет file_id в базу и публикует — модерация не нужна, это твой контент.

Запуск:
    python tools/import_inbox.py            # залить всё, что в inbox
    python tools/import_inbox.py --dry-run  # только показать, что будет залито
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import FSInputFile  # noqa: E402

from bot.config import ConfigError, load_config  # noqa: E402
from bot.db import Database  # noqa: E402

INBOX = BASE_DIR / "inbox"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MAX_SIZE_MB = 49  # лимит Bot API на загрузку файла


def video_files() -> list[Path]:
    if not INBOX.exists():
        return []
    return sorted(
        path
        for path in INBOX.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


async def import_all(dry_run: bool) -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    files = video_files()
    if not files:
        print(f"📂 В папке {INBOX} нет видеофайлов.")
        return 0

    print(f"📂 Найдено файлов: {len(files)}")
    if dry_run:
        for path in files:
            size_mb = path.stat().st_size / 1024 / 1024
            print(f"   • {path.name} — {size_mb:.1f} МБ")
        print("\nЭто был пробный прогон. Запусти без --dry-run.")
        return 0

    db = Database(cfg.db_path)
    await db.connect()
    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    target = cfg.storage_channel_id or cfg.main_channel_id
    author = cfg.admin_ids[0]
    imported = 0
    skipped = 0

    try:
        for path in files:
            size_mb = path.stat().st_size / 1024 / 1024
            if size_mb > MAX_SIZE_MB:
                print(f"⏭  {path.name}: {size_mb:.0f} МБ — больше лимита {MAX_SIZE_MB} МБ")
                skipped += 1
                continue

            try:
                # Загружаем в Telegram как кружок: Bot API сам создаст file_id.
                stored = await bot.send_video_note(
                    chat_id=target,
                    video_note=FSInputFile(path),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"❌ {path.name}: {exc}")
                skipped += 1
                continue

            note = stored.video_note
            if note is None:
                print(f"❌ {path.name}: Telegram не вернул video_note")
                skipped += 1
                continue

            video = await db.create_video(
                author_id=author,
                file_id=note.file_id,
                file_unique_id=note.file_unique_id,
                duration=note.duration,
            )
            await db.publish_video(video.id, author)
            imported += 1
            print(f"✅ {path.name} → в ленте (#{video.public_id})")

        print(f"\nИтог: загружено {imported}, пропущено {skipped}")
        if imported:
            print("Удали или перемести файлы из inbox, чтобы не заливать их снова.")
        return 0 if imported or not skipped else 1
    finally:
        await bot.session.close()
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Импорт кружков из inbox")
    parser.add_argument("--dry-run", action="store_true", help="только показать файлы")
    args = parser.parse_args()
    return asyncio.run(import_all(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())