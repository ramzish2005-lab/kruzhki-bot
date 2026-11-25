"""Сквозной сценарий рефералки: .env -> ссылка -> привязка -> награда."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from bot.config import load_config  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.handlers.referrals import REF_PREFIX, apply_referral, build_link  # noqa: E402


async def main() -> None:
    cfg = load_config()
    print(f"Тариф: {cfg.free_views} бесплатных, +{cfg.referral_views} за друга, "
          f"пакет {cfg.pay_pack_size} за {cfg.pay_pack_stars} ⭐")
    assert cfg.free_views == 3, "ожидали 3 бесплатных"
    assert cfg.referral_views == 2, "ожидали 2 за друга"
    print("OK: тариф из .env правильный")

    assert cfg.bot_username, "BOT_USERNAME пуст — ссылка не будет кликабельной"
    print(f"OK: BOT_USERNAME = {cfg.bot_username}")

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "e2e.db")
        await db.connect()

        # Пользователь A (приглашающий)
        await db.touch_user(100, "alice", "Алиса", cfg.free_views)
        code = await db.ensure_ref_code(100)
        link = build_link(cfg, code)
        print(f"OK: ссылка Алисы -> {link}")

        # Пользователь B приходит по ссылке (как будто нажал /start ref_КОД)
        await db.touch_user(200, "bob", "Боб", cfg.free_views)
        applied = await apply_referral(db, cfg, 200, f"{REF_PREFIX}{code}")
        assert applied, "привязка не сработала"
        print("OK: Боб привязан к Алисе")

        # Боб подписался -> начисляем (как делает reward_if_subscribed)
        result = await db.reward_referrer(200, cfg.referral_views)
        assert result is not None, "награда не начислена"
        referrer_id, total = result
        alice = await db.get_user(100)
        print(f"OK: Алиса получила +{cfg.referral_views} (баланс {alice.balance}, друзей {total})")
        assert alice.balance == cfg.free_views + cfg.referral_views

        # Повторная попытка не должна начислить ещё раз
        again = await db.reward_referrer(200, cfg.referral_views)
        assert again is None, "награда начислена дважды!"
        alice = await db.get_user(100)
        assert alice.balance == cfg.free_views + cfg.referral_views
        print("OK: повторная награда заблокирована")

        await db.close()

    print("\nREFERRAL E2E OK")


if __name__ == "__main__":
    asyncio.run(main())