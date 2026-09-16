import discord
from config import EMBED_COLOR, EMBED_COLOR_FULL, EMBED_COLOR_SUCCESS, RANK_EMOJI


def control_panel_embed() -> discord.Embed:
    e = discord.Embed(
        title="🎮 R6 Siege — Looking For Group",
        description=(
            "Use the buttons below to manage LFG groups.\n\n"
            "**Create Group** — open a new group listing (region, rank, size)\n"
            "**Edit Group** — owners only: change your group's settings\n"
            "**Settings** — configure auto-leave timer, auto-rank, auto-region"
        ),
        color=EMBED_COLOR,
    )
    e.set_footer(text="Memories LA • R6 LFG")
    return e


def group_listing_embed(group, members: list[discord.Member], guild: discord.Guild) -> discord.Embed:
    is_full = len(members) >= group.max_size
    color = EMBED_COLOR_FULL if (is_full or group.status == "full") else EMBED_COLOR
    emoji = RANK_EMOJI.get(group.rank, "")

    owner_mention = f"<@{group.owner_id}>"
    member_lines = "\n".join(f"• <@{uid}>" for uid in [m.id for m in members]) or "—"

    e = discord.Embed(
        title=f"{emoji} R6 {group.region} {group.rank.upper()}",
        color=color,
    )
    e.add_field(name="Owner", value=owner_mention, inline=True)
    e.add_field(name="Region", value=group.region, inline=True)
    e.add_field(name="Rank", value=f"{emoji} {group.rank}", inline=True)
    e.add_field(name="Players", value=f"{len(members)}/{group.max_size}", inline=True)
    if group.note:
        e.add_field(name="Note", value=group.note, inline=False)
    e.add_field(name="Members", value=member_lines, inline=False)

    status_text = "🟢 Open" if not is_full and group.status == "open" else "🔴 Full"
    e.set_footer(text=f"{status_text} • Group #{group.id}")
    return e


def group_announcement_embed(group, member_count: int = 1) -> discord.Embed:
    """Short one-liner posted in the public LFG channel; full details live in the thread."""
    emoji = RANK_EMOJI.get(group.rank, "")
    owner_mention = f"<@{group.owner_id}>"
    is_full = member_count >= group.max_size or group.status == "full"
    color = EMBED_COLOR_FULL if is_full else EMBED_COLOR

    e = discord.Embed(
        description=f"{emoji} {owner_mention} created an **R6 {group.region} {group.rank.upper()}** group.",
        color=color,
    )
    footer = "🔴 Full" if is_full else f"🟢 {member_count}/{group.max_size} • Click Join to get access to the group thread"
    e.set_footer(text=f"Group #{group.id} • {footer}")
    return e


def voice_channel_name(group) -> str:
    """e.g. 'EU CHAMPION'"""
    return f"{group.region} {group.rank.upper()}"[:100]


def ubisoft_checklist_embed(group, members_with_names: list[tuple]) -> discord.Embed:
    """members_with_names: list of (discord.Member, ubisoft_name_or_None)."""
    lines = []
    submitted = 0
    for member, name in members_with_names:
        if name:
            lines.append(f"✅ {member.mention} — `{name}`")
            submitted += 1
        else:
            lines.append(f"❌ {member.mention} — *not submitted*")

    e = discord.Embed(
        title="🎮 Ubisoft Connect Check-In",
        description=(
            "Voice channel is up! Everyone needs to submit their **Ubisoft Connect name** "
            "so the group can add each other and get into the match.\n\n" + "\n".join(lines)
        ),
        color=EMBED_COLOR if submitted < len(members_with_names) else EMBED_COLOR_SUCCESS,
    )
    e.set_footer(text=f"{submitted}/{len(members_with_names)} submitted • Group #{group.id}")
    return e
