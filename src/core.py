import logging
from datetime import UTC, datetime, timedelta
from typing import override

import discord
from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import format_dt

from config.config_data import DEV_GUILD, DEV_ID
from src.bot import DirectAnnouncerBot
from src.database import EventDB, GuildDB, LogDB
from src.events import Events
from src.scraping.nintendo_direct import get_next_nintendo_direct
from src.scraping.pokemon_presents import get_next_pokemon_presents
from src.scraping.scraper_exceptions import ParseException, ScrapeException
from src.util import MENTION_ROLES, NO_MENTIONS_AT_ALL

_POKEMON_YT_CHANNEL = "https://www.youtube.com/@pokemon/videos"
_NINTENDO_YT_CHANNEL = "https://www.youtube.com/@NintendoAmerica/videos"
_INTERNAL_NOTIFICATION_OFFSET = timedelta(minutes=5)
_LOGGER = logging.getLogger(f"dabot.{__name__}")


def _notify_for_event(
    *,
    bot: DirectAnnouncerBot,
    event: Events,
    dt: datetime,
) -> None:
    guild_configs = GuildDB.get_all_guilds_for_event(event)
    for guild_id, settings in guild_configs.items():
        guild = bot.get_guild(guild_id)
        if guild is None:
            _LOGGER.info("Had config for guild %d but guild is unknown", guild_id)
            continue

        channel = guild.get_channel(settings.channel_id)
        if channel is None:
            _LOGGER.info(
                "Unknown channel %d in guild %d",
                settings.channel_id,
                guild_id,
            )
            continue

        if not isinstance(channel, discord.TextChannel):
            _LOGGER.info(
                "Non-TextChannel %d in event config in guild %d",
                channel.id,
                guild_id,
            )
            continue

        role = guild.get_role(settings.ping_role_id)
        if role is None:
            _LOGGER.info("Unknown role %d in guild %d", settings.ping_role_id, guild_id)
            continue

        channel_link = (
            _NINTENDO_YT_CHANNEL if event is Events.DIRECT else _POKEMON_YT_CHANNEL
        )
        _LOGGER.debug("Notifying guild %d about %r", guild_id, event)
        try:
            coro = channel.send(
                (
                    f"{role.mention}\n"
                    f"{event.to_display_str()} is starting soon!\n"
                    f"Scheduled for {format_dt(dt, style="s")} "
                    f"({format_dt(dt, style="R")}).\n\n"
                    f"Channel link: {channel_link}"
                ),
                allowed_mentions=MENTION_ROLES,
            )
            bot.loop.create_task(coro)
        except discord.HTTPException as e:
            _LOGGER.error(
                "Failed to notify guild %d about %r",
                guild_id,
                event,
                exc_info=e,
            )
            continue

    _LOGGER.info("Notified all guilds about %r", event)
    LogDB.log_run(event, dt)
    return None


