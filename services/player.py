import asyncio
import enum
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from config.settings import settings
from services.audio_source import audio_source_service
from services.spotify_client import SpotifyTrack
from utils.logger import setup_logger

logger = setup_logger("GuildPlayer")


class LoopMode(enum.Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"


@dataclass
class QueueItem:
    """Represents a queued song with requester metadata."""
    track: SpotifyTrack
    requester: discord.Member
    enqueued_at: float = None

    def __post_init__(self):
        if self.enqueued_at is None:
            self.enqueued_at = time.time()


class GuildPlayer:
    """
    State machine managing audio playback, queue transitions, and
    lifecycle events for a single Discord Guild.
    """

    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None

        # Queue & Playback State
        self.queue: List[QueueItem] = []
        self.history: List[QueueItem] = []
        self.current: Optional[QueueItem] = None
        self.loop_mode: LoopMode = LoopMode.OFF
        self.volume: float = settings.DEFAULT_VOLUME / 100.0

        # Concurrency & Tasks
        self.lock = asyncio.Lock()
        self.next_event = asyncio.Event()
        self.player_task: Optional[asyncio.Task] = None
        self.idle_task: Optional[asyncio.Task] = None

        # UI hooks (stored to edit or delete previous now playing cards)
        self.now_playing_message: Optional[discord.Message] = None

    @property
    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    @property
    def is_paused(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_paused()

    @property
    def is_connected(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    async def connect(self, channel: discord.VoiceChannel, text_channel: Optional[discord.TextChannel] = None):
        """Connects or moves the bot to the specified voice channel."""
        self.text_channel = text_channel or self.text_channel

        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect(reconnect=True, timeout=20.0, self_deaf=False)

        # Start the player loop task if not active
        if not self.player_task or self.player_task.done():
            self.player_task = asyncio.create_task(self._player_loop())

    async def disconnect(self):
        """Stops playback, clears queue, and leaves the voice channel."""
        logger.info(f"[Guild {self.guild_id}] Disconnecting and cleaning up player state.")
        self._cancel_tasks()
        self.queue.clear()
        self.current = None

        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            if self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            self.voice_client = None

    def _cancel_tasks(self):
        """Cancels background worker tasks."""
        if self.player_task and not self.player_task.done():
            self.player_task.cancel()
        if self.idle_task and not self.idle_task.done():
            self.idle_task.cancel()

    async def add_track(self, track: SpotifyTrack, requester: discord.Member, text_channel: Optional[discord.TextChannel] = None) -> int:
        """Appends a track to the queue and returns its position in queue (1-based)."""
        async with self.lock:
            if text_channel:
                self.text_channel = text_channel

            item = QueueItem(track=track, requester=requester)
            self.queue.append(item)

            # Cancel idle disconnect countdown if active
            if self.idle_task and not self.idle_task.done():
                self.idle_task.cancel()
                self.idle_task = None

            # Wake up player loop if waiting for songs
            self.next_event.set()
            return len(self.queue)

    async def add_tracks(self, tracks: List[SpotifyTrack], requester: discord.Member, text_channel: Optional[discord.TextChannel] = None) -> int:
        """Appends multiple tracks to the queue (e.g. from an album or playlist)."""
        async with self.lock:
            if text_channel:
                self.text_channel = text_channel

            for track in tracks:
                self.queue.append(QueueItem(track=track, requester=requester))

            if self.idle_task and not self.idle_task.done():
                self.idle_task.cancel()
                self.idle_task = None

            self.next_event.set()
            return len(tracks)

    def skip(self):
        """Skips the currently playing song."""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    def pause(self) -> bool:
        """Pauses current audio. Returns True if paused, False otherwise."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self) -> bool:
        """Resumes paused audio. Returns True if resumed, False otherwise."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False

    def stop(self):
        """Clears queue and stops playback."""
        self.queue.clear()
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    def shuffle(self) -> int:
        """Shuffles the upcoming queue in-place. Returns count of tracks shuffled."""
        if len(self.queue) > 1:
            random.shuffle(self.queue)
        return len(self.queue)

    def remove(self, index: int) -> Optional[QueueItem]:
        """Removes a track by 1-based index."""
        if 1 <= index <= len(self.queue):
            return self.queue.pop(index - 1)
        return None

    def set_volume(self, volume_percent: int):
        """Sets the volume percentage (0-100)."""
        self.volume = max(0.0, min(1.0, volume_percent / 100.0))
        if self.voice_client and self.voice_client.source:
            if isinstance(self.voice_client.source, discord.PCMVolumeTransformer):
                self.voice_client.source.volume = self.volume

    def set_loop_mode(self, mode: str) -> LoopMode:
        """Updates loop mode: off, track, or queue."""
        clean_mode = mode.lower().strip()
        if clean_mode in ("track", "song"):
            self.loop_mode = LoopMode.TRACK
        elif clean_mode in ("queue", "all"):
            self.loop_mode = LoopMode.QUEUE
        else:
            self.loop_mode = LoopMode.OFF
        return self.loop_mode

    async def _start_idle_timer(self):
        """Leaves the voice channel after IDLE_TIMEOUT_SECONDS of inactivity."""
        try:
            await asyncio.sleep(settings.IDLE_TIMEOUT_SECONDS)
            if not self.is_playing and len(self.queue) == 0:
                logger.info(f"[Guild {self.guild_id}] Inactivity timeout reached. Leaving voice.")
                if self.text_channel:
                    await self.text_channel.send("👋 Left the voice channel due to inactivity.")
                await self.disconnect()
        except asyncio.CancelledError:
            pass

    async def _player_loop(self):
        """Core background loop dispatching audio playback."""
        await self.bot.wait_until_ready()
        consecutive_failures = 0

        while True:
            self.next_event.clear()

            # Handle Repeat Mode / Queue Consumption
            if self.loop_mode == LoopMode.TRACK and self.current:
                # Keep playing the same track
                next_item = self.current
            else:
                if self.loop_mode == LoopMode.QUEUE and self.current:
                    # Append previous track to the back of the queue
                    self.queue.append(self.current)

                if self.queue:
                    next_item = self.queue.pop(0)
                else:
                    next_item = None

            # If no track is ready to play, start idle timeout and wait
            if not next_item:
                self.current = None
                if not self.idle_task or self.idle_task.done():
                    self.idle_task = asyncio.create_task(self._start_idle_timer())

                # Sleep until woken up by add_track
                await self.next_event.wait()
                continue

            self.current = next_item
            if self.current:
                self.history.append(self.current)

            # JIT Audio Stream Resolution
            search_query = next_item.track.search_query
            logger.info(f"[Guild {self.guild_id}] Resolving stream JIT for: '{search_query}'")

            resolved = await audio_source_service.resolve_stream(search_query)
            if not resolved:
                consecutive_failures += 1
                if self.text_channel:
                    await self.text_channel.send(
                        f"⚠️ Could not resolve audio for **{next_item.track.artist} - {next_item.track.title}**. Skipping..."
                    )
                self.current = None
                # If too many consecutive resolutions fail, stop queue to prevent CPU burn on free hosts
                if consecutive_failures >= 3:
                    if self.text_channel:
                        await self.text_channel.send("🛑 Stopped queue: multiple tracks failed to resolve. Check your connection or search terms.")
                    self.queue.clear()
                    consecutive_failures = 0
                await asyncio.sleep(1.0)
                continue

            # Check voice connection before playing
            if not self.voice_client or not self.voice_client.is_connected():
                logger.warning(f"[Guild {self.guild_id}] Voice client disconnected during stream resolution.")
                break

            # Create audio source and play
            audio_source = audio_source_service.create_audio_source(resolved.stream_url, volume=self.volume)
            track_name = f"{next_item.track.artist} - {next_item.track.title}"
            logger.info(f"[Guild {self.guild_id}] Starting playback: '{track_name}' (Volume: {int(self.volume * 100)}%)")

            def after_playing(error):
                play_dur = time.time() - start_time
                if error:
                    logger.error(f"[Guild {self.guild_id}] Playback error for '{track_name}' after {play_dur:.1f}s: {error}")
                    # Invalidate cache entry so broken or expired URLs are immediately purged
                    try:
                        from services.database import database_service
                        asyncio.run_coroutine_threadsafe(
                            database_service.delete_cached_stream(search_query),
                            self.bot.loop
                        )
                    except Exception as clean_err:
                        logger.debug(f"Failed to invalidate cache after playback error: {clean_err}")
                else:
                    if play_dur < 3.0:
                        logger.warning(
                            f"[Guild {self.guild_id}] Audio for '{track_name}' ended after only {play_dur:.1f}s. "
                            "Stream URL may be empty or unplayable."
                        )
                    else:
                        logger.info(f"[Guild {self.guild_id}] Playback completed normally for '{track_name}' ({play_dur:.1f}s).")

                # Signal the event loop that audio has finished
                self.bot.loop.call_soon_threadsafe(self.next_event.set)

            start_time = time.time()
            self.voice_client.play(audio_source, after=after_playing)

            # Dispatch notification
            if self.text_channel:
                await self._send_now_playing(next_item)

            # Wait until current track completes, skips, or stops
            await self.next_event.wait()

            # Measure playback duration to protect against high-CPU rapid failure loops
            play_duration = time.time() - start_time
            if play_duration >= 4.0:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if self.loop_mode == LoopMode.TRACK:
                    # Break loop mode if track crashed immediately to prevent CPU loop
                    self.current = None

                if consecutive_failures >= 3:
                    if self.text_channel:
                        await self.text_channel.send("🛑 Playback halted: repeated immediate audio errors. Pausing to protect server CPU.")
                    self.queue.clear()
                    consecutive_failures = 0
                await asyncio.sleep(1.0)

    async def _send_now_playing(self, item: QueueItem):
        """Sends a Now Playing notification embed to the text channel."""
        try:
            embed = discord.Embed(
                title="🎶 Now Playing",
                description=f"[{item.track.artist} - {item.track.title}]({item.track.url})",
                color=discord.Color.from_rgb(30, 215, 96)  # Spotify Green
            )
            embed.add_field(name="Album", value=item.track.album, inline=True)
            embed.add_field(name="Duration", value=item.track.formatted_duration, inline=True)
            embed.add_field(name="Requested By", value=item.requester.mention, inline=True)

            if item.track.cover_url:
                embed.set_thumbnail(url=item.track.cover_url)

            embed.set_footer(text=f"Queue: {len(self.queue)} songs | Loop: {self.loop_mode.value.capitalize()}")

            # Delete prior now playing card to prevent text channel clutter
            if self.now_playing_message:
                try:
                    await self.now_playing_message.delete()
                except discord.HTTPException:
                    pass

            from utils.views import MusicControlView
            control_view = MusicControlView(player=self)

            self.now_playing_message = await self.text_channel.send(embed=embed, view=control_view)
        except Exception as e:
            logger.error(f"Failed to send Now Playing embed: {e}")


class PlayerManager:
    """Singleton registry managing GuildPlayer instances across all servers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._players: Dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> GuildPlayer:
        """Retrieves or creates a GuildPlayer for the given guild."""
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer(self.bot, guild_id)
        return self._players[guild_id]

    async def remove_player(self, guild_id: int):
        """Disconnects and removes the player for the given guild."""
        if guild_id in self._players:
            player = self._players.pop(guild_id)
            await player.disconnect()


_player_manager: Optional[PlayerManager] = None


def get_player_manager(bot: commands.Bot) -> PlayerManager:
    global _player_manager
    if _player_manager is None:
        _player_manager = PlayerManager(bot)
    return _player_manager
