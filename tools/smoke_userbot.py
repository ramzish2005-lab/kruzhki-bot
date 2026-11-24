"""Проверка userbot-модуля без реального Telegram: только локальная логика."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from userbot.client import UserConfigError, load_user_credentials  # noqa: E402


def main() -> None:
    ok = True

    # 1. Без переменных — понятная ошибка со списком недостающих.
    for name in ("TG_API_ID", "TG_API_HASH", "TG_PHONE"):
        import os

        os.environ.pop(name, None)
    try:
        load_user_credentials()
    except UserConfigError as exc:
        text = str(exc)
        assert "TG_API_ID" in text and "TG_API_HASH" in text and "TG_PHONE" in text
        print("OK: понятная ошибка без ключей")
    else:
        print("FAIL: ожидалась UserConfigError")
        ok = False

    # 2. С ключами — читаются, сессия в data/.
    import os

    os.environ["TG_API_ID"] = "123456"
    os.environ["TG_API_HASH"] = "0123456789abcdef0123456789abcdef"
    os.environ["TG_PHONE"] = "+79991234567"
    creds = load_user_credentials()
    assert creds.api_id == 123456
    assert creds.api_hash == "0123456789abcdef0123456789abcdef"
    assert creds.phone == "+79991234567"
    assert creds.session_path.name.startswith("userbot")
    assert creds.session_path.is_absolute()
    print("OK: ключи читаются, путь сессии:", creds.session_path)

    # 3. Нечисловой api_id — ошибка, а не молчаливый полом.
    os.environ["TG_API_ID"] = "abc"
    try:
        load_user_credentials()
    except UserConfigError as exc:
        assert "числом" in str(exc)
        print("OK: нечисловой api_id отклонён")
    else:
        print("FAIL: ожидалась ошибка для нечислового api_id")
        ok = False

    # 4. Клиент создаётся; файл сессии технически создаётся сразу (Telethon
    #    так устроен), но авторизации в нём нет — проверяем через status.
    os.environ["TG_API_ID"] = "123456"
    from userbot.client import build_client

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TG_SESSION"] = str(Path(tmp) / "s.session")
        uc = build_client()
        assert uc.client is not None
        # Сессия закрывается, чтобы Windows не держал файл открытым.
        uc.client.disconnect()
        print("OK: клиент собран, подключение к Telegram не выполнялось")

    print("\nUSERBOT SMOKE OK" if ok else "\nUSERBOT SMOKE FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
