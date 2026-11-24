"""Готовит проект к деплою на Railway: git-репозиторий и проверка перед пушем.

Запуск: python tools/prepare_deploy.py
Ничего опасного не делает: только git init/commit и проверки.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

SECRETS = ("BOT_TOKEN", "TG_API_HASH")


def run(*args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8"
        )
    except (FileNotFoundError, OSError):
        return 127, ""
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def has_git() -> bool:
    code, _ = run("git", "--version")
    return code == 0


def is_repo() -> bool:
    code, _ = run("git", "rev-parse", "--git-dir")
    return code == 0


def check_env_not_tracked() -> bool:
    code, out = run("git", "ls-files")
    tracked = out.splitlines()
    leaked = [f for f in tracked if f.strip() in (".env", "data/bot.db")]
    if leaked:
        print(f"❌ В git попали секреты: {', '.join(leaked)}")
        return False
    print("✅ .env и база в git не попадут")
    return True


def main() -> int:
    if not has_git():
        print("❌ Git не установлен. Скачай: https://git-scm.com/download/win")
        print("   Перезапусти этот скрипт после установки.")
        return 1

    if not is_repo():
        print("Инициализирую git-репозиторий…")
        run("git", "init", "-b", "main")

    run("git", "add", "-A")
    code, out = run("git", "commit", "-m", "Kruzhki bot")
    if code != 0 and "nothing to commit" not in out:
        print(out.strip())
    else:
        print("✅ Коммит создан")

    if not check_env_not_tracked():
        return 1

    print("\nГотово к загрузке на GitHub:")
    print("  1) Создай пустой репозиторий на github.com/new (без README)")
    print("  2) Выполни в этой папке две команды, которые покажет GitHub")
    print("     (git remote add origin … и git push -u origin main)")
    print("\nПосле этого: railway.com → New Project → Deploy from GitHub repo")
    print("Инструкция целиком: README.md → «Деплой на Railway»")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())