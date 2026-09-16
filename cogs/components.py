"""
Reusable Select menus and Modals for the LFG system.
Region/Rank are chosen via dropdowns (cleaner than typing on mobile),
group size and note/timer values are chosen via a Modal text input.
"""
import discord
from discord import ui
from config import REGIONS, RANKS, RANK_EMOJI, MIN_GROUP_SIZE, MAX_GROUP_SIZE, \
    MIN_AUTO_LEAVE_MINUTES, MAX_AUTO_LEAVE_MINUTES


class RegionSelect(ui.Select):
    def __init__(self, placeholder="Select region...", default: str | None = None):
        options = [
            discord.SelectOption(label=r, value=r, default=(r == default))
            for r in REGIONS
        ]
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.region = self.values[0]
        for opt in self.options:
            opt.default = (opt.value == self.values[0])
        await interaction.response.edit_message(view=self.view)


class RankSelect(ui.Select):
    def __init__(self, placeholder="Select rank...", default: str | None = None):
        options = [
            discord.SelectOption(label=r, value=r, emoji=RANK_EMOJI.get(r), default=(r == default))
            for r in RANKS
        ]
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.rank = self.values[0]
        for opt in self.options:
            opt.default = (opt.value == self.values[0])
        await interaction.response.edit_message(view=self.view)


class GroupSizeModal(ui.Modal, title="Group Size & Note"):
    size = ui.TextInput(
        label=f"Max players ({MIN_GROUP_SIZE}-{MAX_GROUP_SIZE})",
        placeholder="5",
        default="5",
        max_length=1,
        required=True,
    )
    note = ui.TextInput(
        label="Note (optional)",
        placeholder="e.g. mic required, ranked only",
        required=False,
        max_length=100,
        style=discord.TextStyle.short,
    )

    def __init__(self, on_submit_callback):
        super().__init__()
        self._on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction):
        try:
            size_val = int(str(self.size.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "Group size must be a number.", ephemeral=True
            )
            return
        if not (MIN_GROUP_SIZE <= size_val <= MAX_GROUP_SIZE):
            await interaction.response.send_message(
                f"Group size must be between {MIN_GROUP_SIZE} and {MAX_GROUP_SIZE}.",
                ephemeral=True,
            )
            return
        await self._on_submit_callback(interaction, size_val, str(self.note.value or ""))


class CreateGroupView(ui.View):
    """First step: pick region + rank, then a button opens the size/note modal."""

    def __init__(self, cog, default_region: str | None = None, default_rank: str | None = None,
                 timeout: float = 180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.region = default_region
        self.rank = default_rank
        self.add_item(RegionSelect(default=default_region))
        self.add_item(RankSelect(default=default_rank))

    @ui.button(label="Next: Size & Note", style=discord.ButtonStyle.success, row=2)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.region or not self.rank:
            await interaction.response.send_message(
                "Please select both a region and a rank first.", ephemeral=True
            )
            return

        async def finish(modal_interaction: discord.Interaction, size: int, note: str):
            await self.cog.finalize_create_group(
                modal_interaction, region=self.region, rank=self.rank,
                max_size=size, note=note,
            )

        await interaction.response.send_modal(GroupSizeModal(finish))

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)


class EditGroupView(ui.View):
    """Owner-only editing of an existing group's region/rank."""

    def __init__(self, cog, group, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.group_id = group.id
        self.region = group.region
        self.rank = group.rank
        self.add_item(RegionSelect(default=group.region))
        self.add_item(RankSelect(default=group.rank))

    @ui.button(label="Save Changes", style=discord.ButtonStyle.success, row=2)
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.apply_group_edit(interaction, self.group_id, self.region, self.rank)

    @ui.button(label="Close Group", style=discord.ButtonStyle.danger, row=2)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.close_group_flow(interaction, self.group_id)


class AutoLeaveModal(ui.Modal, title="Auto-Leave Timer"):
    minutes = ui.TextInput(
        label=f"Minutes of inactivity ({MIN_AUTO_LEAVE_MINUTES}-{MAX_AUTO_LEAVE_MINUTES}, 0=off)",
        placeholder="30",
        max_length=3,
        required=True,
    )

    def __init__(self, on_submit_callback):
        super().__init__()
        self._cb = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(str(self.minutes.value).strip())
        except ValueError:
            await interaction.response.send_message("Enter a whole number.", ephemeral=True)
            return
        if val != 0 and not (MIN_AUTO_LEAVE_MINUTES <= val <= MAX_AUTO_LEAVE_MINUTES):
            await interaction.response.send_message(
                f"Must be 0 (off) or between {MIN_AUTO_LEAVE_MINUTES} and {MAX_AUTO_LEAVE_MINUTES}.",
                ephemeral=True,
            )
            return
        await self._cb(interaction, val)


class AutoRankRegionView(ui.View):
    """Settings sub-panel: set default auto-rank / auto-region (or clear)."""

    def __init__(self, cog, current_rank: str | None, current_region: str | None, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.rank = current_rank
        self.region = current_region
        self.add_item(RegionSelect(default=current_region, placeholder="Auto region..."))
        self.add_item(RankSelect(default=current_rank, placeholder="Auto rank..."))

    @ui.button(label="Save", style=discord.ButtonStyle.success, row=2)
    async def save(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.save_auto_rank_region(interaction, self.rank, self.region)

    @ui.button(label="Clear Both", style=discord.ButtonStyle.secondary, row=2)
    async def clear(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.save_auto_rank_region(interaction, None, None)


class SettingsView(ui.View):
    def __init__(self, cog, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.cog = cog

    @ui.button(label="Auto-Leave Timer", style=discord.ButtonStyle.primary, emoji="⏱️")
    async def auto_leave(self, interaction: discord.Interaction, button: ui.Button):
        async def cb(modal_interaction, minutes):
            await self.cog.save_auto_leave(modal_interaction, minutes)
        await interaction.response.send_modal(AutoLeaveModal(cb))

    @ui.button(label="Auto Rank/Region Defaults", style=discord.ButtonStyle.primary, emoji="🎯")
    async def auto_rank_region(self, interaction: discord.Interaction, button: ui.Button):
        settings = await self.cog.bot.db.get_settings(interaction.guild_id)
        view = AutoRankRegionView(self.cog, settings.auto_rank, settings.auto_region)
        await interaction.response.send_message(
            "Set defaults auto-applied when a member creates a group (optional):",
            view=view, ephemeral=True,
        )


class GroupAnnouncementView(ui.View):
    """Persistent view attached to the short announcement posted in the public LFG channel.
    Only a Join button lives here — non-members can't see inside the private thread,
    so this is the only entry point for people who aren't in the group yet."""

    def __init__(self, cog, group_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.group_id = group_id
        self.join_button.custom_id = f"lfg:join:{group_id}"

    @ui.button(label="Join", style=discord.ButtonStyle.success, emoji="➕")
    async def join_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.join_group(interaction, self.group_id)


class GroupThreadView(ui.View):
    """Persistent view attached to the full detail embed inside the group's private thread.
    Only current members can see this thread at all, so Leave/Voice live here."""

    def __init__(self, cog, group_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.group_id = group_id
        self.leave_button.custom_id = f"lfg:threadleave:{group_id}"
        self.voice_button.custom_id = f"lfg:voice:{group_id}"

    @ui.button(label="Leave", style=discord.ButtonStyle.danger, emoji="➖")
    async def leave_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.leave_group(interaction, self.group_id)

    @ui.button(label="Create Voice Channel", style=discord.ButtonStyle.secondary, emoji="🔊")
    async def voice_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.create_group_voice(interaction, self.group_id)
