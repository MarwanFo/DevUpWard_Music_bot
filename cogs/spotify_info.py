import asyncio
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from services.player import get_player_manager
from services.spotify_client import spotify_client
from utils.logger import setup_logger

logger = setup_logger("SpotifyInfoCog")


class LyricsPaginationView(discord.ui.View):
    """View to paginate long lyrics exceeding Discord's embed description limit."""

    def __init__(self, pages: list[str], title: str, artist: str):
        super().__init__(timeout=120)
        self.pages = pages
        self.title = title
        self.artist = artist
        self.current_page = 0
        self._update_buttons()

    def _update_buttons(self):
        self.children[0].disabled = (self.current_page <= 0)
        self.children[1].disabled = (self.current_page >= len(self.pages) - 1)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"📜 Lyrics: {self.artist} - {self.title}",
            description=self.pages[self.current_page],
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.pages)} • Source: Lrclib")
        return embed

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class SpotifyInfoCog(commands.Cog, name="Discovery"):
    """
    Spotify metadata, artist profiles, track details, and lyrics integration.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.player_manager = get_player_manager(bot)

    @app_commands.command(name="artist", description="Look up an artist on Spotify and see their top tracks.")
    @app_commands.describe(name="Artist name or Spotify artist URL")
    async def artist(self, interaction: discord.Interaction, name: str):
        if not spotify_client.is_authenticated:
            await interaction.response.send_message("❌ Spotify client is not configured with API credentials.", ephemeral=True)
            return

        await interaction.response.defer()

        parsed = spotify_client.parse_url(name)
        artist_id = parsed[1] if parsed and parsed[0] == "artist" else None

        try:
            sp = spotify_client._sp
            if not artist_id:
                # Search for artist
                search_res = await asyncio.to_thread(sp.search, q=name, type="artist", limit=1)
                artists = search_res.get("artists", {}).get("items", [])
                if not artists:
                    await interaction.followup.send(f"❌ No artist found matching '{name}'.")
                    return
                artist_data = artists[0]
                artist_id = artist_data["id"]
            else:
                artist_data = await asyncio.to_thread(sp.artist, artist_id)

            # Fetch top tracks
            top_tracks_data = await asyncio.to_thread(sp.artist_top_tracks, artist_id)
            top_tracks = top_tracks_data.get("tracks", [])[:5]

            embed = discord.Embed(
                title=f"🎤 {artist_data.get('name')}",
                url=artist_data.get("external_urls", {}).get("spotify", ""),
                color=discord.Color.from_rgb(30, 215, 96)
            )

            followers = artist_data.get("followers", {}).get("total", 0)
            genres = ", ".join(artist_data.get("genres", [])[:4]).title() or "Not specified"
            images = artist_data.get("images", [])

            embed.add_field(name="Followers", value=f"{followers:,}", inline=True)
            embed.add_field(name="Popularity", value=f"{artist_data.get('popularity', 0)}/100", inline=True)
            embed.add_field(name="Genres", value=genres, inline=False)

            if top_tracks:
                tracks_desc = "\n".join([
                    f"`{i}.` [{t.get('name')}]({t.get('external_urls', {}).get('spotify')}) - *{t.get('album', {}).get('name')}*"
                    for i, t in enumerate(top_tracks, 1)
                ])
                embed.add_field(name="🔥 Top 5 Popular Tracks", value=tracks_desc, inline=False)

            if images:
                embed.set_thumbnail(url=images[0].get("url"))

            embed.set_footer(text="Data provided by official Spotify Web API")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Error fetching artist '{name}': {e}")
            await interaction.followup.send(f"❌ Error retrieving artist information: {e}")

    @app_commands.command(name="trackinfo", description="Get in-depth Spotify metadata and audio attributes for a track.")
    @app_commands.describe(query="Track name or Spotify track URL")
    async def trackinfo(self, interaction: discord.Interaction, query: str):
        if not spotify_client.is_authenticated:
            await interaction.response.send_message("❌ Spotify client is not configured with API credentials.", ephemeral=True)
            return

        await interaction.response.defer()

        parsed = spotify_client.parse_url(query)
        track_id = parsed[1] if parsed and parsed[0] == "track" else None

        try:
            sp = spotify_client._sp
            if not track_id:
                search_res = await asyncio.to_thread(sp.search, q=query, type="track", limit=1)
                items = search_res.get("tracks", {}).get("items", [])
                if not items:
                    await interaction.followup.send(f"❌ No track found matching '{query}'.")
                    return
                track_data = items[0]
                track_id = track_data["id"]
            else:
                track_data = await asyncio.to_thread(sp.track, track_id)

            track = spotify_client._parse_track_payload(track_data)

            embed = discord.Embed(
                title=f"🎵 {track.artist} - {track.title}",
                url=track.url,
                color=discord.Color.from_rgb(30, 215, 96)
            )
            embed.add_field(name="Album", value=track.album, inline=True)
            embed.add_field(name="Duration", value=track.formatted_duration, inline=True)
            if track.isrc:
                embed.add_field(name="ISRC", value=f"`{track.isrc}`", inline=True)

            embed.add_field(name="Popularity", value=f"{track_data.get('popularity', 0)}/100", inline=True)
            embed.add_field(name="Explicit", value="Yes 🔞" if track_data.get("explicit") else "No", inline=True)

            # Try to fetch audio features (with fallback if Spotify restricted the endpoint)
            try:
                features = await asyncio.to_thread(sp.audio_features, [track_id])
                if features and features[0]:
                    f = features[0]
                    bpm = round(f.get("tempo", 0))
                    energy = int(f.get("energy", 0) * 100)
                    dance = int(f.get("danceability", 0) * 100)
                    valence = int(f.get("valence", 0) * 100)  # Musical positiveness

                    embed.add_field(
                        name="🎧 Audio Characteristics",
                        value=f"• **BPM / Tempo:** `{bpm}`\n"
                              f"• **Energy:** `{energy}%`\n"
                              f"• **Danceability:** `{dance}%`\n"
                              f"• **Mood / Valence:** `{valence}%`",
                        inline=False
                    )
            except Exception as feat_err:
                logger.debug(f"Audio features endpoint skipped/restricted: {feat_err}")

            if track.cover_url:
                embed.set_thumbnail(url=track.cover_url)

            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.exception(f"Error fetching track info for '{query}': {e}")
            await interaction.followup.send(f"❌ Failed to retrieve track information: {e}")

    @app_commands.command(name="lyrics", description="Fetch song lyrics for the current track or a search query.")
    @app_commands.describe(query="Optional song name (defaults to currently playing song)")
    async def lyrics(self, interaction: discord.Interaction, query: Optional[str] = None):
        await interaction.response.defer()

        search_title = ""
        search_artist = ""

        # If no query provided, check currently playing track
        if not query:
            player = self.player_manager.get_player(interaction.guild.id)
            if player.current:
                search_title = player.current.track.title
                search_artist = player.current.track.artist
            else:
                await interaction.followup.send("❌ No track currently playing. Please provide a song query: `/lyrics [song name]`.")
                return
        else:
            search_title = query

        # Query Lrclib API (free, open, no token required)
        api_url = "https://lrclib.net/api/get"
        params = {"track_name": search_title}
        if search_artist:
            params["artist_name"] = search_artist

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_lyrics = data.get("plainLyrics") or data.get("syncedLyrics")
                        track_name = data.get("trackName", search_title)
                        artist_name = data.get("artistName", search_artist or "Unknown")
                    else:
                        # Fallback search endpoint
                        async with session.get("https://lrclib.net/api/search", params={"q": query or search_title}, timeout=aiohttp.ClientTimeout(total=8)) as search_resp:
                            if search_resp.status == 200:
                                search_data = await search_resp.json()
                                if search_data:
                                    first_match = search_data[0]
                                    raw_lyrics = first_match.get("plainLyrics") or first_match.get("syncedLyrics")
                                    track_name = first_match.get("trackName", search_title)
                                    artist_name = first_match.get("artistName", search_artist or "Unknown")
                                else:
                                    raw_lyrics = None
                            else:
                                raw_lyrics = None

            if not raw_lyrics:
                await interaction.followup.send(f"❌ No lyrics found for **{search_title}**.")
                return

            # Split lyrics into chunks of max 2000 chars to avoid Discord limits
            lines = raw_lyrics.split("\n")
            pages = []
            current_page = []
            current_len = 0

            for line in lines:
                if current_len + len(line) + 1 > 1800:
                    pages.append("\n".join(current_page))
                    current_page = [line]
                    current_len = len(line)
                else:
                    current_page.append(line)
                    current_len += len(line) + 1

            if current_page:
                pages.append("\n".join(current_page))

            if len(pages) == 1:
                embed = discord.Embed(
                    title=f"📜 Lyrics: {artist_name} - {track_name}",
                    description=pages[0],
                    color=discord.Color.gold()
                )
                embed.set_footer(text="Source: Lrclib")
                await interaction.followup.send(embed=embed)
            else:
                view = LyricsPaginationView(pages=pages, title=track_name, artist=artist_name)
                await interaction.followup.send(embed=view.build_embed(), view=view)

        except Exception as e:
            logger.exception(f"Error fetching lyrics for '{search_title}': {e}")
            await interaction.followup.send("⚠️ An error occurred while retrieving lyrics.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SpotifyInfoCog(bot))
    logger.info("SpotifyInfo cog successfully loaded.")

