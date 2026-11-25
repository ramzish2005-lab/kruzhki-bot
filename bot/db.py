"""SQLite-хранилище: пользователи, кружки, просмотры, лайки, платежи.

Модель квот простая и защищена от сброса на клиенте:
  * при первом входе начисляется FREE_VIEWS;
  * после подписки на спонсоров один раз начисляется BONUS_VIEWS;
  * оплата начисляет пакет;
  * каждый показ кружка списывает 1 просмотр.
Всё считается только на сервере.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    username         TEXT,
    first_name       TEXT,
    created_at       TEXT NOT NULL,
    last_seen_at     TEXT NOT NULL,
    balance          INTEGER NOT NULL DEFAULT 0,
    free_granted     INTEGER NOT NULL DEFAULT 0,
    bonus_granted    INTEGER NOT NULL DEFAULT 0,
    main_sub_ok      INTEGER NOT NULL DEFAULT 0,
    total_views      INTEGER NOT NULL DEFAULT 0,
    submitted        INTEGER NOT NULL DEFAULT 0,
    approved         INTEGER NOT NULL DEFAULT 0,
    blocked          INTEGER NOT NULL DEFAULT 0,
    ref_code         TEXT,
    referred_by      INTEGER,
    referrals        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS videos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id          TEXT NOT NULL UNIQUE,
    author_id          INTEGER NOT NULL,
    file_id            TEXT NOT NULL,
    file_unique_id     TEXT,
    duration           INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'pending',
    created_at         TEXT NOT NULL,
    published_at       TEXT,
    moderated_by       INTEGER,
    reject_reason      TEXT,
    storage_message_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status, id);

CREATE TABLE IF NOT EXISTS seen (
    user_id       INTEGER NOT NULL,
    video_id      INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    times         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, video_id)
);

CREATE TABLE IF NOT EXISTS likes (
    user_id    INTEGER NOT NULL,
    video_id   INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, video_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    charge_id  TEXT NOT NULL UNIQUE,
    amount     INTEGER NOT NULL,
    currency   TEXT NOT NULL,
    views      INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sponsor_checks (
    user_id    INTEGER NOT NULL,
    sponsor_id INTEGER NOT NULL,
    checked_at TEXT NOT NULL,
    PRIMARY KEY (user_id, sponsor_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by INTEGER
);

CREATE TABLE IF NOT EXISTS referral_rewards (
    invitee_id  INTEGER PRIMARY KEY,
    referrer_id INTEGER NOT NULL,
    views       INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime | None = None) -> str:
    return (moment or utcnow()).isoformat(timespec="seconds")


def new_public_id() -> str:
    return secrets.token_hex(4)


@dataclass(frozen=True)
class User:
    user_id: int
    username: str | None
    first_name: str | None
    balance: int
    free_granted: bool
    bonus_granted: bool
    main_sub_ok: bool
    total_views: int
    submitted: int
    approved: int
    blocked: bool
    ref_code: str | None = None
    referred_by: int | None = None
    referrals: int = 0

    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"id{self.user_id}"


@dataclass(frozen=True)
class Video:
    id: int
    public_id: str
    author_id: int
    file_id: str
    duration: int
    status: str


@dataclass(frozen=True)
class Stats:
    users: int
    active_24h: int
    published: int
    pending: int
    views: int
    payments: int
    amount: int
    sponsor_subs: int


_USER_COLUMNS = (
    "user_id, username, first_name, balance, free_granted, bonus_granted, "
    "main_sub_ok, total_views, submitted, approved, blocked, "
    "ref_code, referred_by, referrals"
)


def _row_to_user(row: aiosqlite.Row) -> User:
    return User(
        user_id=row["user_id"],
        username=row["username"],
        first_name=row["first_name"],
        balance=row["balance"],
        free_granted=bool(row["free_granted"]),
        bonus_granted=bool(row["bonus_granted"]),
        main_sub_ok=bool(row["main_sub_ok"]),
        total_views=row["total_views"],
        submitted=row["submitted"],
        approved=row["approved"],
        blocked=bool(row["blocked"]),
        ref_code=row["ref_code"],
        referred_by=row["referred_by"],
        referrals=row["referrals"] or 0,
    )


class Database:
    """Тонкая обёртка над aiosqlite: один коннект на процесс бота."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """Досоздаёт колонки, если база старше текущей схемы."""
        async with self.conn.execute("PRAGMA table_info(users)") as cur:
            existing = {row["name"] for row in await cur.fetchall()}

        new_columns = {
            "ref_code": "TEXT",
            "referred_by": "INTEGER",
            "referrals": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, ddl in new_columns.items():
            if name not in existing:
                await self.conn.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() не был вызван")
        return self._conn

    # ------------------------------------------------------------------ users

    async def touch_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        free_views: int,
    ) -> tuple[User, bool]:
        """Регистрирует/обновляет пользователя. Возвращает (user, is_new)."""
        now = iso()
        async with self.conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            is_new = await cur.fetchone() is None

        if is_new:
            await self.conn.execute(
                "INSERT INTO users (user_id, username, first_name, created_at, "
                "last_seen_at, balance, free_granted) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (user_id, username, first_name, now, now, max(0, free_views)),
            )
        else:
            await self.conn.execute(
                "UPDATE users SET username = ?, first_name = ?, last_seen_at = ? "
                "WHERE user_id = ?",
                (username, first_name, now, user_id),
            )
        await self.conn.commit()
        user = await self.get_user(user_id)
        assert user is not None
        return user, is_new

    async def get_user(self, user_id: int) -> User | None:
        async with self.conn.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def set_main_sub(self, user_id: int, ok: bool) -> None:
        await self.conn.execute(
            "UPDATE users SET main_sub_ok = ? WHERE user_id = ?", (1 if ok else 0, user_id)
        )
        await self.conn.commit()

    async def grant_bonus_once(self, user_id: int, bonus_views: int) -> bool:
        """Начисляет бонус за спонсоров ровно один раз. True — если начислено сейчас."""
        cur = await self.conn.execute(
            "UPDATE users SET balance = balance + ?, bonus_granted = 1 "
            "WHERE user_id = ? AND bonus_granted = 0",
            (max(0, bonus_views), user_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def add_views(self, user_id: int, views: int) -> None:
        await self.conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?", (views, user_id)
        )
        await self.conn.commit()

    async def spend_view(self, user_id: int) -> bool:
        """Списывает один просмотр атомарно. False — если баланс пуст."""
        cur = await self.conn.execute(
            "UPDATE users SET balance = balance - 1, total_views = total_views + 1 "
            "WHERE user_id = ? AND balance > 0",
            (user_id,),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def ensure_ref_code(self, user_id: int) -> str:
        """Выдаёт пользователю личный реферальный код (если ещё нет)."""
        user = await self.get_user(user_id)
        if user and user.ref_code:
            return user.ref_code

        code = new_public_id()
        # Код должен быть уникальным: повторяем при совпадении.
        for _ in range(5):
            async with self.conn.execute(
                "SELECT 1 FROM users WHERE ref_code = ?", (code,)
            ) as cur:
                taken = await cur.fetchone() is not None
            if not taken:
                break
            code = new_public_id()

        await self.conn.execute(
            "UPDATE users SET ref_code = ? WHERE user_id = ?", (code, user_id)
        )
        await self.conn.commit()
        return code

    async def find_by_ref_code(self, code: str) -> User | None:
        async with self.conn.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE ref_code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def set_referrer(self, user_id: int, referrer_id: int) -> bool:
        """Привязывает «кто пригласил». Только один раз и не сам себя."""
        if user_id == referrer_id:
            return False

        user = await self.get_user(user_id)
        if user is None or user.referred_by is not None:
            return False

        await self.conn.execute(
            "UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL",
            (referrer_id, user_id),
        )
        await self.conn.commit()
        return True

    async def reward_referrer(self, invitee_id: int, views: int) -> tuple[int, int] | None:
        """Начисляет пригласившему просмотры за друга. Строго один раз на друга.

        Возвращает (id пригласившего, всего друзей у него) или None,
        если награда уже была выдана.
        """
        user = await self.get_user(invitee_id)
        if user is None or user.referred_by is None:
            return None

        try:
            # Уникальный индекс по invitee_id не даст наградить дважды.
            await self.conn.execute(
                "INSERT INTO referral_rewards (invitee_id, referrer_id, views, created_at) "
                "VALUES (?, ?, ?, ?)",
                (invitee_id, user.referred_by, views, iso()),
            )
        except aiosqlite.IntegrityError:
            await self.conn.rollback()
            return None

        await self.conn.execute(
            "UPDATE users SET referrals = referrals + 1, balance = balance + ? "
            "WHERE user_id = ?",
            (views, user.referred_by),
        )
        await self.conn.commit()

        referrer = await self.get_user(user.referred_by)
        return user.referred_by, (referrer.referrals if referrer else 0)

    async def set_blocked(self, user_id: int, blocked: bool) -> None:
        await self.conn.execute(
            "UPDATE users SET blocked = ? WHERE user_id = ?",
            (1 if blocked else 0, user_id),
        )
        await self.conn.commit()

    # ----------------------------------------------------------------- videos

    async def video_exists_by_unique_id(self, file_unique_id: str | None) -> bool:
        if not file_unique_id:
            return False
        async with self.conn.execute(
            "SELECT 1 FROM videos WHERE file_unique_id = ? LIMIT 1", (file_unique_id,)
        ) as cur:
            return await cur.fetchone() is not None

    async def create_video(
        self, author_id: int, file_id: str, file_unique_id: str | None, duration: int
    ) -> Video:
        public_id = new_public_id()
        cur = await self.conn.execute(
            "INSERT INTO videos (public_id, author_id, file_id, file_unique_id, "
            "duration, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (public_id, author_id, file_id, file_unique_id, duration, iso()),
        )
        await self.conn.execute(
            "UPDATE users SET submitted = submitted + 1 WHERE user_id = ?", (author_id,)
        )
        await self.conn.commit()
        video_id = int(cur.lastrowid or 0)
        return Video(
            id=video_id,
            public_id=public_id,
            author_id=author_id,
            file_id=file_id,
            duration=duration,
            status="pending",
        )

    async def get_video(self, video_id: int) -> Video | None:
        async with self.conn.execute(
            "SELECT id, public_id, author_id, file_id, duration, status "
            "FROM videos WHERE id = ?",
            (video_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return Video(
            id=row["id"],
            public_id=row["public_id"],
            author_id=row["author_id"],
            file_id=row["file_id"],
            duration=row["duration"],
            status=row["status"],
        )

    async def set_storage_message(self, video_id: int, message_id: int | None) -> None:
        await self.conn.execute(
            "UPDATE videos SET storage_message_id = ? WHERE id = ?", (message_id, video_id)
        )
        await self.conn.commit()

    async def publish_video(self, video_id: int, admin_id: int) -> bool:
        cur = await self.conn.execute(
            "UPDATE videos SET status = 'published', published_at = ?, moderated_by = ? "
            "WHERE id = ? AND status = 'pending'",
            (iso(), admin_id, video_id),
        )
        if cur.rowcount > 0:
            await self.conn.execute(
                "UPDATE users SET approved = approved + 1 "
                "WHERE user_id = (SELECT author_id FROM videos WHERE id = ?)",
                (video_id,),
            )
        await self.conn.commit()
        return cur.rowcount > 0

    async def reject_video(self, video_id: int, admin_id: int, reason: str | None) -> bool:
        cur = await self.conn.execute(
            "UPDATE videos SET status = 'rejected', moderated_by = ?, reject_reason = ? "
            "WHERE id = ? AND status = 'pending'",
            (admin_id, reason, video_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def count_published(self) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS c FROM videos WHERE status = 'published'"
        ) as cur:
            row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def count_pending(self) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS c FROM videos WHERE status = 'pending'"
        ) as cur:
            row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def next_video_for_user(self, user_id: int, include_own: bool) -> Video | None:
        """Следующий непросмотренный опубликованный кружок (без повторов)."""
        own_filter = "" if include_own else "AND v.author_id != ?"
        params: list[object] = [user_id]
        if not include_own:
            params.append(user_id)
        sql = (
            "SELECT v.id, v.public_id, v.author_id, v.file_id, v.duration, v.status "
            "FROM videos v "
            "LEFT JOIN seen s ON s.video_id = v.id AND s.user_id = ? "
            "WHERE v.status = 'published' AND s.video_id IS NULL "
            f"{own_filter} "
            "ORDER BY v.id ASC LIMIT 1"
        )
        async with self.conn.execute(sql, tuple(params)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return Video(
            id=row["id"],
            public_id=row["public_id"],
            author_id=row["author_id"],
            file_id=row["file_id"],
            duration=row["duration"],
            status=row["status"],
        )

    async def mark_seen(self, user_id: int, video_id: int) -> None:
        now = iso()
        await self.conn.execute(
            "INSERT INTO seen (user_id, video_id, first_seen_at, last_seen_at, times) "
            "VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(user_id, video_id) DO UPDATE SET "
            "last_seen_at = excluded.last_seen_at, times = seen.times + 1",
            (user_id, video_id, now, now),
        )
        await self.conn.commit()

    async def toggle_like(self, user_id: int, video_id: int) -> bool:
        """Ставит/снимает лайк. True — лайк теперь стоит."""
        async with self.conn.execute(
            "SELECT 1 FROM likes WHERE user_id = ? AND video_id = ?", (user_id, video_id)
        ) as cur:
            exists = await cur.fetchone() is not None
        if exists:
            await self.conn.execute(
                "DELETE FROM likes WHERE user_id = ? AND video_id = ?", (user_id, video_id)
            )
            await self.conn.commit()
            return False
        await self.conn.execute(
            "INSERT INTO likes (user_id, video_id, created_at) VALUES (?, ?, ?)",
            (user_id, video_id, iso()),
        )
        await self.conn.commit()
        return True

    # --------------------------------------------------------------- payments

    async def register_payment(
        self, user_id: int, charge_id: str, amount: int, currency: str, views: int
    ) -> bool:
        """Идемпотентно фиксирует платёж и начисляет просмотры."""
        try:
            await self.conn.execute(
                "INSERT INTO payments (user_id, charge_id, amount, currency, views, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, charge_id, amount, currency, views, iso()),
            )
        except aiosqlite.IntegrityError:
            await self.conn.rollback()
            return False
        await self.conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?", (views, user_id)
        )
        await self.conn.commit()
        return True

    async def mark_sponsor_checked(self, user_id: int, sponsor_id: int) -> None:
        await self.conn.execute(
            "INSERT INTO sponsor_checks (user_id, sponsor_id, checked_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, sponsor_id) DO UPDATE SET checked_at = excluded.checked_at",
            (user_id, sponsor_id, iso()),
        )
        await self.conn.commit()

    # --------------------------------------------------------------- settings

    async def get_setting(self, key: str) -> str | None:
        async with self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else None

    async def get_settings(self) -> dict[str, str]:
        async with self.conn.execute("SELECT key, value FROM settings") as cur:
            rows = await cur.fetchall()
        return {row["key"]: row["value"] for row in rows}

    async def set_setting(self, key: str, value: str, admin_id: int | None = None) -> None:
        await self.conn.execute(
            "INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (key, value, iso(), admin_id),
        )
        await self.conn.commit()

    async def delete_setting(self, key: str) -> None:
        await self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        await self.conn.commit()

    # ------------------------------------------------------------------ stats

    async def stats(self) -> Stats:
        day_ago = iso(utcnow() - timedelta(days=1))
        async with self.conn.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM users) AS users, "
            "(SELECT COUNT(*) FROM users WHERE last_seen_at >= ?) AS active, "
            "(SELECT COUNT(*) FROM videos WHERE status = 'published') AS published, "
            "(SELECT COUNT(*) FROM videos WHERE status = 'pending') AS pending, "
            "(SELECT COALESCE(SUM(total_views), 0) FROM users) AS views, "
            "(SELECT COUNT(*) FROM payments) AS payments, "
            "(SELECT COALESCE(SUM(amount), 0) FROM payments) AS amount, "
            "(SELECT COUNT(DISTINCT user_id) FROM sponsor_checks) AS sponsor_subs",
            (day_ago,),
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        return Stats(
            users=int(row["users"]),
            active_24h=int(row["active"]),
            published=int(row["published"]),
            pending=int(row["pending"]),
            views=int(row["views"]),
            payments=int(row["payments"]),
            amount=int(row["amount"]),
            sponsor_subs=int(row["sponsor_subs"]),
        )
