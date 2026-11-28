"""Обёртка над Railway CLI: статус, логи, деплой последнего коммита.

Запуск:
    python tools/railway.py status
    python tools/railway.py deploys
    python tools/railway.py build-logs --lines 60
    python tools/railway.py deploy-logs --lines 60
    python tools/railway.py redeploy
    python tools/railway.py vars

Токен берётся из .env (RAILWAY_TOKEN), проект и среда — RAILWAY_PROJECT_ID /
RAILWAY_ENVIRONMENT. Вручную подставлять токен в команды не нужно.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CLI = BASE_DIR / "tools" / "bin" / "railway.exe"

sys.path.insert(0, str(BASE_DIR))

from setup_env import current_value, load_lines  # noqa: E402


def env_value(key: str) -> str:
    return current_value(load_lines(), key)


def railway(args: list[str], timeout: int = 180) -> tuple[int, str]:
    """Вызывает railway.exe, подставляя токен из .env."""
    if not CLI.exists():
        return 127, f"❌ Не найден {CLI}. Запусти tools/set_railway_token.py"

    token = env_value("RAILWAY_TOKEN")
    if not token:
        return 401, (
            "❌ RAILWAY_TOKEN не заполнен.\n"
            "   Railway → проект → Settings → Tokens → Create Token\n"
            "   Затем: python tools/set_railway_token.py"
        )

    env = os.environ.copy()
    env["RAILWAY_TOKEN"] = token
    env["RAILWAY_NO_AUTO_UPDATE"] = "1"
    env["NO_COLOR"] = "1"
    for key in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT"):
        value = env_value(key)
        if value:
            env[key] = value

    try:
        proc = subprocess.run(
            [str(CLI), *args],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return 124, "⏱ Railway не ответил вовремя"
    except OSError as exc:
        return 1, f"❌ Не удалось запустить CLI: {exc}"

    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def scope_args() -> list[str]:
    """Флаги проекта и среды, если они известны."""
    args: list[str] = []
    project = env_value("RAILWAY_PROJECT_ID")
    environment = env_value("RAILWAY_ENVIRONMENT")
    if project:
        args += ["-p", project]
    if environment:
        args += ["-e", environment]
    return args


def resolve_service() -> str | None:
    """Определяет сервис: из .env или единственный в проекте."""
    known = env_value("RAILWAY_SERVICE")
    if known:
        return known

    code, out = railway(["status", "--json", *scope_args()])
    if code != 0 or "{" not in out:
        return None

    try:
        data = json.loads(out[out.index("{"):])
    except json.JSONDecodeError:
        return None

    services = data.get("services")
    if isinstance(services, dict) and services:
        key = next(iter(services))
        entry = services[key]
        if isinstance(entry, dict):
            return entry.get("name") or key
        return key
    if isinstance(services, list) and services:
        first = services[0]
        if isinstance(first, dict):
            return first.get("name")
        return str(first)
    return None


def cmd_status() -> int:
    code, out = railway(["status", *scope_args()])
    print(out)
    return code


def cmd_deploys(limit: int) -> int:
    args = ["deployment", "list", "--limit", str(limit), *scope_args()]
    service = resolve_service()
    if service:
        args += ["-s", service]
    code, out = railway(args)
    print(out)
    return code


def cmd_logs(kind: str, lines: int) -> int:
    flag = "-b" if kind == "build" else "-d"
    args = ["logs", "--lines", str(lines), flag, *scope_args()]
    service = resolve_service()
    if service:
        args += ["-s", service]
    code, out = railway(args)
    print(out)
    return code


def cmd_redeploy() -> int:
    args = ["deployment", "redeploy", "--from-source", "-y", *scope_args()]
    service = resolve_service()
    if service:
        args += ["-s", service]
    print("Деплою последний коммит (--from-source)…")
    code, out = railway(args, timeout=300)
    print(out)
    return code


def cmd_vars() -> int:
    args = ["variable", "--kv", *scope_args()]
    service = resolve_service()
    if service:
        args += ["-s", service]
    code, out = railway(args)
    for line in out.splitlines():
        if "=" in line:
            print(f"{line.split('=', 1)[0]}=<скрыто>")
        else:
            print(line)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Railway: статус, логи, деплой")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="проект и последний деплой")
    p_deploys = sub.add_parser("deploys", help="список деплоев")
    p_deploys.add_argument("--limit", type=int, default=10)

    for name, help_text in (
        ("build-logs", "логи сборки"),
        ("deploy-logs", "логи запуска"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--lines", type=int, default=60)

    sub.add_parser("redeploy", help="задеплоить последний коммит")
    sub.add_parser("vars", help="список переменных (значения скрыты)")

    args = parser.parse_args(argv)

    if args.command == "status":
        return cmd_status()
    if args.command == "deploys":
        return cmd_deploys(args.limit)
    if args.command == "build-logs":
        return cmd_logs("build", args.lines)
    if args.command == "deploy-logs":
        return cmd_logs("deploy", args.lines)
    if args.command == "redeploy":
        return cmd_redeploy()
    if args.command == "vars":
        return cmd_vars()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
