# Standard Library
from datetime import datetime, timedelta
import asyncio
import contextlib

# Discord / Red Bot
import discord
import logging
from redbot.core import checks, commands, Config

# Only used for typing
from typing import cast
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

log = logging.getLogger("spAnser.daily")

def seconds_until_midnight():
    """Get the number of seconds until midnight."""
    tomorrow = datetime.now() + timedelta(1)
    midnight = datetime(year=tomorrow.year, month=tomorrow.month,
                        day=tomorrow.day, hour=0, minute=0, second=0)
    return (midnight - datetime.now()).seconds


class Daily(commands.Cog):
    """Daily
    Mute users after posting and reset once a day."""

    default_guild_settings = {
        "channels": [],
    }
    default_channel_settings = {
        "grace": 0,
        "ignored": [],
        "ignored_roles": [],
        "muted": []
    }

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.settings = Config.get_conf(self, identifier=536942012, force_registration=True)
        self.settings.register_guild(**self.default_guild_settings)
        self.settings.register_channel(**self.default_channel_settings)

        self.permission_clearing = asyncio.ensure_future(self.clear_permissions())

        self._ready = asyncio.Event()

    async def initialize(self):
        self._ready.set()

    async def cog_before_invoke(self, ctx: commands.Context) -> None:
        await self._ready.wait()

    def cog_unload(self):
        self.permission_clearing.cancel()

    async def clear_permissions(self):
        await self.bot.wait_until_ready()
        reason = "Daily Reset"
        with contextlib.suppress(RuntimeError, asyncio.CancelledError):  # Suppress the "Event loop is closed" error
            while self == self.bot.get_cog(self.__class__.__name__):
                await asyncio.sleep(seconds_until_midnight())

                guild_dict = await self.settings.all_guilds()
                for guild_id, info in guild_dict.items():
                    async with self.settings.guild_from_id(guild_id).channels() as channels:
                        for channel_id in channels:
                            channel: discord.TextChannel = self.bot.get_channel(channel_id)
                            muted = await self.settings.channel_from_id(channel_id).muted()

                            member_overwrites = list(
                                filter(lambda overwrite: isinstance(overwrite, discord.Member), channel.overwrites))

                            for member in member_overwrites:
                                if member.id not in muted:
                                    overwrites: discord.PermissionOverwrite = channel.overwrites_for(member)
                                    overwrites.update(send_messages=None)
                                    if overwrites.is_empty():
                                        await channel.set_permissions(
                                            member, overwrite=cast(discord.PermissionOverwrite, None), reason=reason
                                        )
                                    else:
                                        await channel.set_permissions(member, overwrite=overwrites, reason=reason)

    @commands.group()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True, manage_roles=True)
    async def daily(self, ctx: commands.Context):
        """Daily cog."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(color=(await ctx.embed_colour()))
            embed.title = "Channels Resetting Daily"
            embed.description = "Reset In: " + humanize_timedelta(seconds=seconds_until_midnight())
            await ctx.send(embed=embed)
            async with self.settings.guild(ctx.guild).channels() as channels:
                if len(channels) == 0:
                    return
                for channel_id in channels:
                    embed = discord.Embed(color=(await ctx.embed_colour()))
                    embed.title = "Channel Info"
                    channel: discord.TextChannel = self.bot.get_channel(channel_id)

                    description = "Channel: " + channel.mention
                    grace = await self.settings.channel(channel).grace()
                    if grace > 0:
                        description += "\nGrace Time: " + humanize_timedelta(seconds=grace)

                    ignored_text = ""
                    async with self.settings.channel(channel).ignored_roles() as ignored_roles:
                        for role_id in ignored_roles:
                            guild: discord.Guild = ctx.guild
                            role: discord.Role = guild.get_role(role_id)
                            if role:
                                if not ignored_text == "":
                                    ignored_text += ", "
                                ignored_text += role.mention
                    async with self.settings.channel(channel).ignored() as ignored:
                        for member_id in ignored:
                            member: discord.Member = self.bot.get_user(member_id)
                            if member:
                                if not ignored_text == "":
                                    ignored_text += ", "
                                ignored_text += member.mention

                    if ignored_text:
                        description += "\nIgnoring: " + ignored_text

                    muted_text = ""
                    async with self.settings.channel(channel).muted() as muted:
                        mutedCount = len(muted)
                        for member_id in muted:
                            member: discord.Member = self.bot.get_user(member_id)
                            if member:
                                if len(description) + len(muted_text) < 1975:
                                    mutedCount = mutedCount - 1
                                    if not muted_text == "":
                                        muted_text += ", "
                                    muted_text += member.mention
                                else:
                                    muted_text += "+{:,} more".format(mutedCount)
                                    break

                    if muted_text:
                        description += "\nMuted: " + muted_text

                    embed.description = description

                    await ctx.send(embed=embed)

    @daily.command()
    @commands.guild_only()
    async def add(self, ctx: commands.Context, channel: discord.TextChannel, grace_seconds: int = 0):
        """Add channel to daily reset."""
        async with self.settings.guild(ctx.guild).channels() as channels:
            if not channels.__contains__(channel.id):
                channels.append(channel.id)
                await ctx.send("{channel} will now reset daily.".format(channel=channel.mention))
            else:
                await ctx.send("{channel} is already reset daily.".format(channel=channel.mention))

        await self.settings.channel(channel).grace.set(grace_seconds)

    @daily.command()
    @commands.guild_only()
    async def remove(self, ctx: commands.Context, channel: discord.TextChannel):
        """Remove channel from daily reset."""
        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                channels.remove(channel.id)
                await ctx.send("{channel} will no longer reset daily.".format(channel=channel.mention))
            else:
                await ctx.send("{channel} is not being reset daily.".format(channel=channel.mention))

    @daily.command()
    @commands.guild_only()
    async def grace(self, ctx: commands.Context, grace_seconds: int, channel: discord.TextChannel = None):
        """Set channel grace timer."""
        if not channel:
            channel = ctx.channel

        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                await self.settings.channel(channel).grace.set(grace_seconds)
            else:
                await ctx.send("{channel} is not a daily reset channel.".format(channel=channel.mention))

    @daily.command()
    @commands.guild_only()
    async def mute(self, ctx: commands.Context, user: discord.Member, channel: discord.TextChannel = None):
        """Member will be muted indefinitely."""
        if not channel:
            channel = ctx.channel

        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                async with self.settings.channel(channel).muted() as muted:
                    if not muted.__contains__(user.id):
                        muted.append(user.id)
                        await ctx.send("{user} will not reset daily in {channel}.".format(
                            user=user.display_name,
                            channel=channel.mention)
                        )
            else:
                await ctx.send("{channel} is not a daily reset channel.".format(channel=channel.mention))

    @daily.command()
    @commands.guild_only()
    async def unmute(self, ctx: commands.Context, user: discord.Member, channel: discord.TextChannel = None):
        """Member will be able to chat again at the daily reset."""
        if not channel:
            channel = ctx.channel

        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                async with self.settings.channel(channel).muted() as muted:
                    if muted.__contains__(user.id):
                        muted.remove(user.id)
                        await ctx.send("{user} will reset daily in {channel}.".format(
                            user=user.display_name,
                            channel=channel.mention)
                        )
            else:
                await ctx.send("{channel} is not a daily reset channel.".format(channel=channel.mention))

    @daily.command()
    @commands.guild_only()
    async def ignore(self, ctx: commands.Context, user: discord.Member, channel: discord.TextChannel = None):
        """Member will be able to talk without being restricted."""
        if not channel:
            channel = ctx.channel

        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                async with self.settings.channel(channel).ignored() as ignored:
                    if not ignored.__contains__(user.id):
                        ignored.append(user.id)
                        await ctx.send("{user} will not reset daily in {channel}.".format(
                            user=user.display_name,
                            channel=channel.mention)
                        )
            else:
                await ctx.send("{channel} is not a daily reset channel.".format(channel=channel.mention))

    @daily.command()
    @commands.guild_only()
    async def unignore(self, ctx: commands.Context, user: discord.Member, channel: discord.TextChannel = None):
        """Member will be removed from the un-restricted list."""
        if not channel:
            channel = ctx.channel

        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                async with self.settings.channel(channel).ignored() as ignored:
                    if ignored.__contains__(user.id):
                        ignored.remove(user.id)
                        await ctx.send("{user} will reset daily in {channel}.".format(
                            user=user.display_name,
                            channel=channel.mention)
                        )
            else:
                await ctx.send("{channel} is not a daily reset channel.".format(channel=channel.mention))

    @daily.command()
    @commands.guild_only()
    async def ignorerole(self, ctx: commands.Context, role: discord.Role, channel: discord.TextChannel = None):
        """Member will be able to talk without being restricted."""
        if not channel:
            channel = ctx.channel

        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                async with self.settings.channel(channel).ignored_roles() as ignored_roles:
                    if not ignored_roles.__contains__(role.id):
                        ignored_roles.append(role.id)
                        await ctx.send("{role} role will not reset daily in {channel}.".format(
                            role=role.name,
                            channel=channel.mention)
                        )
            else:
                await ctx.send("{channel} is not a daily reset channel.".format(channel=channel.mention))

    @daily.command()
    @commands.guild_only()
    async def unignorerole(self, ctx: commands.Context, role: discord.Role, channel: discord.TextChannel = None):
        """Member will be removed from the un-restricted list."""
        if not channel:
            channel = ctx.channel

        async with self.settings.guild(ctx.guild).channels() as channels:
            if channels.__contains__(channel.id):
                async with self.settings.channel(channel).ignored_roles() as ignored_roles:
                    if ignored_roles.__contains__(role.id):
                        ignored_roles.remove(role.id)
                        await ctx.send("{role} role will reset daily in {channel}.".format(
                            role=role.name,
                            channel=channel.mention)
                        )
            else:
                await ctx.send("{channel} is not a daily reset channel.".format(channel=channel.mention))

    async def is_daily_channel(self, guild: discord.Guild, channel: discord.TextChannel):
        async with self.settings.guild(guild).channels() as channels:
            if channels.__contains__(channel.id):
                return True
        return False

    async def is_ignored_member(self, channel: discord.TextChannel, member: discord.Member):
        async with self.settings.channel(channel).ignored() as ignored:
            if ignored.__contains__(member.id):
                return True
        async with self.settings.channel(channel).ignored_roles() as ignored_roles:
            for role in member.roles:
                if ignored_roles.__contains__(role.id):
                    return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        guild: discord.Guild = message.guild
        channel: discord.TextChannel = message.channel
        member: discord.Member = message.author

        if guild is None:
            return

        if member == self.bot.user:
            return

        if await self.is_daily_channel(guild, channel) and not await self.is_ignored_member(channel, member):
            grace = await self.settings.channel(channel).grace()
            await asyncio.sleep(grace)
            await channel.set_permissions(member, overwrite=discord.PermissionOverwrite(send_messages=False))
