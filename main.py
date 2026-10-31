import asyncio
import os
import signal
import sys
import discord
from discord.ext import commands

from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger("MusicBot", level=settings.LOG_LEVEL)


class MusicBot(commands.Bot):
    """
    Core Discord Bot client with asynchronous extension loading
    and guild-aware slash command synchronization.
    """

    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.guilds = True
        # Slash commands do not require privileged Message Content intent

        super().__init__(
            command_prefix="!",  # Fallback prefix (primary interface is Slash Commands)
            intents=intents,
            help_command=None,
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="/play | Spotify Music"
            )
        )

    async def setup_hook(self):
        """
        Executed automatically prior to the bot connecting to the Discord Gateway.
        Loads all Cogs and synchronizes Slash Commands with the Discord API.
        """
        logger.info("Initializing bot subsystems and loading extensions...")

        # Dynamically load all cogs from the cogs/ directory
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                extension_name = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(extension_name)
                    logger.info(f"Loaded extension: {extension_name}")
                except Exception as e:
                    logger.exception(f"Failed to load extension {extension_name}: {e}")

        # Synchronize Application (Slash) Commands
        try:
            if settings.DEV_GUILD_ID:
                dev_guild = discord.Object(id=settings.DEV_GUILD_ID)
                self.tree.copy_global_to(guild=dev_guild)
                synced = await self.tree.sync(guild=dev_guild)
                logger.info(f"Successfully synced {len(synced)} slash commands to Dev Guild [{settings.DEV_GUILD_ID}].")
            else:
                synced = await self.tree.sync()
                logger.info(f"Successfully synced {len(synced)} slash commands globally.")
        except Exception as e:
            logger.exception(f"Error synchronizing application commands: {e}")

    async def on_ready(self):
        logger.info(f"Bot logged in as: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} server(s).")
        logger.info("Bot is ready and listening for interactions!")

    async def on_app_command_completion(self, interaction: discord.Interaction, command: discord.app_commands.Command):
        logger.debug(f"Command '{command.name}' executed by {interaction.user} in guild {interaction.guild_id}")


async def main():
    # 1. Validate environment configuration
    config_warnings = settings.validate_production_readiness()
    if config_warnings:
        logger.warning("================ CONFIGURATION WARNING ================")
        for warning in config_warnings:
            logger.warning(f"-> {warning}")
        logger.warning("Please configure your .env file with valid credentials.")
        logger.warning("=======================================================")

        if not settings.DISCORD_BOT_TOKEN:
            logger.critical("Cannot start bot without a valid DISCORD_BOT_TOKEN. Exiting.")
            sys.exit(1)

    # 2. Instantiate and launch the bot
    bot = MusicBot()

    # Graceful shutdown handling
    loop = asyncio.get_running_loop()

    def handle_shutdown_signal():
        logger.info("Received termination signal. Initiating graceful shutdown...")
        asyncio.create_task(bot.close())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_shutdown_signal)
        except NotImplementedError:
            # Signal handlers are not fully supported on some Windows event loops
            pass

    async with bot:
        await bot.start(settings.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")