class CoreCog(commands.Cog, name="Core"):

    def __init__(self, bot: DirectAnnouncerBot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=UTC)

    @override
    async def cog_load(self) -> None:
        self.scraper_task.start()
        self.scheduler.start()

    @override
    async def cog_unload(self) -> None:
        self.scraper_task.stop()
        if self.scheduler.running:
            self.scheduler.shutdown()

    def _schedule_notification(
        self,
        dt: datetime,
        event: Events,
    ) -> None:
        current_job = self.scheduler.get_job(event.to_job_id())
        assert isinstance(current_job, Job) or current_job is None
        if (current_job is None) or (current_job.next_run_time != dt):
            _LOGGER.debug("Scheduling job: %r for %r", event, dt.isoformat())
            self.scheduler.add_job(
                _notify_for_event,
                trigger=DateTrigger(dt - _INTERNAL_NOTIFICATION_OFFSET, timezone=UTC),
                kwargs={
                    "bot": self.bot,
                    "event": event,
                    "dt": dt,
                },
                id=event.to_job_id(),
                name=f"{event.to_display_str()} Notification Job",
                misfire_grace_time=60,
                replace_existing=True,
            )
        return None

    @tasks.loop(hours=6)
    async def scraper_task(self) -> None:
        try:
            next_direct_dt = await get_next_nintendo_direct()
            if next_direct_dt is not None:
                self._schedule_notification(next_direct_dt, Events.DIRECT)
        except (ScrapeException, ParseException) as e:
            _LOGGER.error(e.msg)

        try:
            next_pokemon_dt = await get_next_pokemon_presents()
            if next_pokemon_dt is not None:
                self._schedule_notification(next_pokemon_dt, Events.POKEMON)
        except (ScrapeException, ParseException) as e:
            _LOGGER.error(e.msg)

    @scraper_task.before_loop
    async def before_scraper_task(self) -> None:
        await self.bot.wait_until_ready()

    @commands.hybrid_group()
    @app_commands.guild_only()
    async def configure(self, _: commands.Context[DirectAnnouncerBot]) -> None:
        pass

    @configure.command(name="channel")
    @app_commands.guild_only()
    async def configure_channel(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
        channel: discord.TextChannel | None = None,
    ) -> None:
        """Show or change the channel in which the bot will ping.

        **Required User Permissions**:

        - Manage Server

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        channel : discord.TextChannel | None
            (Optional) The new channel to ping in
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.channel.permissions_for(ctx.author).manage_guild:
            return None

        if channel is None:
            current_channel_id = GuildDB.get_channel(guild_id=ctx.guild.id)
            if current_channel_id is None:
                msg = "No channel currently configured."
            else:
                ch = ctx.guild.get_channel(current_channel_id)
                if ch is None:
                    msg = (
                        "The currently configured channel does not exist. Please "
                        "update the channel."
                    )
                else:
                    msg = f"The bot will notify users in the {ch.mention} channel."

            await ctx.reply(msg)
            return None

        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.reply(
                (
                    f"The bot cannot send messages in {channel.mention}. Please adjust "
                    f"permissions or choose a different text channel."
                ),
            )
            return None

        GuildDB.set_channel(guild_id=ctx.guild.id, channel_id=channel.id)

        await ctx.reply(
            f"The bot will now use the {channel.mention} channel to notify users.",
        )
        return None

    @configure.command(name="directs-role")
    @app_commands.guild_only()
    async def configure_directs_ping_role(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
        role: discord.Role | None = None,
    ) -> None:
        """Show or change the role to ping for Nintendo Directs

        **Required Bot Permissions**:

        - Manage Roles

        **Required User Permissions**:

        - Manage Server

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        role : discord.Role | None
            (Optional) The new role to ping for Nintendo Directs
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.channel.permissions_for(ctx.author).manage_guild:
            return None
        elif not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.reply(
                (
                    "The bot cannot currently assign/remove roles, which is required "
                    "for users to be able to subscribe/unsubscribe from pings. Please "
                    "provide the bot with the `Manage Roles` permission."
                ),
            )
            return None

        if role is None:
            current_role_id = GuildDB.get_ping_role(
                guild_id=ctx.guild.id,
                event=Events.DIRECT,
            )
            if current_role_id is None:
                msg = "No notification role for Nintendo Directs configured."
            else:
                r = ctx.guild.get_role(current_role_id)
                if r is None:
                    msg = (
                        "The currently configured notification role for Nintendo "
                        "Directs does not exist. Please choose a new role."
                    )
                else:
                    msg = (
                        f"The bot will ping the {r.mention} role for Nintendo Directs."
                    )

            await ctx.reply(msg, allowed_mentions=NO_MENTIONS_AT_ALL)
            return None

        if not role.mentionable:
            await ctx.reply(
                (
                    "The bot cannot mention this role. Please adjust the mentioning "
                    "permissions on this role or choose a different one."
                ),
            )
            return None

        GuildDB.set_ping_role(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
            role_id=role.id,
        )

        await ctx.reply(
            (
                f"The bot will now use the {role.mention} role to notify users about "
                f"Nintendo Directs."
            ),
            allowed_mentions=NO_MENTIONS_AT_ALL,
        )
        return None

    @configure.command(name="pokemon-role")
    @app_commands.guild_only()
    async def configure_pokemon_ping_role(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
        role: discord.Role | None = None,
    ) -> None:
        """Show or change the role to ping for Pokémon Presents

        **Required Bot Permissions**:

        - Manage Roles

        **Required User Permissions**:

        - Manage Server

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        role : discord.Role | None
            (Optional) The new role to ping for Pokémon Presents
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.channel.permissions_for(ctx.author).manage_guild:
            return None
        elif not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.reply(
                (
                    "The bot cannot currently assign/remove roles, which is required "
                    "for users to be able to subscribe/unsubscribe from pings. Please "
                    "provide the bot with the `Manage Roles` permission."
                ),
            )
            return None

        if role is None:
            current_role_id = GuildDB.get_ping_role(
                guild_id=ctx.guild.id,
                event=Events.POKEMON,
            )
            if current_role_id is None:
                msg = "No notification role for Pokémon Presents configured."
            else:
                r = ctx.guild.get_role(current_role_id)
                if r is None:
                    msg = (
                        "The currently configured notification role for Pokémon "
                        "Presents does not exist. Please choose a new role."
                    )
                else:
                    msg = (
                        f"The bot will ping the {r.mention} role for Pokémon Presents."
                    )

            await ctx.reply(msg, allowed_mentions=NO_MENTIONS_AT_ALL)
            return None

        if not role.mentionable:
            await ctx.reply(
                (
                    "The bot cannot mention this role. Please adjust the mentioning "
                    "permissions on this role or choose a different one."
                ),
            )
            return None

        GuildDB.set_ping_role(
            guild_id=ctx.guild.id,
            event=Events.POKEMON,
            role_id=role.id,
        )

        await ctx.reply(
            (
                f"The bot will now use the {role.mention} role to notify users about "
                f"Pokémon Presents."
            ),
            allowed_mentions=NO_MENTIONS_AT_ALL,
        )
        return None

    @configure.command(name="directs")
    @app_commands.guild_only()
    async def configure_directs(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
        enabled: bool | None = None,
    ) -> None:
        """Show or toggle notifications for Nintendo Directs for this server

        **Required User Permissions**:

        - Manage Server

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        enabled : bool | None
            (Optional) Allow/disallow Nintendo Directs
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.channel.permissions_for(ctx.author).manage_guild:
            return None

        if enabled is None:
            directs_enabled = GuildDB.get_pings_enabled(
                guild_id=ctx.guild.id,
                event=Events.DIRECT,
            )
            state_str = "enabled" if directs_enabled else "disabled"
            msg = f"Nintendo Direct notifications are currently **{state_str}**."

            await ctx.reply(msg)
            return None

        GuildDB.set_pings_enabled(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
            pings_enabled=enabled,
        )

        action = "Enabled" if enabled else "Disabled"
        await ctx.reply(f"{action} notifications for Nintendo Directs.")
        return None

    @configure.command(name="pokemon")
    @app_commands.guild_only()
    async def configure_pokemon(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
        enabled: bool | None = None,
    ) -> None:
        """Show or toggle notifications for Pokémon Presents for this server

        **Required User Permissions**:

        - Manage Server

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        enabled : bool | None
            (Optional) Allow/disallow Pokémon Presents
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.channel.permissions_for(ctx.author).manage_guild:
            return None

        if enabled is None:
            pokemon_enabled = GuildDB.get_pings_enabled(
                guild_id=ctx.guild.id,
                event=Events.POKEMON,
            )
            state_str = "enabled" if pokemon_enabled else "disabled"
            msg = f"Pokémon Presents notifications are currently **{state_str}**."

            await ctx.reply(msg)
            return None

        GuildDB.set_pings_enabled(
            guild_id=ctx.guild.id,
            event=Events.POKEMON,
            pings_enabled=enabled,
        )

        action = "Enabled" if enabled else "Disabled"
        await ctx.reply(f"{action} notifications for Pokémon Presents.")
        return None

    @commands.hybrid_group()
    @app_commands.guild_only()
    async def subscribe(self, _: commands.Context[DirectAnnouncerBot]) -> None:
        pass

    @subscribe.command(name="directs", aliases=["direct"])
    @app_commands.guild_only()
    async def subscribe_directs(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
    ) -> None:
        """Subscribe to Nintendo Directs notifications

        **Required Bot Permissions**:

        - Manage Roles

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.reply(
                (
                    "The bot cannot currently assign/remove roles, which is required "
                    "for users to be able to subscribe/unsubscribe from pings. Please "
                    "provide the bot with the `Manage Roles` permission."
                ),
            )
            return None

        directs_enabled = GuildDB.get_pings_enabled(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if not directs_enabled:
            await ctx.reply(
                (
                    "This server has not enabled notifications for Nintendo Directs so "
                    "you cannot subscribe to them."
                ),
            )
            return None

        role_id = GuildDB.get_ping_role(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if role_id is None:
            await ctx.reply(
                (
                    "This server has not configured a notification role for Nintendo "
                    "Directs so you cannot subscribe to them."
                ),
            )
            return None
        elif role_id in [r.id for r in ctx.author.roles]:
            await ctx.reply(
                (
                    "You are currently subscribed to Nintendo Directs. Use "
                    "`/unsubscribe directs` to unsubscribe."
                ),
            )
            return None

        try:
            await ctx.author.add_roles(
                discord.Object(id=role_id),
                reason="Subscribed to Nintendo Direct notifications",
            )
        except discord.HTTPException:
            await ctx.reply(
                (
                    "An error occurred trying to assign you the Nintendo Directs ping "
                    "role."
                ),
            )
            return None

        await ctx.reply("Successfully subscribed you to Nintendo Direct notifications.")
        return None

    @subscribe.command(name="pokemon")
    @app_commands.guild_only()
    async def subscribe_pokemon(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
    ) -> None:
        """Subscribe to Pokémon Presents notifications

        **Required Bot Permissions**:

        - Manage Roles

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.reply(
                (
                    "The bot cannot currently assign/remove roles, which is required "
                    "for users to be able to subscribe/unsubscribe from pings. Please "
                    "provide the bot with the `Manage Roles` permission."
                ),
            )
            return None

        pokemon_enabled = GuildDB.get_pings_enabled(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if not pokemon_enabled:
            await ctx.reply(
                (
                    "This server has not enabled notifications for Pokémon Presents so "
                    "you cannot subscribe to them."
                ),
            )
            return None

        role_id = GuildDB.get_ping_role(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if role_id is None:
            await ctx.reply(
                (
                    "This server has not configured a notification role for Pokémon "
                    "Presents so you cannot subscribe to them."
                ),
            )
            return None
        elif role_id in [r.id for r in ctx.author.roles]:
            await ctx.reply(
                (
                    "You are currently subscribed to Pokémon Presents. Use "
                    "`/unsubscribe directs` to unsubscribe."
                ),
            )
            return None

        try:
            await ctx.author.add_roles(
                discord.Object(id=role_id),
                reason="Subscribed to Pokémon Present notifications",
            )
        except discord.HTTPException:
            await ctx.reply(
                (
                    "An error occurred trying to assign you the Pokémon Presents ping "
                    "role."
                ),
            )
            return None

        await ctx.reply("Successfully subscribed you to Pokémon Present notifications.")
        return None

    @commands.hybrid_group()
    @app_commands.guild_only()
    async def unsubscribe(self, _: commands.Context[DirectAnnouncerBot]) -> None:
        pass

    @unsubscribe.command(name="directs")
    @app_commands.guild_only()
    async def unsubscribe_directs(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
    ) -> None:
        """Unsubscribe from Nintendo Direct notifications

        **Required Bot Permissions**:

        - Manage Roles

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.reply(
                (
                    "The bot cannot currently assign/remove roles, which is required "
                    "for users to be able to subscribe/unsubscribe from pings. Please "
                    "provide the bot with the `Manage Roles` permission."
                ),
            )
            return None

        directs_enabled = GuildDB.get_pings_enabled(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if not directs_enabled:
            await ctx.reply(
                (
                    "This server has not enabled notifications for Nintendo Directs so "
                    "you cannot unsubscribe from them."
                ),
            )
            return None

        role_id = GuildDB.get_ping_role(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if role_id is None:
            await ctx.reply(
                (
                    "This server has not configured notifications for Nintendo "
                    "Directs, so you cannot unsubscribe from them."
                ),
            )
            return None
        elif role_id not in [r.id for r in ctx.author.roles]:
            await ctx.reply(
                (
                    "You are not currently subscribed to Nintendo Direct "
                    "notifications. Use `/subscribe directs` to subscribe."
                ),
            )
            return None

        try:
            await ctx.author.remove_roles(discord.Object(id=role_id))
        except discord.HTTPException:
            await ctx.reply(
                (
                    "An error occurred trying to remove you from the Nintendo Directs "
                    "notification role."
                ),
            )
            return None

        await ctx.reply(
            "Successfully unsubscribed you from Nintendo Direct notifications.",
        )
        return None

    @unsubscribe.command(name="pokemon")
    @app_commands.guild_only()
    async def unsubscribe_pokemon(
        self,
        ctx: commands.Context[DirectAnnouncerBot],
    ) -> None:
        """Unsubscribe from Pokémon Presents notifications

        **Required Bot Permissions**:

        - Manage Roles

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        """
        if ctx.guild is None:
            return None
        elif isinstance(ctx.author, discord.User):
            return None
        elif not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.reply(
                (
                    "The bot cannot currently assign/remove roles, which is required "
                    "for users to be able to subscribe/unsubscribe from pings. Please "
                    "provide the bot with the `Manage Roles` permission."
                ),
            )
            return None

        directs_enabled = GuildDB.get_pings_enabled(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if not directs_enabled:
            await ctx.reply(
                (
                    "This server has not enabled notifications for Pokémon Presents so "
                    "you cannot unsubscribe from them."
                ),
            )
            return None

        role_id = GuildDB.get_ping_role(
            guild_id=ctx.guild.id,
            event=Events.DIRECT,
        )
        if role_id is None:
            await ctx.reply(
                (
                    "This server has not configured notifications for Pokémon "
                    "Presents, so you cannot unsubscribe from them."
                ),
            )
            return None
        elif role_id not in [r.id for r in ctx.author.roles]:
            await ctx.reply(
                (
                    "You are not currently subscribed to Pokémon Presents "
                    "notifications. Use `/subscribe directs` to subscribe."
                ),
            )
            return None

        try:
            await ctx.author.remove_roles(discord.Object(id=role_id))
        except discord.HTTPException:
            await ctx.reply(
                (
                    "An error occurred trying to remove you from the Pokémon Presents "
                    "notification role."
                ),
            )
            return None

        await ctx.reply(
            "Successfully unsubscribed you from Pokémon Presents notifications.",
        )
        return None

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def upcoming(self, ctx: commands.Context[DirectAnnouncerBot]) -> None:
        """Show upcoming events, if any

        Parameters
        ----------
        ctx : commands.Context[DirectAnnouncerBot]
        """
        if ctx.guild is None:
            return None

        now = datetime.now(UTC)

        direct_dt = EventDB.get_event_timestamp(Events.DIRECT)
        pokemon_dt = EventDB.get_event_timestamp(Events.POKEMON)

        direct_msg = ""
        if direct_dt is not None and direct_dt > now:
            # Discord does automatic list numbering even if everything is "1."
            direct_msg = (
                f"1. **Nintendo Direct** on {format_dt(direct_dt, style="F")} "
                f"({format_dt(direct_dt, style="R")})"
            )

        pokemon_msg = ""
        if pokemon_dt is not None and pokemon_dt > now:
            # Discord does automatic list numbering even if everything is "1."
            pokemon_msg = (
                f"1. **Pokémon Presents** on {format_dt(pokemon_dt, style="F")} "
                f"({format_dt(pokemon_dt, style="R")})"
            )

        if direct_dt is not None and pokemon_dt is not None:
            if direct_dt < pokemon_dt:
                msg = f"{direct_msg}\n{pokemon_msg}"
            else:
                msg = f"{pokemon_msg}\n{direct_msg}"
        else:
            msg = f"{direct_msg}\n{pokemon_msg}"

        if msg.strip() == "":
            msg = "None at this time"

        out = (
            f"__Upcoming Events__\n\n"
            f"{msg.strip()}"
            f"\n\n-# Please note that it may take a bit for new events to be found."
        )

        await ctx.reply(out)
        return None

    @commands.command(hidden=True, aliases=["debug", "state"])
    async def jobs(self, ctx: commands.Context[DirectAnnouncerBot]) -> None:
        if ctx.author.id != DEV_ID or ctx.guild is None or ctx.guild.id != DEV_GUILD:
            return None

        jobs: list[Job] = self.scheduler.get_jobs()
        jobs.sort(key=lambda j: j.next_run_time)
        job_strs: list[str] = []
        for job in jobs:
            run_dt: datetime = job.next_run_time
            job_strs.append(
                (
                    f"1. Scheduled job `{job.id}`:\n"
                    f"  Name: `{job.name}`\n"
                    f"  Next run time: `{run_dt.isoformat()}` "
                    f"({format_dt(run_dt, style="s")}) ({format_dt(run_dt, style="R")})"
                ),
            )

        msg = "" + "\n---\n".join(job_strs).strip()

        if msg.strip() == "":
            msg = "No jobs currently scheduled."

        await ctx.reply(msg)
        return None

    @commands.command(hidden=True)
    async def restart(self, ctx: commands.Context[DirectAnnouncerBot]) -> None:
        if ctx.author.id != DEV_ID or ctx.guild is None or ctx.guild.id != DEV_GUILD:
            return None

        self.scraper_task.restart()

        await ctx.reply("Background task restarted successfully.")
        return None


async def setup(bot: DirectAnnouncerBot) -> None:
    await bot.add_cog(CoreCog(bot))
