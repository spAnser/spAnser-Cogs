# Standard Library
from collections import defaultdict, deque
from datetime import datetime
from enum import Enum
import random

from pprint import pprint

# Discord / Red Bot
from discord.ext import commands
from cogs.utils.dataIO import dataIO

NUM_ENC = "\N{COMBINING ENCLOSING KEYCAP}"

default_settings = {"PAYDAY_TIME": 300, "PAYDAY_CREDITS": 120,
                    "SLOT_MIN": 5, "SLOT_MAX": 100, "SLOT_TIME": 0,
                    "REGISTER_CREDITS": 0}


class EconomyError(Exception):
    pass


class OnCooldown(EconomyError):
    pass


class InvalidBid(EconomyError):
    pass


class BankError(Exception):
    pass


class NoAccount(BankError):
    pass


class InsufficientBalance(BankError):
    pass


class SMReel(Enum):
    cherries  = "\N{CHERRIES}"
    cookie    = "\N{COOKIE}"
    two       = "\N{DIGIT TWO}" + NUM_ENC
    flc       = "\N{FOUR LEAF CLOVER}"
    cyclone   = "\N{CYCLONE}"
    sunflower = "\N{SUNFLOWER}"
    six       = "\N{DIGIT SIX}" + NUM_ENC
    mushroom  = "\N{MUSHROOM}"
    heart     = "\N{HEAVY BLACK HEART}"
    snowflake = "\N{SNOWFLAKE}"

PAYOUTS = {
    (SMReel.two, SMReel.two, SMReel.six) : {
        "payout" : lambda x: x * 100 + x,
        "phrase" : "JACKPOT! 226! Your bid has been multiplied * 100!"
    },
    (SMReel.flc, SMReel.flc, SMReel.flc) : {
        "payout" : lambda x: x * 10 + x,
        "phrase" : "4LC! Your bid has been multiplied * 10!"
    },
    (SMReel.cherries, SMReel.cherries, SMReel.cherries) : {
        "payout" : lambda x: x * 8 + x,
        "phrase" : "Three cherries! Your bid has been multiplied * 8!"
    },
    (SMReel.two, SMReel.six) : {
        "payout" : lambda x: x * 4 + x,
        "phrase" : "2 6! Your bid has been multiplied * 4!"
    },
    (SMReel.cherries, SMReel.cherries) : {
        "payout" : lambda x: x * 3 + x,
        "phrase" : "Two cherries! Your bid has been multiplied * 3!"
    },
    "3 symbols" : {
        "payout" : lambda x: x * 6 + x,
        "phrase" : "Three symbols!  Your bid has been multiplied * 6!"
    },
    "2 symbols" : {
        "payout" : lambda x: x * 2 + x,
        "phrase" : "Two consecutive symbols! Your bid has been multiplied * 2!"
    },
}

SLOT_PAYOUTS_MSG = ("Slot machine payouts:\n\n"
                    "{two.value} {two.value} {six.value} Bet * 100\n\n"
                    "{flc.value} {flc.value} {flc.value} Bet * 10\n\n"
                    "{cherries.value} {cherries.value} {cherries.value} Bet * 8\n\n"
                    "{two.value} {six.value} Bet * 4\n\n"
                    "{cherries.value} {cherries.value} Bet * 3\n\n"
                    "Three symbols: Bet * 6\n"
                    "Two symbols: Bet * 2".format(**SMReel.__dict__))

