import aiosqlite
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS chapters (
    chapter_number INTEGER PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    text TEXT,
    telegraph_url TEXT,
    source TEXT NOT NULL DEFAULT 'unknown',
    source_message_id INTEGER,
    source_chat_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS volumes (
    volume_number INTEGER PRIMARY KEY,
    start_chapter INTEGER NOT NULL,
    end_chapter INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (start_chapter <= end_chapter)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chapters_url ON chapters(telegraph_url);
CREATE INDEX IF NOT EXISTS idx_chapters_source_chat ON chapters(source_chat_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.db = None

    async def connect(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(SCHEMA)
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()

    async def upsert_chapter(
        self, number, title="", text=None, url=None,
        source="unknown", message_id=None, chat_id=None
    ):
        sql = """
        INSERT INTO chapters
            (chapter_number,title,text,telegraph_url,source,source_message_id,source_chat_id)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(chapter_number) DO UPDATE SET
            title=CASE WHEN excluded.title != '' THEN excluded.title ELSE chapters.title END,
            text=CASE WHEN excluded.text IS NOT NULL AND excluded.text != ''
                      THEN excluded.text ELSE chapters.text END,
            telegraph_url=COALESCE(excluded.telegraph_url, chapters.telegraph_url),
            source=CASE WHEN excluded.source != 'unknown' THEN excluded.source ELSE chapters.source END,
            source_message_id=COALESCE(excluded.source_message_id, chapters.source_message_id),
            source_chat_id=COALESCE(excluded.source_chat_id, chapters.source_chat_id),
            updated_at=CURRENT_TIMESTAMP
        """
        await self.db.execute(sql, (number, title, text, url, source, message_id, chat_id))
        await self.db.commit()

    async def get_chapter(self, number):
        cur = await self.db.execute(
            "SELECT * FROM chapters WHERE chapter_number=?", (number,)
        )
        return await cur.fetchone()

    async def get_chapters_range(self, start, end):
        cur = await self.db.execute(
            "SELECT * FROM chapters WHERE chapter_number BETWEEN ? AND ? ORDER BY chapter_number",
            (start, end),
        )
        return await cur.fetchall()

    async def count_chapters(self):
        cur = await self.db.execute("SELECT COUNT(*) FROM chapters")
        return (await cur.fetchone())[0]

    async def count_with_text(self):
        cur = await self.db.execute(
            "SELECT COUNT(*) FROM chapters WHERE text IS NOT NULL AND length(trim(text)) > 0"
        )
        return (await cur.fetchone())[0]

    async def missing_range(self, start, end):
        cur = await self.db.execute(
            "SELECT chapter_number FROM chapters WHERE chapter_number BETWEEN ? AND ?",
            (start, end),
        )
        existing = {row[0] for row in await cur.fetchall()}
        return [n for n in range(start, end + 1) if n not in existing]

    async def chapters_without_text(self):
        cur = await self.db.execute(
            "SELECT * FROM chapters WHERE telegraph_url IS NOT NULL AND (text IS NULL OR trim(text)='') ORDER BY chapter_number"
        )
        return await cur.fetchall()

    async def upsert_volume(self, number, start, end):
        await self.db.execute(
            """
            INSERT INTO volumes(volume_number,start_chapter,end_chapter)
            VALUES(?,?,?)
            ON CONFLICT(volume_number) DO UPDATE SET
                start_chapter=excluded.start_chapter,
                end_chapter=excluded.end_chapter
            """,
            (number, start, end),
        )
        await self.db.commit()

    async def delete_volume(self, number):
        await self.db.execute("DELETE FROM volumes WHERE volume_number=?", (number,))
        await self.db.commit()

    async def get_volume(self, number):
        cur = await self.db.execute(
            "SELECT * FROM volumes WHERE volume_number=?", (number,)
        )
        return await cur.fetchone()

    async def list_volumes(self):
        cur = await self.db.execute(
            "SELECT * FROM volumes ORDER BY volume_number"
        )
        return await cur.fetchall()

    async def set_setting(self, key, value):
        await self.db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        await self.db.commit()

    async def get_setting(self, key, default=None):
        cur = await self.db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default
