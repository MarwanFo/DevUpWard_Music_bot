import asyncio
import os
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

import discord
import yt_dlp

from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger("AudioSource")

# yt-dlp configuration optimized for minimal latency, high-quality audio streaming,
# and bypassing YouTube bot-detection on cloud/VPS IP addresses.
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
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",   # Bind to IPv4 to mitigate IPv6 throttling
    "extractor_args": {
        "youtube": {
            # Use lean mobile clients to minimize CPU & RAM on shared hosts and bypass bot checks
            "player_client": ["android", "ios"],
        }
    },
}

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# FFmpeg encoding arguments: '-threads 1' prevents CPU spikes on shared hosting
FFMPEG_OPTIONS = "-vn -b:a 128k -threads 1 -nostdin"


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
        opts = YTDL_OPTIONS.copy()
        if os.path.exists("cookies.txt"):
            opts["cookiefile"] = "cookies.txt"
            logger.info("Found and loaded cookies.txt for yt-dlp authentication.")

        self._ytdl = yt_dlp.YoutubeDL(opts)

    @staticmethod
    def _clean_soundcloud_query(query: str) -> str:
        """Strips tags like (feat. ...), official audio, etc. to optimize SoundCloud search."""
        clean = re.sub(r"(?i)[\(\[][^\)\]]*(?:feat|ft)[^\)\]]*[\)\]]", "", query)
        clean = re.sub(r"(?i)\b(official\s+(audio|video|visualizer)|lyrics|video\s+clip|hd|4k)\b", "", clean)
        clean = re.sub(r"[\(\)\[\]\-]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean or query

    @staticmethod
    def _extract_stream_data(raw_info: Dict[str, Any]) -> Optional[Tuple[str, str, str, int]]:
        """Extracts direct stream URL, webpage URL, title, and duration from raw info."""
        if not raw_info:
            return None

        entry = raw_info
        if "entries" in raw_info:
            entries = raw_info.get("entries")
            if not entries:
                return None
            entry = entries[0]

        stream_url = entry.get("url")
        if not stream_url and "formats" in entry:
            # Fallback to last available audio format
            audio_formats = [f for f in entry.get("formats", []) if f.get("acodec") != "none"]
            if audio_formats:
                stream_url = audio_formats[-1].get("url")
            elif entry.get("formats"):
                stream_url = entry["formats"][-1].get("url")

        if not stream_url:
            return None

        webpage_url = entry.get("webpage_url") or entry.get("url") or ""
        title = entry.get("title", "Unknown Title")
        duration = int(entry.get("duration", 0))

        return stream_url, webpage_url, title, duration

    async def resolve_stream(self, search_query_or_url: str) -> Optional[ResolvedAudio]:
        """
        Extracts direct streaming audio URL for a given query or URL.
        1. Checks SQLite cache.
        2. Tries YouTube (ytsearch1:) with mobile/android player client.
        3. Falls back to SoundCloud (scsearch1:) with cleaned keywords if YouTube fails.
        """
        # 1. Check SQLite Cache
        try:
            from services.database import database_service
            cached = await database_service.get_cached_stream(search_query_or_url)
            if cached:
                return cached
        except Exception as e:
            logger.debug(f"Cache lookup bypassed: {e}")

        loop = asyncio.get_running_loop()

        # Format target query
        query = search_query_or_url.strip()
        is_direct_url = query.startswith("http://") or query.startswith("https://")
        primary_target = query if is_direct_url else f"ytsearch1:{query}"

        # 2. Extract from primary source (YouTube)
        raw_info = None
        try:
            raw_info = await loop.run_in_executor(
                None,
                lambda: self._ytdl.extract_info(primary_target, download=False)
            )
        except Exception as yt_err:
            logger.warning(f"YouTube resolution failed for '{query}': {yt_err}")

        # Check if YouTube gave a valid playable stream
        extracted = self._extract_stream_data(raw_info) if raw_info else None

        # 3. Fallback to SoundCloud if YouTube returned nothing, threw error, or has no stream URL
        if not extracted and not is_direct_url:
            sc_query = self._clean_soundcloud_query(query)
            fallback_target = f"scsearch1:{sc_query}"
            logger.info(f"Attempting SoundCloud fallback for '{sc_query}'...")
            try:
                sc_raw_info = await loop.run_in_executor(
                    None,
                    lambda: self._ytdl.extract_info(fallback_target, download=False)
                )
                extracted = self._extract_stream_data(sc_raw_info)
            except Exception as sc_err:
                logger.error(f"SoundCloud fallback also failed for '{sc_query}': {sc_err}")

        if not extracted:
            logger.error(f"Could not resolve any audio stream for: '{search_query_or_url}'")
            return None

        stream_url, webpage_url, title, duration = extracted
        resolved = ResolvedAudio(
            stream_url=stream_url,
            webpage_url=webpage_url,
            title=title,
            duration_seconds=duration
        )

        # 4. Save to cache
        try:
            from services.database import database_service
            await database_service.cache_stream(search_query_or_url, resolved)
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

        return resolved

    def create_audio_source(self, stream_url: str, volume: float = 0.5) -> discord.PCMVolumeTransformer:
        """Constructs a discord.PCMVolumeTransformer wrapping FFmpegPCMAudio with headers to avoid CDN 403 Forbidden."""
        referer = "https://soundcloud.com/" if "soundcloud" in stream_url.lower() else "https://www.google.com/"

        before_options = (
            "-reconnect 1 "
            "-reconnect_streamed 1 "
            "-reconnect_delay_max 5 "
            "-nostdin "
            f'-user_agent "{BROWSER_USER_AGENT}" '
            f'-headers "Referer: {referer}\r\n"'
        )

        ffmpeg_source = discord.FFmpegPCMAudio(
            stream_url,
            executable=settings.FFMPEG_PATH,
            before_options=before_options,
            options=FFMPEG_OPTIONS
        )
        return discord.PCMVolumeTransformer(ffmpeg_source, volume=volume)


# Global audio source service instance
audio_source_service = AudioSourceService()
