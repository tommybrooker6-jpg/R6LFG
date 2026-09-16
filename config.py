"""
Central configuration & static data for the R6 LFG bot.
Edit BOT_TOKEN via environment variable, never hardcode it.
"""
import os

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# ---- Static option data -----------------------------------------------

REGIONS = ["EU", "NA EAST", "NA WEST", "AFRICA", "AUS", "SA", "ASIA"]

RANKS = [
    "Copper", "Bronze", "Silver", "Gold",
    "Platinum", "Emerald", "Diamond", "Champion",
]

RANK_EMOJI = {
    "Copper": "🟫",
    "Bronze": "🟤",
    "Silver": "⚪",
    "Gold": "🟡",
    "Platinum": "🔵",
    "Emerald": "🟢",
    "Diamond": "💎",
    "Champion": "🏆",
}

# ---- Behaviour defaults -------------------------------------------------

DEFAULT_MAX_SIZE = 5
MIN_GROUP_SIZE = 2
MAX_GROUP_SIZE = 5

DEFAULT_AUTO_LEAVE_MINUTES = 30   # 0 = disabled
MIN_AUTO_LEAVE_MINUTES = 5
MAX_AUTO_LEAVE_MINUTES = 240

# ---- Channel / category naming ------------------------------------------

CATEGORY_NAME = "R6 LFG"
LFG_TEXT_CHANNEL_NAME = "looking-for-group"

# Discord embed color (Siege-ish dark red/orange)
EMBED_COLOR = 0xE0122A
EMBED_COLOR_FULL = 0x555555
EMBED_COLOR_SUCCESS = 0x2ECC71

DB_PATH = os.getenv("LFG_DB_PATH", "lfg_bot.sqlite3")
