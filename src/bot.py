import logging
from typing import override

import discord
from discord.ext import commands

from config.config_data import DEV_GUILD
from src.database import GuildDB
from src.util import NO_MENTIONS_AT_ALL

discord.VoiceClient.warn_dave = False
discord.VoiceClient.warn_nacl = False
_LOGGER = logging.getLogger(f"dabot.{__name__}")


class DirectAnnouncerBot(commands.Bot):
    def __init__(self, debug_mode: bool) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix="d!",
            intents=intents,
            activity=discord.CustomActivity(
                name="Looking out for Nintendo Directs & Pokémon Presents",
            ),
            allowed_mentions=NO_MENTIONS_AT_ALL,
        )
        self.debug_mode = debug_mode

    @override
    async def setup_hook(self) -> None:
        await self.load_extension("src.core")
        dev_guild_snowflake = discord.Object(id=DEV_GUILD)
        if self.debug_mode:
            self.tree.copy_global_to(guild=dev_guild_snowflake)
        else:
            await self.tree.sync(guild=dev_guild_snowflake)
            await self.tree.sync()

    # noinspection PyMethodMayBeStatic
    async def on_guild_join(self, guild: discord.Guild) -> None:
        _LOGGER.debug("Joined guild %r (ID: %d)!", guild.name, guild.id)
        GuildDB.add_guild(guild_id=guild.id)

    # noinspection PyMethodMayBeStatic
    async def on_guild_available(self, guild: discord.Guild) -> None:
        _LOGGER.debug("Guild %r (ID: %d) is available!", guild.name, guild.id)
        GuildDB.add_guild(guild_id=guild.id)
