"""Проверка готовности к деплою: git, .env, каналы, секреты.

Запуск: python tools/deploy_check.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from setup_env import current_value, load_lines  # noqa: E402

OK = "✅"
NO = "❌"
WARN = "⚠️ "


def run(*args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except (FileNotFoundError, OSError):
        return 127, ""
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    problems = 0
    lines = load_lines()

    print("=" * 62)
    print("  ПРОВЕРКА ПЕРЕД ДЕПЛОЕМ")
    print("=" * 62)

    # 1. Git
    code, out = run("git", "--version")
    if code == 0:
        print(f"{OK} Git установлен: {out.strip()}")
    else:
        print(f"{NO} Git НЕ установлен")
        print("   → Скачай: https://git-scm.com/download/win")
        print("   → При установке жми Next везде (настройки по умолчанию)")
        problems += 1

    # 2. Обязательные переменные
    required = {
        "BOT_TOKEN": "токен бота",
        "ADMIN_IDS": "твой Telegram ID",
        "MAIN_CHANNEL_ID": "ID новостного канала",
        "MAIN_CHANNEL_URL": "ссылка на новостной канал",
        "SOURCE_CHANNEL_ID": "ID канала с кружками",
    }
    missing = [
        f"{key} ({desc})"
        for key, desc in required.items()
        if not current_value(lines, key)
    ]
    if missing:
        print(f"{NO} Не заполнено в .env:")
        for item in missing:
            print(f"     • {item}")
        print("   → Запусти: python setup_env.py")
        problems += 1
    else:
        print(f"{OK} Все обязательные переменные заполнены")

    # 3. Тарифы
    print(
        f"{OK} Тариф: {current_value(lines, 'FREE_VIEWS')} бесплатно, "
        f"пакет {current_value(lines, 'PAY_PACK_SIZE')} за "
        f"{current_value(lines, 'PAY_PACK_STARS')} ⭐"
    )

    # 4. .env в git
    code, out = run("git", "ls-files")
    if code == 0:
        tracked = {line.strip() for line in out.splitlines()}
        if ".env" in tracked:
            print(f"{NO} Файл .env попал в git — там секреты!")
            print("   → Выполни: git rm --cached .env")
            problems += 1
        else:
            print(f"{OK} .env в git не попадёт")

    # 5. Railway-конфиги
    for name in ("railway.json", "nixpacks.toml", "requirements.txt"):
        if (BASE_DIR / name).exists():
            print(f"{OK} {name} на месте")
        else:
            print(f"{NO} Нет файла {name}")
            problems += 1

    print("=" * 62)
    if problems:
        print(f"Исправь {problems} пункт(а) выше, потом запусти снова.")
        return 1

    print("Всё готово! Дальше смотри README.md → «Деплой на Railway».")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())