class SlotMachine:
    """SlotMachines

    A replacement for the built in economy slot machines!"""

    def __init__(self, bot):
        global default_settings
        self.bot = bot
        econ = self.bot.get_cog('Economy')
        self.bank = econ.bank
        self.file_path = "data/economy/settings.json"
        self.settings = dataIO.load_json(self.file_path)
        if "PAYDAY_TIME" in self.settings:  # old format
            default_settings = self.settings
            self.settings = {}
        self.settings = defaultdict(default_settings.copy, self.settings)
        self.slot_register = defaultdict(dict)

    @commands.command()
    async def slotpayouts(self):
        """Shows slot machine payouts"""
        await self.bot.whisper(SLOT_PAYOUTS_MSG)

    @commands.command(pass_context=True, no_pm=True)
    async def pull(self, ctx, bid: int):
        """Reload slot settings"""
        global default_settings
        self.settings = dataIO.load_json(self.file_path)
        if "PAYDAY_TIME" in self.settings:  # old format
            default_settings = self.settings
            self.settings = {}
        self.settings = defaultdict(default_settings.copy, self.settings)

        """Play the slot machine"""
        author = ctx.message.author
        server = author.server
        settings = self.settings[server.id]
        valid_bid = settings["SLOT_MIN"] <= bid and bid <= settings["SLOT_MAX"]
        slot_time = settings["SLOT_TIME"]
        last_slot = self.slot_register.get(author.id)
        now = datetime.utcnow()
        try:
            if not self.bank.account_exists(author):
                raise NoAccount
            if last_slot:
                if (now - last_slot).seconds < slot_time:
                    raise OnCooldown()
            if not valid_bid:
                raise InvalidBid()
            if not self.bank.can_spend(author, bid):
                raise InsufficientBalance
            await self.slot_machine(author, bid)
        except NoAccount:
            await self.bot.say("{} You need an account to use the slot "
                               "machine. Type `{}bank register` to open one."
                               "".format(author.mention, ctx.prefix))
        except InsufficientBalance:
            await self.bot.say("{} You need an account with enough funds to "
                               "play the slot machine.".format(author.mention))
        except OnCooldown:
            await self.bot.say("Slot machine is still cooling off! Wait {} "
                               "seconds between each pull".format(slot_time))
        except InvalidBid:
            await self.bot.say("Bid must be between {} and {}."
                               "".format(settings["SLOT_MIN"],
                                         settings["SLOT_MAX"]))

    async def slot_machine(self, author, bid):
        default_reel = deque(SMReel)
        reels = []
        self.slot_register[author.id] = datetime.utcnow()
        for i in range(3):
            default_reel.rotate(random.randint(-999, 999)) # weeeeee
            new_reel = deque(default_reel, maxlen=3) # we need only 3 symbols
            reels.append(new_reel)                   # for each reel
        rows = ((reels[0][0], reels[1][0], reels[2][0]),
                (reels[0][1], reels[1][1], reels[2][1]),
                (reels[0][2], reels[1][2], reels[2][2]))

        slot = "~~\n~~" # Mobile friendly
        for i, row in enumerate(rows): # Let's build the slot to show
            sign = "  "
            if i == 1:
                sign = ">"
            slot += "{}{} {} {}\n".format(sign, *[c.value for c in row])

        payout = PAYOUTS.get(rows[1])
        if not payout:
            # Checks for two-consecutive-symbols special rewards
            payout = PAYOUTS.get((rows[1][0], rows[1][1]),
                     PAYOUTS.get((rows[1][1], rows[1][2]))
                                )
        if not payout:
            # Still nothing. Let's check for 3 generic same symbols
            # or 2 consecutive symbols
            has_three = rows[1][0] == rows[1][1] == rows[1][2]
            has_two = (rows[1][0] == rows[1][1]) or (rows[1][1] == rows[1][2])
            if has_three:
                payout = PAYOUTS["3 symbols"]
            elif has_two:
                payout = PAYOUTS["2 symbols"]

        if payout:
            then = self.bank.get_balance(author)
            pay = payout["payout"](bid)
            now = then - bid + pay
            self.bank.set_credits(author, now)
            await self.bot.say("{}\n{} {}\n\nYour bid: {}\n{} → {}!"
                               "".format(slot, author.mention,
                                         payout["phrase"], bid, then, now))
        else:
            then = self.bank.get_balance(author)
            self.bank.withdraw_credits(author, bid)
            now = then - bid
            await self.bot.say("{}\n{} Nothing!\nYour bid: {}\n{} → {}!"
                               "".format(slot, author.mention, bid, then, now))

def setup(bot):
    bot.add_cog(SlotMachine(bot))