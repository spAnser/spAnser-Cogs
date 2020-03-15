from redbot.core.bot import Red
from .daily import Daily


async def setup(bot: Red):
    cog = Daily(bot)
    bot.add_cog(cog)
    await cog.initialize()
