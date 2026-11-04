import math
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

from services.player import GuildPlayer, get_player_manager
from services.spotify_client import SpotifyTrack, spotify_client
from utils.logger import setup_logger

logger = setup_logger("MusicCog")


def is_user_in_voice():
    """Interaction check verifying the user is connected to a voice channel."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ You must be connected to a voice channel to use this command.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)


def is_same_voice_channel():
    """Interaction check verifying the user is in the same voice channel as the bot."""
    async def predicate(interaction: discord.Interaction) -> bool:
        bot_voice = interaction.guild.voice_client
        if bot_voice and bot_voice.channel:
            if not interaction.user.voice or interaction.user.voice.channel.id != bot_voice.channel.id:
                await interaction.response.send_message(
                    f"❌ You must be in the same voice channel as the bot ({bot_voice.channel.mention}) to use this command.",
                    ephemeral=True
                )
                return False
        return True
    return app_commands.check(predicate)


class MusicCog(commands.Cog, name="Music"):
    """
    Core music playback, queue management, and voice controls.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.player_manager = get_player_manager(bot)

    def _get_player(self, guild_id: int) -> GuildPlayer:
        return self.player_manager.get_player(guild_id)

    @app_commands.command(name="play", description="Play a song or playlist from Spotify URL or search query.")
    @app_commands.describe(query="Spotify URL (Track, Album, Playlist) or song search keywords")
    @is_user_in_voice()
    async def play(self, interaction: discord.Interaction, query: str):
        # 1. Defer immediately to prevent Discord's 3-second interaction timeout
        await interaction.response.defer()

        guild = interaction.guild
        voice_channel = interaction.user.voice.channel
        player = self._get_player(guild.id)

        # Check permissions in the voice channel
        bot_member = guild.me
        perms = voice_channel.permissions_for(bot_member)
        if not perms.connect:
            await interaction.followup.send(f"❌ I do not have permission to **Connect** to {voice_channel.mention}!")
            return
        if not perms.speak:
            await interaction.followup.send(
                f"⚠️ I do not have permission to **Speak** in {voice_channel.mention}!\n"
                "Please make sure my role or channel permissions have **Speak** enabled so you can hear audio."
            )
            return
        if bot_member.voice and bot_member.voice.mute:
            await interaction.followup.send(
                "⚠️ I am currently **Server Muted** in this server! An admin needs to right-click me and uncheck **Server Mute**."
            )
            return

        # 2. Connect to voice channel if not already connected
        try:
            await player.connect(voice_channel, text_channel=interaction.channel)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to connect to voice channel: {e}")
            return

        parsed = spotify_client.parse_url(query)

        # Case A: Spotify Playlist
        if parsed and parsed[0] == "playlist":
            playlist = await spotify_client.get_playlist(parsed[1])
            if not playlist or not playlist.tracks:
                await interaction.followup.send("❌ Could not load or find tracks in this Spotify playlist.")
                return

            queued_count = await player.add_tracks(playlist.tracks, requester=interaction.user, text_channel=interaction.channel)
            embed = discord.Embed(
                title="📂 Queued Playlist",
                description=f"Added **{queued_count}** tracks from [{playlist.title}]({playlist.url})",
                color=discord.Color.from_rgb(30, 215, 96)
            )
            if playlist.cover_url:
                embed.set_thumbnail(url=playlist.cover_url)
            embed.set_footer(text=f"Curator: {playlist.owner_or_artist} • Requested by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)
            return

        # Case B: Spotify Album
        if parsed and parsed[0] == "album":
            album = await spotify_client.get_album(parsed[1])
            if not album or not album.tracks:
                await interaction.followup.send("❌ Could not load tracks from this Spotify album.")
                return

            queued_count = await player.add_tracks(album.tracks, requester=interaction.user, text_channel=interaction.channel)
            embed = discord.Embed(
                title="💿 Queued Album",
                description=f"Added **{queued_count}** tracks from [{album.title}]({album.url})",
                color=discord.Color.from_rgb(30, 215, 96)
            )
            if album.cover_url:
                embed.set_thumbnail(url=album.cover_url)
            embed.set_footer(text=f"Artist: {album.owner_or_artist} • Requested by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)
            return

        # Case C: Spotify Single Track
        if parsed and parsed[0] == "track":
            track = await spotify_client.get_track(parsed[1])
            if not track:
                await interaction.followup.send("❌ Could not resolve this Spotify track.")
                return

            pos = await player.add_track(track, requester=interaction.user, text_channel=interaction.channel)
            embed = discord.Embed(
                title="🎵 Queued Track",
                description=f"[{track.artist} - {track.title}]({track.url})",
                color=discord.Color.from_rgb(30, 215, 96)
            )
            embed.add_field(name="Duration", value=track.formatted_duration, inline=True)
            embed.add_field(name="Position in Queue", value=f"#{pos}" if player.is_playing else "Playing next", inline=True)
            if track.cover_url:
                embed.set_thumbnail(url=track.cover_url)
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)
            return

        # Case D: Text Search Query
        # First attempt search on Spotify if authenticated, otherwise create fallback track
        search_results = []
        if spotify_client.is_authenticated:
            search_results = await spotify_client.search(query, limit=1)

        if search_results:
            track = search_results[0]
        else:
            # Fallback direct query format
            track = SpotifyTrack(
                spotify_id="query",
                title=query,
                artist="",
                artists=[],
                album="Direct Search",
                duration_ms=0,
                url="https://spotify.com"
            )

        pos = await player.add_track(track, requester=interaction.user, text_channel=interaction.channel)
        embed = discord.Embed(
            title="🔍 Track Enqueued",
            description=f"**{track.artist + ' - ' if track.artist else ''}{track.title}**",
            color=discord.Color.from_rgb(30, 215, 96)
        )
        embed.add_field(name="Position in Queue", value=f"#{pos}" if player.is_playing else "Playing next", inline=True)
        if track.cover_url:
            embed.set_thumbnail(url=track.cover_url)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="pause", description="Pause current music playback.")
    @is_same_voice_channel()
    async def pause(self, interaction: discord.Interaction):
        player = self._get_player(interaction.guild.id)
        if not player.is_playing:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        if player.pause():
            await interaction.response.send_message("⏸️ Playback paused.")
        else:
            await interaction.response.send_message("⚠️ Could not pause playback.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume paused music playback.")
    @is_same_voice_channel()
    async def resume(self, interaction: discord.Interaction):
        player = self._get_player(interaction.guild.id)
        if not player.is_paused:
            await interaction.response.send_message("❌ Playback is not paused.", ephemeral=True)
            return

        if player.resume():
            await interaction.response.send_message("▶️ Playback resumed.")
        else:
            await interaction.response.send_message("⚠️ Could not resume playback.", ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current track.")
    @is_same_voice_channel()
    async def skip(self, interaction: discord.Interaction):
        player = self._get_player(interaction.guild.id)
        if not player.is_playing and not player.is_paused:
            await interaction.response.send_message("❌ No track currently playing to skip.", ephemeral=True)
            return

        current_title = player.current.track.title if player.current else "track"
        player.skip()
        await interaction.response.send_message(f"⏭️ Skipped **{current_title}**.")

    @app_commands.command(name="stop", description="Stop music, clear queue, and leave voice.")
    @is_same_voice_channel()
    async def stop(self, interaction: discord.Interaction):
        player = self._get_player(interaction.guild.id)
        await player.disconnect()
        await interaction.response.send_message("⏹️ Playback stopped, queue cleared, and disconnected.")

    @app_commands.command(name="queue", description="Display upcoming songs in the server queue.")
    @app_commands.describe(page="Page number of the queue (default 1)")
    async def queue(self, interaction: discord.Interaction, page: Optional[int] = 1):
        player = self._get_player(interaction.guild.id)

        if not player.current and not player.queue:
            await interaction.response.send_message("📭 The queue is currently empty.", ephemeral=True)
            return

        from utils.views import QueuePaginationView
        view = QueuePaginationView(player=player, current_page=page or 1, items_per_page=10)
        embed = view.build_embed(interaction.guild.name)

        if view.total_pages > 1:
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show detailed information about the currently playing song.")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self._get_player(interaction.guild.id)
        if not player.current:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        item = player.current
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"[{item.track.artist} - {item.track.title}]({item.track.url})",
            color=discord.Color.from_rgb(30, 215, 96)
        )
        embed.add_field(name="Album", value=item.track.album or "Unknown", inline=True)
        embed.add_field(name="Duration", value=item.track.formatted_duration, inline=True)
        embed.add_field(name="Requested By", value=item.requester.mention, inline=True)
        embed.add_field(name="Loop Mode", value=f"`{player.loop_mode.value.capitalize()}`", inline=True)
        embed.add_field(name="Volume", value=f"`{int(player.volume * 100)}%`", inline=True)

        if item.track.cover_url:
            embed.set_thumbnail(url=item.track.cover_url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Adjust playback volume (0 to 100).")
    @app_commands.describe(level="Volume level from 0 to 100")
    @is_same_voice_channel()
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
        player = self._get_player(interaction.guild.id)
        player.set_volume(level)
        await interaction.response.send_message(f"🔊 Volume set to **{level}%**.")

    @app_commands.command(name="loop", description="Change repeat mode.")
    @app_commands.describe(mode="Choose loop mode")
    @is_same_voice_channel()
    async def loop(self, interaction: discord.Interaction, mode: Literal["off", "track", "queue"]):
        player = self._get_player(interaction.guild.id)
        new_mode = player.set_loop_mode(mode)
        await interaction.response.send_message(f"🔁 Loop mode set to: **{new_mode.value.capitalize()}**.")

    @app_commands.command(name="shuffle", description="Randomize the order of tracks in the queue.")
    @is_same_voice_channel()
    async def shuffle(self, interaction: discord.Interaction):
        player = self._get_player(interaction.guild.id)
        if len(player.queue) < 2:
            await interaction.response.send_message("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return

        count = player.shuffle()
        await interaction.response.send_message(f"🔀 Shuffled **{count}** tracks in the queue.")

    @app_commands.command(name="remove", description="Remove a specific song from the queue by its position index.")
    @app_commands.describe(index="Position number in the queue (use /queue to check)")
    @is_same_voice_channel()
    async def remove(self, interaction: discord.Interaction, index: int):
        player = self._get_player(interaction.guild.id)
        removed = player.remove(index)

        if removed:
            await interaction.response.send_message(
                f"🗑️ Removed `#{index}`: **{removed.track.artist} - {removed.track.title}** from the queue."
            )
        else:
            await interaction.response.send_message(
                f"❌ Invalid queue position. Must be between 1 and {len(player.queue)}.",
                ephemeral=True
            )

    @app_commands.command(name="debug_voice", description="Check voice channel permissions, latency, and audio connection health.")
    async def debug_voice(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        bot_member = guild.me
        user_voice = interaction.user.voice

        embed = discord.Embed(
            title="🛠️ Voice Diagnostics & Health",
            color=discord.Color.blue()
        )

        vc = guild.voice_client
        if vc and vc.channel:
            perms = vc.channel.permissions_for(bot_member)
            embed.add_field(
                name="Voice Connection",
                value=(
                    f"**Channel:** {vc.channel.name}\n"
                    f"**Connected:** {'✅ Yes' if vc.is_connected() else '❌ No'}\n"
                    f"**Playing Audio:** {'🔊 Yes' if vc.is_playing() else '⏸️ Paused' if vc.is_paused() else '⏹️ Idle'}\n"
                    f"**Latency:** {round(vc.latency * 1000, 1)}ms\n"
                    f"**Encryption Mode:** `{getattr(vc, 'mode', 'unknown')}`"
                ),
                inline=False
            )
            embed.add_field(
                name="Bot Permissions & State",
                value=(
                    f"**Connect:** {'✅ Granted' if perms.connect else '❌ MISSING'}\n"
                    f"**Speak:** {'✅ Granted' if perms.speak else '❌ MISSING (Audio cannot be heard!)'}\n"
                    f"**Server Muted:** {'⚠️ YES (Unmute the bot!)' if bot_member.voice and bot_member.voice.mute else '✅ No'}\n"
                    f"**Server Deafened:** {'⚠️ Yes' if bot_member.voice and bot_member.voice.deaf else 'No'}"
                ),
                inline=False
            )
        else:
            embed.add_field(name="Voice Connection", value="Bot is not currently in any voice channel.", inline=False)

        if user_voice and user_voice.channel:
            embed.add_field(
                name="Your Voice State",
                value=(
                    f"**Channel:** {user_voice.channel.name}\n"
                    f"**Deafened:** {'⚠️ Yes (You cannot hear audio)' if user_voice.self_deaf or user_voice.deaf else 'No'}\n"
                    f"**Muted:** {'Yes' if user_voice.self_mute or user_voice.mute else 'No'}"
                ),
                inline=False
            )

        embed.set_footer(text="DevUpWard Music • Tip: Right-click the bot in voice to ensure 'User Volume' is > 0%")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Auto-disconnects if the bot is left alone in a voice channel."""
        # Only care if someone left a channel
        if not before.channel or before.channel == after.channel:
            return

        # Check if the channel is the one the bot is currently in
        bot_voice = member.guild.voice_client
        if not bot_voice or not bot_voice.channel or bot_voice.channel.id != before.channel.id:
            return

        # Count real members (excluding bots) in the channel
        human_members = [m for m in before.channel.members if not m.bot]
        if len(human_members) == 0:
            logger.info(f"[Guild {member.guild.id}] Bot left alone in voice channel. Disconnecting.")
            player = self._get_player(member.guild.id)
            if player.text_channel:
                await player.text_channel.send("👋 Left the voice channel because everyone left.")
            await player.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    logger.info("Music cog successfully loaded.")
