import hashlib
import os
import time
from typing import Optional

import aiosqlite

from services.audio_source import ResolvedAudio
from utils.logger import setup_logger

logger = setup_logger("DatabaseService")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bot.db")


class DatabaseService:
    """
    Asynchronous SQLite persistence layer for high-speed stream URL caching
    and per-guild configurations.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self):
        """Initializes database tables and indexes."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            # Stream URL Cache Table (TTL-based)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS stream_cache (
                    query_hash TEXT PRIMARY KEY,
                    search_query TEXT,
                    stream_url TEXT NOT NULL,
                    webpage_url TEXT,
                    title TEXT,
                    duration_seconds INTEGER,
                    expires_at REAL NOT NULL
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_stream_cache_exp ON stream_cache (expires_at)")

            # Purge expired entries and stale signed URLs from previous sessions
            await db.execute(
                "DELETE FROM stream_cache WHERE expires_at <= ? OR stream_url LIKE '%soundcloud%'",
                (time.time(),)
            )

            # Guild Settings Table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    default_volume INTEGER DEFAULT 50,
                    dj_role_id INTEGER,
                    updated_at REAL
                )
            """)
            await db.commit()

        self._initialized = True
        logger.info(f"Database initialized successfully at {self.db_path}")

    @staticmethod
    def _hash_query(query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

    async def get_cached_stream(self, query: str) -> Optional[ResolvedAudio]:
        """Retrieves unexpired cached audio stream data."""
        if not self._initialized:
            await self.initialize()

        query_hash = self._hash_query(query)
        now = time.time()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT stream_url, webpage_url, title, duration_seconds FROM stream_cache WHERE query_hash = ? AND expires_at > ?",
                    (query_hash, now)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        logger.debug(f"Cache HIT for query: '{query}'")
                        return ResolvedAudio(
                            stream_url=row[0],
                            webpage_url=row[1] or "",
                            title=row[2] or "Unknown Title",
                            duration_seconds=row[3] or 0
                        )
        except Exception as e:
            logger.error(f"Error querying stream cache: {e}")

        return None

    async def delete_cached_stream(self, query: str):
        """Deletes a cached stream entry if playback failed or URL expired."""
        if not self._initialized:
            await self.initialize()

        query_hash = self._hash_query(query)
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM stream_cache WHERE query_hash = ?", (query_hash,))
                await db.commit()
                logger.debug(f"Removed stream cache entry for query: '{query}'")
        except Exception as e:
            logger.error(f"Error deleting cached stream: {e}")

    async def cache_stream(self, query: str, audio: ResolvedAudio, ttl_seconds: int = 14400):
        """
        Stores resolved stream URL in cache.
        YouTube TTL: 4 hours (14400s).
        SoundCloud signed URLs expire rapidly: 10 minutes (600s).
        """
        if not self._initialized:
            await self.initialize()

        # SoundCloud CloudFront signed URLs expire in 15-20 min; use short TTL
        if "soundcloud" in audio.stream_url.lower():
            ttl_seconds = 600

        query_hash = self._hash_query(query)
        expires_at = time.time() + ttl_seconds

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO stream_cache (
                        query_hash, search_query, stream_url, webpage_url, title, duration_seconds, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (query_hash, query, audio.stream_url, audio.webpage_url, audio.title, audio.duration_seconds, expires_at))
                await db.commit()
                logger.debug(f"Cached stream for query: '{query}' (TTL: {ttl_seconds}s)")
        except Exception as e:
            logger.error(f"Error saving stream to cache: {e}")

    async def get_guild_volume(self, guild_id: int) -> int:
        """Gets configured default volume for a guild."""
        if not self._initialized:
            await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT default_volume FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0]
        except Exception as e:
            logger.error(f"Error reading guild settings: {e}")
        return 50

    async def set_guild_volume(self, guild_id: int, volume: int):
        """Saves configured volume for a guild."""
        if not self._initialized:
            await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO guild_settings (guild_id, default_volume, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET default_volume = excluded.default_volume, updated_at = excluded.updated_at
                """, (guild_id, volume, time.time()))
                await db.commit()
        except Exception as e:
            logger.error(f"Error updating guild volume: {e}")


database_service = DatabaseService()

