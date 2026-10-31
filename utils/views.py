import math
from typing import TYPE_CHECKING, Optional

import discord

if TYPE_CHECKING:
    from services.player import GuildPlayer, LoopMode


class MusicControlView(discord.ui.View):
    """
    Interactive button view attached to the Now Playing embed.
    Allows users to Pause/Resume, Skip, Stop, Loop, and Shuffle with one click.
    """

    def __init__(self, player: "GuildPlayer", timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.player = player
        self._update_button_labels()

    def _update_button_labels(self):
        # Update pause/resume button label and emoji
        pause_btn: discord.ui.Button = self.children[0]
        if self.player.is_paused:
            pause_btn.label = "Resume"
            pause_btn.emoji = "▶️"
            pause_btn.style = discord.ButtonStyle.success
        else:
            pause_btn.label = "Pause"
            pause_btn.emoji = "⏸️"
            pause_btn.style = discord.ButtonStyle.secondary

        # Update loop button label
        loop_btn: discord.ui.Button = self.children[3]
        loop_btn.label = f"Loop: {self.player.loop_mode.value.capitalize()}"

    async def _check_user_voice(self, interaction: discord.Interaction) -> bool:
        """Verifies clicking user is in the same voice channel as the bot."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ You must be in a voice channel to control playback.",
                ephemeral=True
            )
            return False

        if not self.player.voice_client or not self.player.voice_client.channel:
            await interaction.response.send_message(
                "❌ Bot is not currently in a voice channel.",
                ephemeral=True
            )
            return False

        if interaction.user.voice.channel.id != self.player.voice_client.channel.id:
            await interaction.response.send_message(
                f"❌ You must be in {self.player.voice_client.channel.mention} to use these controls.",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="btn_play_pause", row=0)
    async def toggle_play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_user_voice(interaction):
            return

        if self.player.is_paused:
            self.player.resume()
        elif self.player.is_playing:
            self.player.pause()

        self._update_button_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.primary, custom_id="btn_skip", row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_user_voice(interaction):
            return

        current_title = self.player.current.track.title if self.player.current else "track"
        self.player.skip()
        await interaction.response.send_message(f"⏭️ {interaction.user.mention} skipped **{current_title}**.", ephemeral=False)

    @discord.ui.button(label="Stop", emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="btn_stop", row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_user_voice(interaction):
            return

        await self.player.disconnect()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="⏹️ Playback stopped and bot disconnected.", view=self)

    @discord.ui.button(label="Loop: Off", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="btn_loop", row=1)
    async def toggle_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_user_voice(interaction):
            return

        from services.player import LoopMode
        # Cycle through: OFF -> TRACK -> QUEUE -> OFF
        if self.player.loop_mode == LoopMode.OFF:
            self.player.set_loop_mode("track")
        elif self.player.loop_mode == LoopMode.TRACK:
            self.player.set_loop_mode("queue")
        else:
            self.player.set_loop_mode("off")

        self._update_button_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Shuffle", emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="btn_shuffle", row=1)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_user_voice(interaction):
            return

        if len(self.player.queue) < 2:
            await interaction.response.send_message("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return

        count = self.player.shuffle()
        await interaction.response.send_message(f"🔀 Shuffled **{count}** tracks in the queue.", ephemeral=False)


class QueuePaginationView(discord.ui.View):
    """
    Pagination view for navigating large queues page by page.
    """

    def __init__(self, player: "GuildPlayer", current_page: int = 1, items_per_page: int = 10):
        super().__init__(timeout=120)
        self.player = player
        self.current_page = current_page
        self.items_per_page = items_per_page
        self.total_pages = max(1, math.ceil(len(player.queue) / items_per_page))
        self._update_buttons()

    def _update_buttons(self):
        # Prev button
        self.children[0].disabled = (self.current_page <= 1)
        # Next button
        self.children[1].disabled = (self.current_page >= self.total_pages)

    def build_embed(self, guild_name: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"📋 Queue for {guild_name}",
            color=discord.Color.blue()
        )

        if self.player.current:
            embed.add_field(
                name="🔊 Currently Playing",
                value=f"[{self.player.current.track.artist} - {self.player.current.track.title}]({self.player.current.track.url}) | "
                      f"`{self.player.current.track.formatted_duration}` | "
                      f"Req: {self.player.current.requester.mention}",
                inline=False
            )

        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        queue_slice = self.player.queue[start_idx:end_idx]

        if queue_slice:
            lines = [
                f"`{i}.` [{item.track.artist} - {item.track.title}]({item.track.url}) "
                f"(`{item.track.formatted_duration}`) - {item.requester.mention}"
                for i, item in enumerate(queue_slice, start=start_idx + 1)
            ]
            embed.add_field(name="Upcoming Songs", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Upcoming Songs", value="No more tracks queued.", inline=False)

        total_duration_sec = sum(item.track.duration_seconds for item in self.player.queue)
        q_minutes, q_seconds = divmod(total_duration_sec, 60)

        embed.set_footer(
            text=f"Page {self.current_page}/{self.total_pages} • Total queued: {len(self.player.queue)} songs ({q_minutes}m {q_seconds}s) • Loop: {self.player.loop_mode.value.capitalize()}"
        )
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
        self._update_buttons()
        embed = self.build_embed(interaction.guild.name)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages:
            self.current_page += 1
        self._update_buttons()
        embed = self.build_embed(interaction.guild.name)
        await interaction.response.edit_message(embed=embed, view=self)

