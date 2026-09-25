"""
Discord presentation embed formatters.

What it does:
- Serializes application DTOs into Discord Embed objects and markdown strings.
- Formats countdowns, progress bars, and timestamps.

What it does NOT do:
- Does NOT execute business logic or domain math.
- Does NOT perform database operations.
"""

from datetime import datetime, timezone
from typing import Tuple, Optional
import discord

from src.application.dtos.task_dtos import TaskResultDTO
from src.application.dtos.deadline_dtos import DeadlineResultDTO
from src.application.dtos.report_dtos import MemberReportDTO, GuildReportDTO
from src.application.dtos.project_dtos import ProjectStatusDTO, ProjectArchiveSummaryDTO
from src.application.services.vault_service import VaultSubmissionResultDTO

COLOR_PRIMARY = discord.Color.from_rgb(88, 101, 242)
COLOR_SUCCESS = discord.Color.from_rgb(87, 242, 135)
COLOR_WARNING = discord.Color.from_rgb(254, 231, 92)
COLOR_DANGER  = discord.Color.from_rgb(237, 66, 69)
COLOR_INFO    = discord.Color.from_rgb(0, 176, 244)

def format_discord_timestamps(dt: datetime) -> Tuple[str, str]:
    """Generates absolute and relative Discord timestamp markdown."""
    epoch = int(dt.timestamp())
    return f"<t:{epoch}:F>", f"<t:{epoch}:R>"

