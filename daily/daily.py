# Standard Library
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import contextlib
import os
import random

# Discord / Red Bot
import discord
from __main__ import send_cmd_help
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from cogs.utils import checks


default_settings = {}


def seconds_until_midnight():
    """Get the number of seconds until midnight."""
    tomorrow = datetime.now() + timedelta(1)
    midnight = datetime(year=tomorrow.year, month=tomorrow.month, 
                        day=tomorrow.day, hour=0, minute=0, second=0)
    return (midnight - datetime.now()).seconds


class Daily:
    """Daily

    Mute users after posting and reset once a day."""

    def __init__(self, bot):
        global default_settings
        self.bot = bot
        self.file_path = "data/daily/settings.json"
        settings = dataIO.load_json("data/daily/settings.json")
        self.settings = defaultdict(lambda: default_settings.copy(), settings)

        self.permision_clearing = asyncio.ensure_future(self.clear_permissions())
        
    def __unload(self):
        # This method is ran whenever the bot unloads this cog.
        self.permision_clearing.cancel()

    # Events
    async def on_message(self, message):
        server = message.server
        channel = message.channel
        author = message.author

        if message.server is None:
            return

        if author == self.bot.user:
            return

        if self.settings[server.id]:
            if channel.id in self.settings[server.id]:
                settings = self.settings[server.id][channel.id]
                if 'ignored' in settings and author.id in settings['ignored']:
                    pass
                else:
                    perms = channel.overwrites_for(author)
                    perms.send_messages = False
                    await self.bot.edit_channel_permissions(channel, author, perms)

    async def clear_permissions(self):
        await self.bot.wait_until_ready()
        with contextlib.suppress(RuntimeError, asyncio.CancelledError):  # Suppress the "Event loop is closed" error
            while self == self.bot.get_cog(self.__class__.__name__):
                await asyncio.sleep(seconds_until_midnight())
                for server_id, channels in self.settings.items():
                    for channel_id, settings in channels.items():
                        channel = self.bot.get_channel(channel_id)

                        member_overwrites = list(filter(lambda o: isinstance(o[0], discord.Member), channel.overwrites))
                        for member_perm in member_overwrites:
                            member = member_perm[0]
                            perms = member_perm[1]
                            if 'muted' in settings and member.id in settings.muted:
                                pass
                            else:
                                perms.send_messages = None
                                if perms.is_empty():
                                    await self.bot.delete_channel_permissions(channel, member)
                                else:
                                    await self.bot.edit_channel_permissions(channel, member, perms)
                            


    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def daily(self, ctx):
        """Changes daily module settings"""
        server = ctx.message.server
        settings = self.settings[server.id]
        if ctx.invoked_subcommand is None:
            msg = "```"
            for k, v in settings.items():
                msg += "{}: {}\n".format(k, v)
            msg += "```"
            await send_cmd_help(ctx)
            await self.bot.say(msg)

    @daily.command(pass_context=True)
    async def add(self, ctx, channel: discord.Channel=None):
        """Add channel to daily reset."""
        server = ctx.message.server
        if not self.settings[server.id]:
            self.settings[server.id] = {}
        if not channel.id in self.settings[server.id]:
            self.settings[server.id][channel.id] = { "ignored":[], "muted":[] }
            await self.bot.say("<#{}> added to daily cooldown.".format(channel.id))
            dataIO.save_json(self.file_path, self.settings)

    @daily.command(pass_context=True)
    async def remove(self, ctx, channel: discord.Channel=None):
        """Remove channel from daily reset."""
        server = ctx.message.server
        if self.settings[server.id]:
            del self.settings[server.id][channel.id]
        await self.bot.say("<#{}> removed from daily cooldown.".format(channel.id))
        dataIO.save_json(self.file_path, self.settings)

    @daily.command(pass_context=True)
    async def mute(self, ctx, channel: discord.Channel=None, member: discord.Member=None):
        """Member will be muted indefinately."""
        server = ctx.message.server
        if self.settings[server.id]:
            if channel.id in self.settings[server.id]:
                settings = self.settings[server.id][channel.id]
                if not 'muted' in settings:
                    self.settings[server.id][channel.id]['muted'] = []

                if member.id not in settings['muted']:
                    self.settings[server.id][channel.id]['muted'].append(member.id)
                    await self.bot.say("<@{}> in <#{}> will not reset daily.".format(member.id, channel.id))
                    dataIO.save_json(self.file_path, self.settings)

    @daily.command(pass_context=True)
    async def unmute(self, ctx, channel: discord.Channel=None, member: discord.Member=None):
        """Member will be able to chat again at the daily reset."""
        server = ctx.message.server
        if self.settings[server.id]:
            if channel.id in self.settings[server.id]:
                settings = self.settings[server.id][channel.id]
                if 'muted' in settings and member.id in settings['muted']:
                    del self.settings[server.id][channel.id]['muted'][settings['muted'].index(member.id)]
                    await self.bot.say("<@{}> in <#{}> will now reset daily.".format(member.id, channel.id))
                    dataIO.save_json(self.file_path, self.settings)

    @daily.command(pass_context=True)
    async def ignore(self, ctx, channel: discord.Channel=None, member: discord.Member=None):
        """Member will be able to talk without being restricted."""
        server = ctx.message.server
        if self.settings[server.id]:
            if channel.id in self.settings[server.id]:
                settings = self.settings[server.id][channel.id]
                if not 'ignored' in settings:
                    self.settings[server.id][channel.id]['ignored'] = []

                if member.id not in settings['ignored']:
                    self.settings[server.id][channel.id]['ignored'].append(member.id)
                    await self.bot.say("<@{}> in <#{}> be ignored.".format(member.id, channel.id))
                    dataIO.save_json(self.file_path, self.settings)

    @daily.command(pass_context=True)
    async def unignore(self, ctx, channel: discord.Channel=None, member: discord.Member=None):
        """Member will be removed from the un-restricted list."""
        server = ctx.message.server
        if self.settings[server.id]:
            if channel.id in self.settings[server.id]:
                settings = self.settings[server.id][channel.id]
                if 'ignored' in settings and member.id in settings['ignored']:
                    del self.settings[server.id][channel.id]['ignored'][settings['ignored'].index(member.id)]
                    await self.bot.say("<@{}> in <#{}> is no longer ignored.".format(member.id, channel.id))
                    dataIO.save_json(self.file_path, self.settings)


def check_folders():
    if not os.path.exists("data/daily"):
        print("Creating data/daily folder...")
        os.makedirs("data/daily")


def check_files():
    f = "data/daily/settings.json"
    if not dataIO.is_valid_json(f):
        print("Creating default daily's settings.json...")
        dataIO.save_json(f, {})


def setup(bot):
    global logger
    check_folders()
    check_files()
    bot.add_cog(Daily(bot))