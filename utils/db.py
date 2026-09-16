"""
Lightweight async SQLite wrapper for persisting:
  - per-guild settings (channel/category ids, auto-leave timer, auto rank/region defaults)
  - active LFG groups (owner, region, rank, size, message/thread/voice ids)
  - group members

Uses aiosqlite so it doesn't block the event loop.
"""
import aiosqlite
import time
from typing import Optional, List
from dataclasses import dataclass

from config import DB_PATH, DEFAULT_AUTO_LEAVE_MINUTES, DEFAULT_MAX_SIZE


@dataclass
class GuildSettings:
    guild_id: int
    category_id: Optional[int] = None
    lfg_channel_id: Optional[int] = None
    auto_leave_minutes: int = DEFAULT_AUTO_LEAVE_MINUTES
    auto_rank: Optional[str] = None      # if set, new groups default to this rank
    auto_region: Optional[str] = None    # if set, new groups default to this region


@dataclass
class Group:
    id: int
    guild_id: int
    owner_id: int
    region: str
    rank: str
    max_size: int
    note: str
    message_id: Optional[int]
    thread_id: Optional[int]
    voice_channel_id: Optional[int]
    created_at: float
    last_active_at: float
    status: str  # 'open', 'full', 'closed'


SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    category_id INTEGER,
    lfg_channel_id INTEGER,
    auto_leave_minutes INTEGER NOT NULL DEFAULT 30,
    auto_rank TEXT,
    auto_region TEXT
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    rank TEXT NOT NULL,
    max_size INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    message_id INTEGER,
    thread_id INTEGER,
    voice_channel_id INTEGER,
    created_at REAL NOT NULL,
    last_active_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at REAL NOT NULL,
    PRIMARY KEY (group_id, user_id)
);
"""


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    # ---------------- guild settings ----------------

    async def get_settings(self, guild_id: int) -> GuildSettings:
        cur = await self._conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
        if row is None:
            settings = GuildSettings(guild_id=guild_id)
            await self._conn.execute(
                "INSERT INTO guild_settings (guild_id, auto_leave_minutes) VALUES (?, ?)",
                (guild_id, DEFAULT_AUTO_LEAVE_MINUTES),
            )
            await self._conn.commit()
            return settings
        return GuildSettings(
            guild_id=row["guild_id"],
            category_id=row["category_id"],
            lfg_channel_id=row["lfg_channel_id"],
            auto_leave_minutes=row["auto_leave_minutes"],
            auto_rank=row["auto_rank"],
            auto_region=row["auto_region"],
        )

    async def save_settings(self, s: GuildSettings):
        await self._conn.execute(
            """INSERT INTO guild_settings
                (guild_id, category_id, lfg_channel_id, auto_leave_minutes, auto_rank, auto_region)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
                category_id=excluded.category_id,
                lfg_channel_id=excluded.lfg_channel_id,
                auto_leave_minutes=excluded.auto_leave_minutes,
                auto_rank=excluded.auto_rank,
                auto_region=excluded.auto_region
            """,
            (s.guild_id, s.category_id, s.lfg_channel_id, s.auto_leave_minutes,
             s.auto_rank, s.auto_region),
        )
        await self._conn.commit()

    # ---------------- groups ----------------

    async def create_group(self, guild_id: int, owner_id: int, region: str,
                            rank: str, max_size: int, note: str = "") -> Group:
        now = time.time()
        cur = await self._conn.execute(
            """INSERT INTO groups
                (guild_id, owner_id, region, rank, max_size, note,
                 created_at, last_active_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
            (guild_id, owner_id, region, rank, max_size, note, now, now),
        )
        await self._conn.commit()
        group_id = cur.lastrowid
        await self._conn.execute(
            "INSERT INTO group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
            (group_id, owner_id, now),
        )
        await self._conn.commit()
        return await self.get_group(group_id)

    async def get_group(self, group_id: int) -> Optional[Group]:
        cur = await self._conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
        row = await cur.fetchone()
        return self._row_to_group(row) if row else None

    async def get_group_by_owner(self, guild_id: int, owner_id: int) -> Optional[Group]:
        cur = await self._conn.execute(
            """SELECT * FROM groups WHERE guild_id = ? AND owner_id = ?
               AND status != 'closed' LIMIT 1""",
            (guild_id, owner_id),
        )
        row = await cur.fetchone()
        return self._row_to_group(row) if row else None

    async def get_group_by_member(self, guild_id: int, user_id: int) -> Optional[Group]:
        cur = await self._conn.execute(
            """SELECT g.* FROM groups g
               JOIN group_members m ON m.group_id = g.id
               WHERE g.guild_id = ? AND m.user_id = ? AND g.status != 'closed'
               LIMIT 1""",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return self._row_to_group(row) if row else None

    async def get_group_by_thread(self, thread_id: int) -> Optional[Group]:
        cur = await self._conn.execute(
            "SELECT * FROM groups WHERE thread_id = ?", (thread_id,)
        )
        row = await cur.fetchone()
        return self._row_to_group(row) if row else None

    async def get_group_by_message(self, message_id: int) -> Optional[Group]:
        cur = await self._conn.execute(
            "SELECT * FROM groups WHERE message_id = ?", (message_id,)
        )
        row = await cur.fetchone()
        return self._row_to_group(row) if row else None

    async def list_open_groups(self, guild_id: int) -> List[Group]:
        cur = await self._conn.execute(
            "SELECT * FROM groups WHERE guild_id = ? AND status IN ('open','full') "
            "ORDER BY created_at ASC",
            (guild_id,),
        )
        rows = await cur.fetchall()
        return [self._row_to_group(r) for r in rows]

    async def list_stale_groups(self, cutoff_ts: float) -> List[Group]:
        cur = await self._conn.execute(
            "SELECT * FROM groups WHERE status != 'closed' AND last_active_at < ?",
            (cutoff_ts,),
        )
        rows = await cur.fetchall()
        return [self._row_to_group(r) for r in rows]

    async def update_group_fields(self, group_id: int, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [group_id]
        await self._conn.execute(f"UPDATE groups SET {cols} WHERE id = ?", vals)
        await self._conn.commit()

    async def touch_group(self, group_id: int):
        await self.update_group_fields(group_id, last_active_at=time.time())

    async def close_group(self, group_id: int):
        await self.update_group_fields(group_id, status="closed")

    async def add_member(self, group_id: int, user_id: int):
        await self._conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
            (group_id, user_id, time.time()),
        )
        await self._conn.commit()

    async def remove_member(self, group_id: int, user_id: int):
        await self._conn.execute(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        await self._conn.commit()

    async def get_members(self, group_id: int) -> List[int]:
        cur = await self._conn.execute(
            "SELECT user_id FROM group_members WHERE group_id = ? ORDER BY joined_at ASC",
            (group_id,),
        )
        rows = await cur.fetchall()
        return [r["user_id"] for r in rows]

    async def count_members(self, group_id: int) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) as c FROM group_members WHERE group_id = ?", (group_id,)
        )
        row = await cur.fetchone()
        return row["c"]

    @staticmethod
    def _row_to_group(row) -> Group:
        return Group(
            id=row["id"],
            guild_id=row["guild_id"],
            owner_id=row["owner_id"],
            region=row["region"],
            rank=row["rank"],
            max_size=row["max_size"],
            note=row["note"],
            message_id=row["message_id"],
            thread_id=row["thread_id"],
            voice_channel_id=row["voice_channel_id"],
            created_at=row["created_at"],
            last_active_at=row["last_active_at"],
            status=row["status"],
        )
