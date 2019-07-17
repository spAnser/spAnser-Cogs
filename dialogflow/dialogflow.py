# Standard Library
from collections import defaultdict, deque
import os
import time

# Discord / Red Bot
import discord
from __main__ import send_cmd_help
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from cogs.utils import checks


# DialogFlow
from google.oauth2 import service_account
import dialogflow_v2


default_settings = {}
default_status = {}

settings_path = 'data/dialogflow/settings.json'
status_path = 'data/dialogflow/status.json'


class DialogFlow:
    """dialogflow

    Mute users after posting and reset once a day."""

    def __init__(self, bot):
        global default_settings
        self.bot = bot
        self.sessions = {}
        self.sessions_server = {}
        self.session_ids = []
        self.sessions_awaiting_input = []
        # Load settings
        settings = dataIO.load_json(settings_path)
        self.settings = defaultdict(lambda: default_settings.copy(), settings)
        # Load status
        status = dataIO.load_json(status_path)
        self.status = defaultdict(lambda: default_status.copy(), status)

        credentials = service_account.Credentials.from_service_account_file('data/dialogflow/' + self.settings['service_credentials'])
        self.client = dialogflow_v2.SessionsClient(credentials=credentials)

    def __unload(self):
        pass

    def get_role_from_name(self, roles, role_name):
        for role in roles:
            if role.name == role_name:
                return role
        return None

    async def process_response(self, member, response, respond=True):
        try:
            for context in response.query_result.output_contexts:
                try:
                    # Lifespan of conversation is over remove session_id for bot to retrigger conversation again from status.
                    if context.lifespan_count <= 1:
                        self.session_ids.remove(member.id)
                except:
                    pass
        except:
            pass
        for message in response.query_result.fulfillment_messages:
            for key in message.payload:
                if key == 'actions':
                    for action in message.payload[key]:
                        await self.do_action(action, member, respond)

    async def do_action(self, action, member, respond=True):
        try:
            serverId = self.status[member.id]['server']
            channel = discord.Object(id=self.settings[serverId]['log_channel'])
        except:
            channel = None
        if action['action'] == 'inquire':
            await self.action_inquire(member, action['inquiry'])
        elif action['action'] == 'message':
            if respond:
                await self.action_message(member, action['message'])
        elif action['action'] == 'question':
            if respond:
                await self.action_message(member, action['message'])
            self.sessions_awaiting_input.append(member.id)
        elif action['action'] == 'kick':
            if respond:
                await self.action_message(member, action['message'])
            await self.action_kick(member)
            self.sessions.pop(member.id, None)
            self.sessions_server.pop(member.id, None)
            if member.id in self.session_ids:
                self.session_ids.remove(member.id)
            self.status.pop(member.id, None)
            dataIO.save_json(status_path, self.status)
            if channel:
                await self.bot.send_message(channel, "Dialogflow: Kicked {} ({}).".format(member.mention, member.id))
        elif action['action'] == 'add_role':
            await self.action_add_role(member, action['role'])
            if channel:
                await self.bot.send_message(channel, "Dialogflow: Added {} role to {} ({}).".format(action['role'], member.mention, member.id))
        elif action['action'] == 'try_again':
            if respond:
                await self.action_message(member, self.settings['try_again_message'])
            self.sessions_awaiting_input.append(member.id)
        elif action['action'] == 'finished':
            if respond:
                await self.action_message(member, self.settings['welcome_message'])
            self.sessions.pop(member.id, None)
            self.sessions_server.pop(member.id, None)
            if member.id in self.session_ids:
                self.session_ids.remove(member.id)
            self.status.pop(member.id, None)
            dataIO.save_json(status_path, self.status)
        else:
            print('Unknown action: ' + action['action'])

    async def action_inquire(self, member, inquiry, respond=True):
        self.status[member.id] = {
            'inquiry': inquiry,
            'server': self.sessions_server[member.id]
        }
        dataIO.save_json(status_path, self.status)
        text_input = dialogflow_v2.types.TextInput(text=inquiry, language_code='en')
        query_input = dialogflow_v2.types.QueryInput(text=text_input)
        response = self.client.detect_intent(self.sessions[member.id], query_input)
        await self.process_response(member, response, respond)

    async def action_message(self, member, message):
        try:
            await self.bot.send_message(member, message)
        except:
            print("dialogflow.py: unable to whisper {}. Probably doesn't want to be PM'd".format(member))

    async def action_kick(self, member):
        member = self.bot.get_server(self.sessions_server[member.id]).get_member(member.id)
        await self.bot.kick(member)

    async def action_add_role(self, member, role_name):
        server = self.bot.get_server(self.sessions_server[member.id])
        member = server.get_member(member.id)
        role = self.get_role_from_name(server.roles, role_name)
        if role:
            await self.bot.add_roles(member, role)

    async def on_member_join(self, member):
        if 'on_member_join' in self.settings:
            self.sessions[member.id] = self.client.session_path(self.settings['project_id'], member.id)
            self.sessions_server[member.id] = member.server.id
            self.session_ids.append(member.id)
            for action in self.settings['on_member_join']['actions']:
                await self.do_action(action, member)

    async def on_message(self, message: discord.Message):
        channel = message.channel
        if channel.is_private:
            if message.author.id not in self.session_ids and message.author.id in self.status:
                self.sessions[message.author.id] = self.client.session_path(self.settings['project_id'], message.author.id)
                self.sessions_server[message.author.id] = self.status[message.author.id]['server']
                self.session_ids.append(message.author.id)
                await self.action_inquire(message.author, self.status[message.author.id]['inquiry'], False)
                time.sleep(0.375)
            if message.author.id in self.session_ids and message.author.id in self.sessions_awaiting_input:
                self.sessions_awaiting_input.remove(message.author.id)
                text_input = dialogflow_v2.types.TextInput(text=message.content, language_code='en')
                query_input = dialogflow_v2.types.QueryInput(text=text_input)
                response = self.client.detect_intent(self.sessions[message.author.id], query_input)
                await self.process_response(message.author, response)
            elif message.author.id not in self.session_ids:
                if 'on_message' in self.settings and message.content in self.settings['on_message']:
                    self.sessions[message.author.id] = self.client.session_path(self.settings['project_id'], message.author.id)
                    self.sessions_server[message.author.id] = self.settings['server_if_unknown']
                    self.session_ids.append(message.author.id)
                    await self.action_inquire(message.author, message.content)

def check_folders():
    if not os.path.exists("data/dialogflow"):
        print("Creating data/dialogflow folder...")
        os.makedirs("data/dialogflow")


def check_files():
    if not dataIO.is_valid_json(settings_path):
        print("Creating default dialogflow's settings.json...")
        dataIO.save_json(settings_path, {})

    if not dataIO.is_valid_json(status_path):
        print("Creating default dialogflow's status.json...")
        dataIO.save_json(status_path, {})


def setup(bot):
    global logger
    check_folders()
    check_files()
    cog = DialogFlow(bot)
    bot.add_cog(cog)
