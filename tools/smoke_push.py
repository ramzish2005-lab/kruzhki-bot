"""Проверка фонового цикла напоминаний: стартует, работает, отменяется."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from bot.db import Database  # noqa: E402
from bot.services.push import notification_loop, send_wave  # noqa: E402
from tests.test_feed_order import make_config  # noqa: E402
from tests.test_flow import FakeSession  # noqa: E402
from aiogram import Bot  # noqa: E402


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "loop.db")
        await db.connect()
        cfg = make_config(Path(tmp) / "loop.db")

        session = FakeSession()
        bot = Bot(token="123:token", session=session)

        # 1. Цикл запускается и не падает сразу.
        task = asyncio.create_task(notification_loop(bot, db, cfg))
        await asyncio.sleep(0.05)
        assert not task.done(), "цикл не должен завершаться сам"
        print("OK: цикл запущен и висит в ожидании интервала")

        # 2. Отменяется без ошибок.
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            print("OK: цикл корректно отменён")

        # 3. Волна доставляет сообщение живому пользователю с кружком.
        await db.touch_user(777, None, "Тест", 3)
        video = await db.create_video(4242, "FILEX", "UNIQX", 8)
        await db.publish_video(video.id, 9001)

        sent = await send_wave(bot, db, cfg)
        assert sent == 1, f"ожидали 1 доставку, получили {sent}"
        print("OK: волна доставила напоминание")

        # 4. Повторная волна не выдаёт второй кружок по той же кнопке.
        await send_wave(bot, db, cfg)
        first_id = 1
        assert await db.claim_notification(777, first_id), "первая выдача должна пройти"
        assert not await db.claim_notification(777, first_id), "вторая выдача должна быть отклонена"
        print("OK: повторное нажатие блокируется")

        await bot.session.close()
        await db.close()

    print("\nPUSH LOOP OK")


if __name__ == "__main__":
    asyncio.run(main())