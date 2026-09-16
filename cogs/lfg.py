import discord
from discord import app_commands
from discord.ext import commands, tasks
import time

from config import (
    CATEGORY_NAME, LFG_TEXT_CHANNEL_NAME, EMBED_COLOR,
    DEFAULT_MAX_SIZE,
)
from utils.embeds import (
    control_panel_embed, group_listing_embed, group_announcement_embed,
    voice_channel_name, ubisoft_checklist_embed,
)
from cogs.components import (
    CreateGroupView, EditGroupView, SettingsView, GroupAnnouncementView, GroupThreadView,
    UbisoftCheckinView,
)


class ControlPanelView(discord.ui.View):
    """Persistent view for the main LFG control panel embed."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.create_button.custom_id = "lfg:panel:create"
        self.edit_button.custom_id = "lfg:panel:edit"
        self.settings_button.custom_id = "lfg:panel:settings"

    @discord.ui.button(label="Create Group", style=discord.ButtonStyle.success, emoji="🆕")
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.start_create_group(interaction)

    @discord.ui.button(label="Edit Group", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.start_edit_group(interaction)

    @discord.ui.button(label="Settings", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def settings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.open_settings(interaction)


class LFGCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.auto_leave_check.start()

    def cog_unload(self):
        self.auto_leave_check.cancel()

    # ---------------------------------------------------------------
    # Setup command
    # ---------------------------------------------------------------

    @app_commands.command(name="lfg-setup", description="Create/repost the R6 LFG category, channel and control panel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lfg_setup(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        settings = await self.db.get_settings(guild.id)

        category = guild.get_channel(settings.category_id) if settings.category_id else None
        if category is None:
            category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(CATEGORY_NAME)

        channel = guild.get_channel(settings.lfg_channel_id) if settings.lfg_channel_id else None
        if channel is None:
            channel = discord.utils.get(category.text_channels, name=LFG_TEXT_CHANNEL_NAME)
        if channel is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False, read_messages=True, add_reactions=False
                ),
                guild.me: discord.PermissionOverwrite(send_messages=True, manage_messages=True),
            }
            channel = await guild.create_text_channel(
                LFG_TEXT_CHANNEL_NAME, category=category, overwrites=overwrites
            )
        else:
            # Make sure regular members can't type in it — only buttons.
            await channel.set_permissions(guild.default_role, send_messages=False, read_messages=True)

        settings.category_id = category.id
        settings.lfg_channel_id = channel.id
        await self.db.save_settings(settings)

        embed = control_panel_embed()
        await channel.send(embed=embed, view=ControlPanelView(self))

        await interaction.followup.send(
            f"LFG system is set up in {channel.mention}.", ephemeral=True
        )

    # ---------------------------------------------------------------
    # Create Group flow
    # ---------------------------------------------------------------

    async def start_create_group(self, interaction: discord.Interaction):
        existing = await self.db.get_group_by_owner(interaction.guild_id, interaction.user.id)
        if existing:
            await interaction.response.send_message(
                "You already own an active group. Use **Edit Group** or close it first.",
                ephemeral=True,
            )
            return
        already_in = await self.db.get_group_by_member(interaction.guild_id, interaction.user.id)
        if already_in:
            await interaction.response.send_message(
                "You're already in a group. Leave it before creating a new one.",
                ephemeral=True,
            )
            return

        settings = await self.db.get_settings(interaction.guild_id)
        view = CreateGroupView(self, default_region=settings.auto_region, default_rank=settings.auto_rank)
        await interaction.response.send_message(
            "**Create a Group** — choose region & rank, then continue:",
            view=view, ephemeral=True,
        )

    async def finalize_create_group(self, interaction: discord.Interaction, region: str,
                                     rank: str, max_size: int, note: str):
        guild = interaction.guild
        settings = await self.db.get_settings(guild.id)
        channel = guild.get_channel(settings.lfg_channel_id)
        if channel is None:
            await interaction.response.send_message(
                "LFG channel isn't set up yet. Ask an admin to run /lfg-setup.", ephemeral=True
            )
            return

        group = await self.db.create_group(
            guild_id=guild.id, owner_id=interaction.user.id,
            region=region, rank=rank, max_size=max_size, note=note,
        )

        # Post the short public announcement (Join button only) in the LFG channel
        announcement = group_announcement_embed(group)
        msg = await channel.send(embed=announcement, view=GroupAnnouncementView(self, group.id))
        await self.db.update_group_fields(group.id, message_id=msg.id)

        # Create private thread for the group — this is where the full detail card lives
        thread = await channel.create_thread(
            name=f"R6 {region} {rank} — Group #{group.id}",
            type=discord.ChannelType.private_thread,
            invitable=False,
        )
        await self.db.update_group_fields(group.id, thread_id=thread.id)
        await thread.add_user(interaction.user)

        members = [interaction.user]
        detail_embed = group_listing_embed(group, members, guild)
        detail_msg = await thread.send(embed=detail_embed, view=GroupThreadView(self, group.id))
        await self.db.update_group_fields(group.id, thread_message_id=detail_msg.id)

        await interaction.response.send_message(
            f"Group created! Your private thread is {thread.mention}.",
            ephemeral=True,
        )

    # ---------------------------------------------------------------
    # Edit Group flow (owner only)
    # ---------------------------------------------------------------

    async def start_edit_group(self, interaction: discord.Interaction):
        group = await self.db.get_group_by_owner(interaction.guild_id, interaction.user.id)
        if not group:
            await interaction.response.send_message(
                "You don't own an active group. Only group owners can edit.",
                ephemeral=True,
            )
            return
        view = EditGroupView(self, group)
        await interaction.response.send_message(
            f"**Editing Group #{group.id}** — update region/rank or close it:",
            view=view, ephemeral=True,
        )

    async def apply_group_edit(self, interaction: discord.Interaction, group_id: int,
                                region: str, rank: str):
        group = await self.db.get_group(group_id)
        if not group or group.owner_id != interaction.user.id:
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return
        await self.db.update_group_fields(group_id, region=region, rank=rank)
        await self.db.touch_group(group_id)
        await self._refresh_listing(interaction.guild, group_id)
        await interaction.response.edit_message(
            content=f"Group #{group_id} updated to **{region} {rank}**.", view=None
        )

    async def close_group_flow(self, interaction: discord.Interaction, group_id: int):
        group = await self.db.get_group(group_id)
        if not group or group.owner_id != interaction.user.id:
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Closing group...", view=None)
        await self._teardown_group(interaction.guild, group, reason="closed by owner")

    # ---------------------------------------------------------------
    # Join / Leave (buttons on the public listing)
    # ---------------------------------------------------------------

    async def join_group(self, interaction: discord.Interaction, group_id: int):
        group = await self.db.get_group(group_id)
        if not group or group.status != "open":
            await interaction.response.send_message("This group is no longer open.", ephemeral=True)
            return

        already_in = await self.db.get_group_by_member(interaction.guild_id, interaction.user.id)
        if already_in:
            await interaction.response.send_message(
                "You're already in a group. Leave your current group first.", ephemeral=True
            )
            return

        count = await self.db.count_members(group_id)
        if count >= group.max_size:
            await interaction.response.send_message("This group is full.", ephemeral=True)
            return

        await self.db.add_member(group_id, interaction.user.id)
        await self.db.touch_group(group_id)

        guild = interaction.guild
        thread = guild.get_thread(group.thread_id) if group.thread_id else None
        if thread:
            await thread.add_user(interaction.user)
            await thread.send(f"➕ {interaction.user.mention} joined the group.")

        new_count = await self.db.count_members(group_id)
        if new_count >= group.max_size:
            await self.db.update_group_fields(group_id, status="full")

        await self._refresh_listing(guild, group_id)
        await self._refresh_announcement(guild, group_id)
        await interaction.response.send_message(
            f"Joined the group! Head to {thread.mention if thread else 'the group thread'}.",
            ephemeral=True,
        )

    async def leave_group(self, interaction: discord.Interaction, group_id: int):
        group = await self.db.get_group(group_id)
        if not group:
            await interaction.response.send_message("Group not found.", ephemeral=True)
            return

        members = await self.db.get_members(group_id)
        if interaction.user.id not in members:
            await interaction.response.send_message("You're not in this group.", ephemeral=True)
            return

        guild = interaction.guild

        if interaction.user.id == group.owner_id:
            # Owner leaving closes the whole group.
            await interaction.response.send_message(
                "You're the owner — leaving will close the group for everyone.",
                ephemeral=True,
            )
            await self._teardown_group(guild, group, reason="owner left")
            return

        await self.db.remove_member(group_id, interaction.user.id)
        await self.db.touch_group(group_id)
        if group.status == "full":
            await self.db.update_group_fields(group_id, status="open")

        thread = guild.get_thread(group.thread_id) if group.thread_id else None
        if thread:
            try:
                await thread.remove_user(interaction.user)
            except discord.HTTPException:
                pass
            await thread.send(f"➖ {interaction.user.mention} left the group.")

        await self._refresh_listing(guild, group_id)
        await self._refresh_announcement(guild, group_id)
        await interaction.response.send_message("You left the group.", ephemeral=True)

    # ---------------------------------------------------------------
    # Voice channel creation (owner only, from the listing)
    # ---------------------------------------------------------------

    async def create_group_voice(self, interaction: discord.Interaction, group_id: int):
        group = await self.db.get_group(group_id)
        if not group:
            await interaction.response.send_message("Group not found.", ephemeral=True)
            return
        if interaction.user.id != group.owner_id:
            await interaction.response.send_message(
                "Only the group owner can create the voice channel.", ephemeral=True
            )
            return
        if group.voice_channel_id:
            channel = interaction.guild.get_channel(group.voice_channel_id)
            if channel:
                await interaction.response.send_message(
                    f"Voice channel already exists: {channel.mention}", ephemeral=True
                )
                return

        guild = interaction.guild
        settings = await self.db.get_settings(guild.id)
        category = guild.get_channel(settings.category_id)

        members = await self.db.get_members(group_id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
            guild.me: discord.PermissionOverwrite(connect=True, manage_channels=True, view_channel=True),
        }
        for uid in members:
            member = guild.get_member(uid)
            if member:
                overwrites[member] = discord.PermissionOverwrite(connect=True, view_channel=True)

        vc = await guild.create_voice_channel(
            name=voice_channel_name(group),
            category=category,
            overwrites=overwrites,
            user_limit=group.max_size,
        )
        await self.db.update_group_fields(group_id, voice_channel_id=vc.id)
        await self.db.touch_group(group_id)

        thread = guild.get_thread(group.thread_id) if group.thread_id else None
        if thread:
            member_mentions = " ".join(f"<@{uid}>" for uid in members)
            await thread.send(
                f"🔊 Voice channel created: {vc.mention}\n\n"
                f"{member_mentions} — everyone needs to submit their **Ubisoft Connect name** "
                f"below so the group can add each other and get into the match."
            )
            checklist_members = [
                (guild.get_member(uid), name)
                for uid, name in await self.db.get_members_with_ubisoft(group_id)
            ]
            checklist_members = [(m, n) for m, n in checklist_members if m is not None]
            checklist_embed = ubisoft_checklist_embed(group, checklist_members)
            checklist_msg = await thread.send(embed=checklist_embed, view=UbisoftCheckinView(self, group_id))
            await self.db.update_group_fields(group_id, checklist_message_id=checklist_msg.id)

        await interaction.response.send_message(f"Voice channel created: {vc.mention}", ephemeral=True)

    async def submit_ubisoft_name(self, interaction: discord.Interaction, group_id: int, name: str):
        group = await self.db.get_group(group_id)
        if not group:
            await interaction.response.send_message("Group not found.", ephemeral=True)
            return
        members = await self.db.get_members(group_id)
        if interaction.user.id not in members:
            await interaction.response.send_message(
                "You're not a member of this group.", ephemeral=True
            )
            return

        await self.db.set_ubisoft_name(group_id, interaction.user.id, name)
        await self.db.touch_group(group_id)
        await self._refresh_checklist(interaction.guild, group_id)
        await interaction.response.send_message(
            f"Got it — your Ubisoft Connect name is set to **{name}**.", ephemeral=True
        )

    # ---------------------------------------------------------------
    # Settings flow
    # ---------------------------------------------------------------

    async def open_settings(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Only server managers can change LFG settings.", ephemeral=True
            )
            return
        settings = await self.db.get_settings(interaction.guild_id)
        desc = (
            f"**Auto-leave timer:** {settings.auto_leave_minutes} min "
            f"({'disabled' if settings.auto_leave_minutes == 0 else 'enabled'})\n"
            f"**Auto rank default:** {settings.auto_rank or 'none'}\n"
            f"**Auto region default:** {settings.auto_region or 'none'}"
        )
        embed = discord.Embed(title="⚙️ LFG Settings", description=desc, color=EMBED_COLOR)
        await interaction.response.send_message(embed=embed, view=SettingsView(self), ephemeral=True)

    async def save_auto_leave(self, interaction: discord.Interaction, minutes: int):
        settings = await self.db.get_settings(interaction.guild_id)
        settings.auto_leave_minutes = minutes
        await self.db.save_settings(settings)
        label = "disabled" if minutes == 0 else f"{minutes} minutes"
        await interaction.response.send_message(f"Auto-leave timer set to **{label}**.", ephemeral=True)

    async def save_auto_rank_region(self, interaction: discord.Interaction, rank, region):
        settings = await self.db.get_settings(interaction.guild_id)
        settings.auto_rank = rank
        settings.auto_region = region
        await self.db.save_settings(settings)
        await interaction.response.edit_message(
            content=f"Defaults saved — rank: **{rank or 'none'}**, region: **{region or 'none'}**.",
            view=None,
        )

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------

    async def _refresh_listing(self, guild: discord.Guild, group_id: int):
        """Update the full detail embed inside the group's private thread."""
        group = await self.db.get_group(group_id)
        if not group or not group.thread_id or not group.thread_message_id:
            return
        thread = guild.get_thread(group.thread_id)
        if not thread:
            return
        try:
            msg = await thread.fetch_message(group.thread_message_id)
        except discord.NotFound:
            return
        member_ids = await self.db.get_members(group_id)
        members = [guild.get_member(uid) or discord.Object(id=uid) for uid in member_ids]
        members = [m for m in members if isinstance(m, discord.Member)]
        embed = group_listing_embed(group, members, guild)
        await msg.edit(embed=embed, view=GroupThreadView(self, group_id))

    async def _refresh_announcement(self, guild: discord.Guild, group_id: int):
        """Update the short public announcement's footer/color and disable Join if full."""
        group = await self.db.get_group(group_id)
        if not group or not group.message_id:
            return
        settings = await self.db.get_settings(guild.id)
        channel = guild.get_channel(settings.lfg_channel_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(group.message_id)
        except discord.NotFound:
            return
        count = await self.db.count_members(group_id)
        embed = group_announcement_embed(group, member_count=count)
        view = GroupAnnouncementView(self, group_id)
        if count >= group.max_size or group.status == "full":
            view.join_button.disabled = True
            view.join_button.label = "Full"
        await msg.edit(embed=embed, view=view)

    async def _refresh_checklist(self, guild: discord.Guild, group_id: int):
        group = await self.db.get_group(group_id)
        if not group or not group.thread_id or not group.checklist_message_id:
            return
        thread = guild.get_thread(group.thread_id)
        if not thread:
            return
        try:
            msg = await thread.fetch_message(group.checklist_message_id)
        except discord.NotFound:
            return
        checklist_members = [
            (guild.get_member(uid), name)
            for uid, name in await self.db.get_members_with_ubisoft(group_id)
        ]
        checklist_members = [(m, n) for m, n in checklist_members if m is not None]
        embed = ubisoft_checklist_embed(group, checklist_members)
        await msg.edit(embed=embed, view=UbisoftCheckinView(self, group_id))

    async def _teardown_group(self, guild: discord.Guild, group, reason: str = ""):
        """Close a group: remove listing, delete thread, delete voice channel."""
        settings = await self.db.get_settings(guild.id)
        channel = guild.get_channel(settings.lfg_channel_id)

        if channel and group.message_id:
            try:
                msg = await channel.fetch_message(group.message_id)
                await msg.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                pass

        if group.thread_id:
            thread = guild.get_thread(group.thread_id)
            if thread:
                try:
                    await thread.send(f"🔒 Group closed ({reason}). This thread will be deleted.")
                    await thread.delete()
                except discord.HTTPException:
                    pass

        if group.voice_channel_id:
            vc = guild.get_channel(group.voice_channel_id)
            if vc:
                try:
                    await vc.delete(reason=f"LFG group closed: {reason}")
                except discord.HTTPException:
                    pass

        await self.db.close_group(group.id)

    # ---------------------------------------------------------------
    # Background task: auto-leave inactive groups & clean up if owner left server
    # ---------------------------------------------------------------

    @tasks.loop(minutes=2)
    async def auto_leave_check(self):
        for guild in self.bot.guilds:
            settings = await self.db.get_settings(guild.id)
            if settings.auto_leave_minutes <= 0:
                continue
            cutoff = time.time() - settings.auto_leave_minutes * 60
            stale_groups = await self.db.list_stale_groups(cutoff)
            for group in stale_groups:
                if group.guild_id != guild.id:
                    continue
                await self._teardown_group(guild, group, reason="inactivity timeout")

        # Also clean up any group whose owner left the guild/voice-owner check
        # could be extended here if needed.

    @auto_leave_check.before_loop
    async def before_auto_leave_check(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------------
    # Listener: if owner leaves the guild entirely, close their group
    # ---------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        group = await self.db.get_group_by_owner(member.guild.id, member.id)
        if group:
            await self._teardown_group(member.guild, group, reason="owner left the server")


async def setup(bot: commands.Bot):
    cog = LFGCog(bot)
    await bot.add_cog(cog)
    # Register persistent views so buttons keep working after a bot restart.
    bot.add_view(ControlPanelView(cog))
