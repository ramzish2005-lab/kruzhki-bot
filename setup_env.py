"""Мастер настройки: спрашивает значения и сам записывает их в .env.

Запуск:
    python setup_env.py

Ничего вручную в файлах править не нужно — просто отвечай на вопросы
и жми Enter. Уже заполненные значения показываются как «заполнено»
и по Enter сохраняются.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
EXAMPLE_PATH = BASE_DIR / ".env.example"

# Значения из .env.example: считаем их пустыми, чтобы мастер их переспросил.
PLACEHOLDERS = {
    "123456789:AAExampleTokenFromBotFather",
    "123456789",
    "-1001234567890",
    "https://t.me/your_channel",
    "-1001111111111|https://t.me/sponsor_one|Канал №1,"
    "-1002222222222|https://t.me/sponsor_two|Канал №2,"
    "-1003333333333|https://t.me/sponsor_three|Канал №3",
}


def load_lines() -> list[str]:
    if not ENV_PATH.exists():
        return EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def current_value(lines: list[str], key: str) -> str:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            value = line[len(prefix):].strip().strip('"').strip("'")
            return "" if value in PLACEHOLDERS else value
    return ""


def set_value(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            return lines
    lines.append(f"{prefix}{value}")
    return lines


def _read_line() -> str:
    """Читает строку, устойчиво к кодировке консоли Windows.

    При вводе с клавиатуры берём обычный input(). При перенаправлении
    потока (пайп, файл) читаем байты и пробуем utf-8, затем cp866/cp1251,
    иначе кириллица превращается в «?????».
    """
    if sys.stdin is not None and sys.stdin.isatty():
        return input()

    raw = sys.stdin.buffer.readline()
    if not raw:
        raise EOFError
    for encoding in ("utf-8-sig", "utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()


def ask(label: str, key: str, lines: list[str], hint: str = "", required: bool = False) -> None:
    old = current_value(lines, key)
    shown = "заполнено" if old else "пусто"

    print()
    print(f"— {label}")
    if hint:
        print(f"  {hint}")
    print(f"  сейчас: {shown}")

    try:
        raw = _read_line().strip()
    except (EOFError, KeyboardInterrupt):
        print("\nОтменено.")
        sys.exit(1)

    if raw:
        lines[:] = set_value(lines, key, raw)
    elif required and not old:
        print("  ⚠️  Это поле обязательно, но оставлено пустым.")


def main() -> int:
    print("=" * 62)
    print("  НАСТРОЙКА БОТА «КРУЖКИ»")
    print("  Всё пишется в .env автоматически. Enter — пропустить.")
    print("=" * 62)

    lines = load_lines()

    print("\n=== ТОКЕН И ТВОЙ ID ===")
    ask(
        "Токен бота",
        "BOT_TOKEN",
        lines,
        "BotFather → /newbot → скопируй «123456:AA...»",
        required=True,
    )
    ask(
        "Твой Telegram ID",
        "ADMIN_IDS",
        lines,
        "@userinfobot пришлёт число. Сюда приходят кружки на проверку",
        required=True,
    )

    print("\n=== КАНАЛ 1: НОВОСТНОЙ ===")
    print("  На него подписываются, чтобы пользоваться ботом.")
    ask(
        "ID новостного канала",
        "MAIN_CHANNEL_ID",
        lines,
        "Вида -1001234567890. Бот должен быть АДМИНОМ этого канала",
        required=True,
    )
    ask(
        "Ссылка на новостной канал",
        "MAIN_CHANNEL_URL",
        lines,
        "Например https://t.me/mychannel",
        required=True,
    )

    print("\n=== КАНАЛ 2: КУДА ТЫ КИДАЕШЬ КРУЖКИ ===")
    print("  Всё, что ты туда отправишь, сразу появится в ленте бота.")
    ask(
        "ID канала с кружками",
        "SOURCE_CHANNEL_ID",
        lines,
        "Вида -1001234567890. Бот должен быть АДМИНОМ этого канала",
        required=True,
    )

    print("\n--- РЕКЛАМА (можно пропустить) ---")
    ask(
        "Каналы-спонсоры",
        "SPONSORS",
        lines,
        "Формат: -100111|https://t.me/a|Канал1,-100222|https://t.me/b|Канал2",
    )

    print("\n--- ВТОРОЙ АККАУНТ (можно пропустить) ---")
    print("  Нужен только для импорта кружков из чужих каналов.")
    ask("api_id", "TG_API_ID", lines, "my.telegram.org → API development tools")
    ask("api_hash", "TG_API_HASH", lines, "оттуда же, вторая строка")
    ask("Телефон", "TG_PHONE", lines, "формат +79991234567")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n✅ Сохранено в {ENV_PATH}")

    # Короткая проверка: обязательные поля на месте.
    missing = [
        key
        for key in (
            "BOT_TOKEN",
            "ADMIN_IDS",
            "MAIN_CHANNEL_ID",
            "MAIN_CHANNEL_URL",
            "SOURCE_CHANNEL_ID",
        )
        if not current_value(load_lines(), key)
    ]
    if missing:
        print(f"⚠️  Не заполнено: {', '.join(missing)}")
        print("   Запусти мастер ещё раз.")
        return 1

    print("Дальше: .\\.venv\\Scripts\\python.exe run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())