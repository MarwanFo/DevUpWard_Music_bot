import time
import platform
import discord
from discord import app_commands
from discord.ext import commands

from utils.logger import setup_logger

logger = setup_logger("AdminCog")


class AdminCog(commands.Cog, name="Admin"):
    """
    Administrative and diagnostic commands: ping, stats, and error handling.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(name="ping", description="Check the bot's WebSocket and interaction latency.")
    async def ping(self, interaction: discord.Interaction):
        start = time.perf_counter()
        # Defer immediately to get an accurate round-trip time measurement
        await interaction.response.defer(ephemeral=False)
        end = time.perf_counter()

        round_trip_ms = round((end - start) * 1000)
        ws_latency_ms = round(self.bot.latency * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green()
        )
        embed.add_field(name="Gateway Latency", value=f"`{ws_latency_ms} ms`", inline=True)
        embed.add_field(name="API Round-trip", value=f"`{round_trip_ms} ms`", inline=True)
        embed.set_footer(text="Spotify Music Bot • Phase 1 Active")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="status", description="Display system and bot performance diagnostics.")
    async def status(self, interaction: discord.Interaction):
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        embed = discord.Embed(
            title="🤖 Bot Diagnostics & Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="Servers Connected", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="Voice Connections", value=f"`{len(self.bot.voice_clients)}`", inline=True)
        embed.add_field(name="Uptime", value=f"`{uptime_str}`", inline=True)
        embed.add_field(name="Python Version", value=f"`{platform.python_version()}`", inline=True)
        embed.add_field(name="discord.py Version", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="Platform", value=f"`{platform.system()} {platform.release()}`", inline=True)
        embed.set_footer(text="Spotify Music Bot Engine")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
    logger.info("Admin cog successfully loaded.")

