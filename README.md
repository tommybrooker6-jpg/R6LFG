# R6 Siege LFG Bot

A Discord bot for Memories LA (or any server) that runs a self-contained
"Looking For Group" system for Rainbow Six Siege, entirely through buttons,
dropdowns, and popups — no typed commands needed for members.

## What it does

- **One category, one text channel.** `/lfg-setup` creates an `R6 LFG`
  category with a `#looking-for-group` channel. Members can't type in that
  channel — they can only click buttons on the control panel embed.
- **Control panel embed** with three buttons:
  - **Create Group** → dropdowns for Region (EU, NA EAST, NA WEST, AFRICA,
    AUS, SA, ASIA) and Rank (Copper → Champion), then a popup for max group
    size (2-5, custom) and an optional note.
  - **Edit Group** → owner-only. Only works if you currently own a group.
    Lets you change region/rank, or close the group entirely.
  - **Settings** → auto-leave timer (custom minutes, or off), and
    auto-rank/auto-region defaults that pre-fill the Create Group dropdowns.
- **Live group listings.** Each open group posts its own embed in the LFG
  channel (title like `💎 R6 EU DIAMOND`), with Join/Leave/Create Voice
  Channel buttons and a live member count. The embed updates in place as
  people join/leave.
- **Private group threads.** Creating a group spins up a private thread
  visible only to members who've joined. It's auto-deleted when the group
  closes.
- **On-demand voice channels.** The group owner can spawn a voice channel
  (in the same LFG category) once people have joined. It's pre-named from
  the group's settings, e.g. `R6 EU CHAMP`, limited to the group's max size,
  and only joinable by group members. It's auto-deleted when the group
  closes or the owner leaves.
- **Auto-leave / cleanup.** A background loop closes groups that have been
  inactive past the configured timer, deleting their listing, thread, and
  voice channel together. Groups also auto-close if the owner leaves the
  server, or if the owner leaves the group manually.

## Setup

1. **Create the bot application** at https://discord.com/developers/applications
   - Under **Bot**, enable the **Server Members Intent**.
   - Under **OAuth2 → URL Generator**, select scopes `bot` and
     `applications.commands`, and permissions: Manage Channels, Manage
     Threads, Send Messages, Embed Links, Create Private Threads, Connect,
     Move Members (optional). Use the generated URL to invite the bot.

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set your token**
   ```bash
   cp .env.example .env
   # edit .env and paste your bot token
   export $(cat .env | xargs)   # or use python-dotenv / your process manager
   ```

4. **Run the bot**
   ```bash
   python bot.py
   ```

5. **In your Discord server**, run the slash command:
   ```
   /lfg-setup
   ```
   (Requires Manage Server permission.) This creates the category, channel,
   and posts the control panel. Re-running it is safe — it reuses the
   existing category/channel if found.

## Project structure

```
bot.py               entrypoint, loads the cog, syncs slash commands
config.py            regions, ranks, colors, size/timer limits — edit freely
utils/db.py          SQLite persistence (guild settings, groups, members)
utils/embeds.py      embed builders (control panel, group listing)
cogs/components.py   Select menus, Modals (popups), Views (buttons)
cogs/lfg.py          all business logic: create/edit/join/leave/voice/cleanup
```

## Customizing

- **Ranks/regions:** edit `REGIONS` / `RANKS` in `config.py`.
- **Group size limits:** `MIN_GROUP_SIZE` / `MAX_GROUP_SIZE` in `config.py`.
- **Default auto-leave time:** `DEFAULT_AUTO_LEAVE_MINUTES` in `config.py`.
- **Colors/branding:** `EMBED_COLOR*` in `config.py`, and the footer text in
  `utils/embeds.py`.

## Notes on scaling

The bot currently syncs slash commands globally on startup
(`await self.tree.sync()` in `bot.py`). If you're only testing in one
server, switch to a guild-scoped sync for instant updates:

```python
guild = discord.Object(id=YOUR_GUILD_ID)
self.tree.copy_global_to(guild=guild)
await self.tree.sync(guild=guild)
```

Global command updates can take up to an hour to propagate.