def build_task_embed(dto: TaskResultDTO) -> discord.Embed:
    """Builds a formatted task ledger embed card."""
    abs_ts, rel_ts = format_discord_timestamps(dto.due_date)
    color = COLOR_SUCCESS if dto.is_completed else COLOR_PRIMARY
    title = f"{'✅' if dto.is_completed else '📋'} Task: {dto.task_id}"

    embed = discord.Embed(
        title=title,
        description=f"**{dto.description}**",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 Assignee", value=f"<@{dto.assigned_to}>", inline=True)
    status_text = f"Completed at {dto.completed_at}" if dto.is_completed else "In Progress"
    embed.add_field(name="📌 Status", value=f"`{status_text}`", inline=True)
    embed.add_field(name="⏰ Due Date", value=f"{abs_ts} ({rel_ts})", inline=False)
    footer = "Task completed" if dto.is_completed else f"Mark complete with: /task complete {dto.task_id}"
    embed.set_footer(text=footer)
    return embed

def build_deadline_embed(dto: DeadlineResultDTO) -> discord.Embed:
    """Builds a live countdown embed card for #deadlines channel."""
    abs_ts, rel_ts = format_discord_timestamps(dto.due_datetime)
    now = datetime.now(timezone.utc)
    is_overdue = dto.due_datetime < now

    embed = discord.Embed(
        title=f"🎯 Milestone: {dto.name}",
        color=COLOR_DANGER if is_overdue else COLOR_INFO,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="⏳ Time Remaining", value=f"### {rel_ts}", inline=False)
    embed.add_field(name="📅 Scheduled Due Date", value=abs_ts, inline=True)
    embed.add_field(name="🆔 Milestone ID", value=f"`{dto.deadline_id}`", inline=True)
    embed.set_footer(text="Live countdown • Alert pings at 72h, 24h & 6h")
    return embed

def build_member_report_embed(dto: MemberReportDTO, member: discord.Member) -> discord.Embed:
    """Builds an individual student contribution scorecard embed."""
    embed = discord.Embed(
        title=f"📊 Contribution Scorecard: {member.display_name}",
        description="Anti-free-riding metrics and deliverables breakdown.",
        color=COLOR_PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)

    bar_filled = min(10, max(0, dto.completion_rate // 10))
    bar_str = "🟩" * bar_filled + "⬜" * (10 - bar_filled)

    embed.add_field(
        name="✅ Tasks Completed",
        value=f"**{dto.tasks_completed}** (Pending: {dto.pending_tasks})",
        inline=True
    )
    embed.add_field(name="💬 Messages Sent", value=f"**{dto.message_count}**", inline=True)
    embed.add_field(name="📁 Files Submitted", value=f"**{dto.files_submitted}**", inline=True)
    embed.add_field(
        name="📈 Task Completion Rate",
        value=f"{bar_str} **{dto.completion_rate}%**",
        inline=False
    )
    embed.add_field(
        name="🏆 Contribution Score",
        value=f"**{dto.contribution_score:.1f}** points",
        inline=True
    )
    last_act = dto.last_active.strftime('%Y-%m-%d %H:%M') if dto.last_active else "No activity"
    embed.set_footer(text=f"Last active: {last_act}")
    return embed

def build_guild_report_embed(dto: GuildReportDTO, guild: discord.Guild) -> discord.Embed:
    """Builds the team contribution leaderboard embed."""
    embed = discord.Embed(
        title=f"🏆 Team Contribution Standings: {guild.name}",
        description="Ranking group participation, deliverables, and completed tasks.",
        color=COLOR_PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    if not dto.standings:
        embed.description = "No team activity recorded yet! Assign tasks and communicate to build standings."
        return embed

    lines = []
    for idx, item in enumerate(dto.standings[:10], start=1):
        member = guild.get_member(int(item.user_id))
        name = member.display_name if member else f"User {item.user_id}"
        lines.append(
            f"**{idx}. {name}** — Score: `{item.contribution_score:.1f}` | "
            f"✅ `{item.tasks_completed}` | 📁 `{item.files_submitted}` | 💬 `{item.message_count}`"
        )
    embed.add_field(name="Leaderboard", value="\n".join(lines), inline=False)
    embed.set_footer(text="Keep delivering to maintain team momentum!")
    return embed

def build_vault_receipt_embed(dto: VaultSubmissionResultDTO, user_name: str) -> discord.Embed:
    """Builds a verified submission receipt embed for vault uploads."""
    embed = discord.Embed(
        title="📦 Verified Deliverable Submitted",
        description=f"Deliverable has been cryptographically verified and archived.",
        color=COLOR_SUCCESS,
        timestamp=datetime.now(timezone.utc)
    )
    size_kb = round(dto.file_size / 1024, 2)
    embed.add_field(name="👤 Submitter", value=user_name, inline=True)
    embed.add_field(name="📄 Original Name", value=f"`{dto.original_filename}`", inline=True)
    embed.add_field(name="📦 Size", value=f"{size_kb} KB", inline=True)
    embed.add_field(name="🏷️ Vault File", value=f"`{dto.stored_filename}`", inline=False)
    if dto.notes:
        embed.add_field(name="📝 Notes", value=dto.notes, inline=False)
    embed.add_field(name="🔐 SHA-256 Hash", value=f"```{dto.file_hash}```", inline=False)
    embed.set_footer(text="Submission verified • Contribution score updated")
    return embed

def build_project_status_embed(dto: ProjectStatusDTO, guild_name: str) -> discord.Embed:
    """Builds a real-time project progress dashboard embed."""
    embed = discord.Embed(
        title=f"📊 Project Health Dashboard: {guild_name}",
        description=f"Current Status: **`{dto.status}`**",
        color=COLOR_PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    completion_rate = int((dto.completed_tasks / dto.total_tasks * 100)) if dto.total_tasks > 0 else 0
    bar_filled = min(10, max(0, completion_rate // 10))
    bar_str = "🟩" * bar_filled + "⬜" * (10 - bar_filled)

    embed.add_field(
        name="📋 Deliverable Tasks",
        value=f"**{dto.completed_tasks}** completed / **{dto.total_tasks}** total\n{bar_str} **{completion_rate}%**",
        inline=False
    )

    if dto.nearest_deadline_name and dto.nearest_deadline_due:
        abs_ts, rel_ts = format_discord_timestamps(dto.nearest_deadline_due)
        embed.add_field(
            name="🎯 Next Upcoming Milestone",
            value=f"**{dto.nearest_deadline_name}**\nDue: {abs_ts} ({rel_ts})",
            inline=False
        )
    else:
        embed.add_field(name="🎯 Next Upcoming Milestone", value="No active deadlines scheduled.", inline=False)

    embed.add_field(name="📁 Vault Deliverables", value=f"**{dto.total_files_submitted}** files verified", inline=True)
    embed.add_field(name="⏳ Open Tasks", value=f"**{dto.pending_tasks}** remaining", inline=True)
    embed.set_footer(text="Keep updating tasks to keep your accountability score high!")
    return embed

def build_project_archive_embed(dto: ProjectArchiveSummaryDTO, guild_name: str) -> discord.Embed:
    """Builds the final retrospective summary embed upon project completion."""
    embed = discord.Embed(
        title=f"🎓 Project Sprint Completed & Archived: {guild_name}",
        description=(
            f"This project has been officially concluded and archived by **{dto.archived_by}**.\n"
            f"All display channels (`#tasks`, `#deadlines`, `#submissions`) are preserved in read-only mode."
        ),
        color=COLOR_SUCCESS,
        timestamp=dto.archived_at
    )
    embed.add_field(name="✅ Total Tasks Completed", value=f"**{dto.total_tasks_completed}** tasks", inline=True)
    embed.add_field(name="📁 Verified Files Archived", value=f"**{dto.total_files_submitted}** deliverables", inline=True)

    if dto.standings:
        lines = []
        for idx, item in enumerate(dto.standings[:10], start=1):
            lines.append(
                f"**{idx}. <@{item.user_id}>** — Score: `{item.contribution_score:.1f}` pts | "
                f"✅ `{item.tasks_completed}` tasks | 📁 `{item.files_submitted}` files"
            )
        embed.add_field(name="🏆 Final Member Standings", value="\n".join(lines), inline=False)

    embed.set_footer(text="Project archived • Great work everyone!")
    return embed
