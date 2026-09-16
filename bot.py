import asyncio
import logging

import discord
from discord.ext import commands

from config import BOT_TOKEN
from utils.db import Database

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("r6-lfg-bot")

INTENTS = discord.Intents.default()
INTENTS.members = True          # needed for on_member_remove + role/member lookups
INTENTS.message_content = False # not needed, everything is button/modal driven


class LFGBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db = Database()

    async def setup_hook(self):
        await self.db.connect()
        await self.load_extension("cogs.lfg")
        # Sync slash commands (guild-specific sync is faster while testing;
        # switch to global sync for production across many servers).
        await self.tree.sync()

    async def close(self):
        await self.db.close()
        await super().close()


bot = LFGBot()


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    log.info("Run /lfg-setup in a server to install the LFG panel.")


async def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "No bot token found. Set the DISCORD_BOT_TOKEN environment variable."
        )
    async with bot:
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
