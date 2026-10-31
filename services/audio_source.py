import asyncio
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any

import discord
import yt_dlp

from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger("AudioSource")

# yt-dlp configuration optimized for minimal latency and high-quality audio streaming
YTDL_OPTIONS: Dict[str, Any] = {
    "format": "bestaudio/best",
    "extract_flat": False,
    "skip_download": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytmsearch",  # Search YouTube Music first for cleaner audio
    "source_address": "0.0.0.0",   # Bind to IPv4 to mitigate IPv6 throttling
}

# FFmpeg network reconnect and buffering arguments
FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 "
    "-reconnect_streamed 1 "
    "-reconnect_delay_max 5 "
    "-nostdin"
)

FFMPEG_OPTIONS = "-vn -b:a 128k"


@dataclass
class ResolvedAudio:
    """Represents a resolved audio stream ready for FFmpeg playback."""
    stream_url: str
    webpage_url: str
    title: str
    duration_seconds: int


class AudioSourceService:
    """
    Manages audio stream extraction via yt-dlp and instantiation of
    discord-compatible audio players with volume transforms.
    """

    def __init__(self):
        # Check if optional cookies.txt exists in the workspace
        opts = YTDL_OPTIONS.copy()
        if os.path.exists("cookies.txt"):
            opts["cookiefile"] = "cookies.txt"
            logger.info("Found and loaded cookies.txt for yt-dlp authentication.")

        self._ytdl = yt_dlp.YoutubeDL(opts)

    async def resolve_stream(self, search_query_or_url: str) -> Optional[ResolvedAudio]:
        """
        Extracts the direct streaming audio URL for a given query or video URL.
        First checks SQLite cache for instant lookup (<5ms); on cache miss, executes yt-dlp.
        Dispatched via asyncio.to_thread to keep the event loop non-blocking.
        """
        # 1. Check Cache
        try:
            from services.database import database_service
            cached = await database_service.get_cached_stream(search_query_or_url)
            if cached:
                return cached
        except Exception as e:
            logger.debug(f"Cache lookup bypassed: {e}")

        # 2. Extract via yt-dlp
        try:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(
                None,
                lambda: self._ytdl.extract_info(search_query_or_url, download=False)
            )

            if not info:
                logger.warning(f"No audio stream found for query: '{search_query_or_url}'")
                return None

            # If search returned multiple entries, pick the first match
            if "entries" in info:
                entries = info.get("entries")
                if not entries:
                    logger.warning(f"Search entries empty for: '{search_query_or_url}'")
                    return None
                info = entries[0]

            stream_url = info.get("url")
            if not stream_url:
                logger.error(f"Failed to extract direct stream URL for '{search_query_or_url}'")
                return None

            resolved = ResolvedAudio(
                stream_url=stream_url,
                webpage_url=info.get("webpage_url", search_query_or_url),
                title=info.get("title", "Unknown Title"),
                duration_seconds=int(info.get("duration", 0))
            )

            # 3. Store in cache
            try:
                from services.database import database_service
                await database_service.cache_stream(search_query_or_url, resolved)
            except Exception as e:
                logger.debug(f"Cache write error: {e}")

            return resolved
        except Exception as e:
            logger.error(f"yt-dlp stream resolution error for '{search_query_or_url}': {e}")
            return None

    def create_audio_source(self, stream_url: str, volume: float = 0.5) -> discord.PCMVolumeTransformer:
        """
        Constructs a discord.PCMVolumeTransformer wrapping FFmpegPCMAudio.
        """
        ffmpeg_source = discord.FFmpegPCMAudio(
            stream_url,
            executable=settings.FFMPEG_PATH,
            before_options=FFMPEG_BEFORE_OPTIONS,
            options=FFMPEG_OPTIONS
        )
        return discord.PCMVolumeTransformer(ffmpeg_source, volume=volume)


# Global audio source service instance
audio_source_service = AudioSourceService()
