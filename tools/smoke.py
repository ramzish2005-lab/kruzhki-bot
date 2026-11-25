"""Смоук-тест: диспетчер собирается, клавиатуры и тексты валидны, без сети."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import texts  # noqa: E402
from bot.config import Sponsor  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.keyboards import (  # noqa: E402
    CheckSubCB,
    FeedCB,
    MenuCB,
    ModerationCB,
    PayCB,
    SponsorCB,
    feed_kb,
    main_menu,
    moderation_kb,
    pay_gate,
    reply_menu,
    sponsor_gate,
    sub_gate,
)
from run import build_dispatcher  # noqa: E402


def fake_config():
    from bot.config import Config

    return Config(
        bot_token="123:token",
        admin_ids=(1,),
        main_channel_id=-1001,
        main_channel_url="https://t.me/main",
        storage_channel_id=-1002,
        free_views=10,
        bonus_views=10,
        sponsors=(Sponsor(-2001, "https://t.me/s1", "S1"),),
        pay_pack_size=10,
        pay_pack_stars=35,
        pay_pack_rub=50,
        payment_mode="stars",
        provider_token="",
        db_path=Path("data/smoke.db"),
        feed_include_own=False,
    )


def main() -> None:
    cfg = fake_config()

    # 1. Диспетчер и все роутеры.
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "smoke.db")
        dp = build_dispatcher(cfg, db)
        routers = [r.name for r in dp.sub_routers]
        assert routers, "нет подключённых роутеров"
        print("routers:", routers)
        types = dp.resolve_used_update_types()
        print("update types:", types)
        for expected in ("message", "callback_query", "pre_checkout_query"):
            assert expected in types, f"не подписан на {expected}"

    # 2. Callback-данные пакуются и распаковываются.
    assert MenuCB.unpack(MenuCB(action="feed").pack()) == MenuCB(action="feed")
    like_cb = FeedCB.unpack(FeedCB(action="like", item_id=42).pack())
    assert like_cb.action == "like" and like_cb.item_id == 42
    mod_cb = ModerationCB.unpack(ModerationCB(action="ok", item_id=5).pack())
    assert mod_cb.action == "ok" and mod_cb.item_id == 5
    assert PayCB.unpack(PayCB(size=10).pack()).size == 10
    assert SponsorCB.unpack(SponsorCB(index=2).pack()).index == 2
    assert CheckSubCB.unpack(CheckSubCB(target="sponsors").pack()).target == "sponsors"

    # 3. Клавиатуры собираются.
    keyboards = [
        main_menu(),
        reply_menu(),
        reply_menu(is_admin=True),
        sub_gate(cfg.main_channel_url),
        sponsor_gate([("S1", "https://t.me/s1")], 10),
        pay_gate(10, "35 ⭐"),
        feed_kb(7),
        moderation_kb(7),
    ]
    for kb in keyboards:
        assert kb is not None
    print("keyboards OK:", len(keyboards))

    # 4. Тексты форматируются без KeyError.
    formatted = [
        texts.START.format(name="Тест", status=texts.STATUS_OK.format(views=10)),
        texts.STATUS_NEED_SPONSORS.format(bonus=10),
        texts.STATUS_NEED_PAY.format(size=10, price="35 ⭐"),
        texts.GATE_SPONSORS_REQUIRED.format(bonus=10, left=3),
        texts.GATE_SPONSORS_NOT_YET.format(left=2),
        texts.GATE_NO_VIEWS.format(referral=2, size=10, price="50 ₽"),
        texts.REFERRAL_TEXT.format(
            views=2, link="https://t.me/b?start=ref_x", count=3, earned=6
        ),
        texts.REFERRAL_BONUS.format(views=2, balance=5),
        texts.REFERRAL_NEW_USER,
        texts.FEED_VIEWS_LEFT.format(views=9),
        texts.SUBMIT_TOO_LONG.format(seconds=60),
        texts.MODERATION_CAPTION.format(author="@u", public_id="abcd1234", user_id=1),
        texts.MODERATION_DONE_APPROVE.format(public_id="abcd1234"),
        texts.PAY_SUCCESS.format(views=10),
        texts.ADMIN_STATS.format(
            users=1, active=1, published=1, pending=0, views=1,
            payments=0, amount=0, sponsor_subs=0,
        ),
    ]
    for text in formatted:
        assert text
    print("texts OK:", len(formatted))

    # 5. Валидация конфига: без ADMIN_IDS должен быть ConfigError.
    from bot.config import ConfigError, load_config

    try:
        load_config()
    except ConfigError as exc:
        print("config validation OK:", str(exc)[:60])
    else:
        print("config loaded from .env (файл существует)")

    print("\nSMOKE OK")


if __name__ == "__main__":
    main()
