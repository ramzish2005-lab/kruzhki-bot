"""Настройка доступа к Railway: сохраняет токен в .env и находит проект.

Запуск: python tools/set_railway_token.py

Токен вводится один раз и записывается в .env (в git и Docker-образ не попадает).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from setup_env import ENV_PATH, load_lines, set_value  # noqa: E402
from tools.railway import railway  # noqa: E402


def ask_token() -> str:
    print()
    print("1) Railway → открой проект kruzhki-bot")
    print("2) Settings (проекта) → раздел Tokens")
    print("3) Create Token → имя local-dev → среда production")
    print("4) Скопируй токен и вставь сюда")
    print()
    print("Вставь токен Railway и нажми Enter:")
    sys.stdout.write("> ")
    sys.stdout.flush()
    return input().strip()


def main() -> int:
    token = ask_token()
    if len(token) < 10:
        print("\n❌ Слишком короткий токен. Скопируй целиком.")
        return 1

    lines = set_value(load_lines(), "RAILWAY_TOKEN", token)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n✅ Токен сохранён в .env")

    print("\nИщу проекты, доступные этому токену…")
    code, out = railway(["list", "--json"])
    if code != 0:
        print(out)
        print("\n⚠️  Не удалось получить список проектов.")
        print("   Значит токен не рабочий либо это токен без доступа к проекту.")
        return 1

    try:
        projects = json.loads(out[out.index("["):])
    except (ValueError, json.JSONDecodeError):
        print(out)
        return 1

    if not projects:
        print("⚠️  Токен не видит ни одного проекта.")
        print("   Проверь, что при создании токена была выбрана среда production.")
        return 1

    if len(projects) == 1:
        project = projects[0]
    else:
        print("\nДоступные проекты:")
        for index, item in enumerate(projects, start=1):
            print(f"  {index}) {item.get('name')} — {item.get('id')}")
        sys.stdout.write("\nНомер проекта: ")
        sys.stdout.flush()
        try:
            choice = int(input().strip() or "1")
        except ValueError:
            choice = 1
        project = projects[max(0, min(choice - 1, len(projects) - 1))]

    project_id = project.get("id") or ""
    project_name = project.get("name") or "?"

    lines = set_value(load_lines(), "RAILWAY_PROJECT_ID", project_id)
    lines = set_value(lines, "RAILWAY_ENVIRONMENT", "production")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n✅ Проект: {project_name}")
    print(f"   ID: {project_id}")
    print("   Среда: production")

    print("\nПроверяю доступ…")
    code, out = railway(["status"])
    print(out)
    if code != 0:
        print("\n⚠️  Статус не получен — смотри сообщение выше.")
        return 1

    print("\nГотово. Дальше можно:")
    print("  python tools/railway.py deploys")
    print("  python tools/railway.py build-logs --lines 60")
    print("  python tools/railway.py redeploy     # последний коммит")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())