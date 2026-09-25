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

from src.application.dtos.task_dtos import TaskResultDTO, OverdueShameActionDTO
from src.application.dtos.deadline_dtos import DeadlineResultDTO
from src.application.dtos.report_dtos import MemberReportDTO, GuildReportDTO
from src.application.dtos.project_dtos import ProjectStatusDTO, ProjectArchiveSummaryDTO
from src.application.dtos.extension_dtos import ExtensionResultDTO
from src.application.dtos.preference_dtos import MemberPreferenceDTO
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
    if dto.is_completed:
        if dto.needs_verification:
            color = COLOR_WARNING
            title = f"🔍 Task: {dto.task_id} (Awaiting Sign-off)"
            status_text = f"Submitted by <@{dto.assigned_to}> • Pending Buddy Verification"
        else:
            color = COLOR_SUCCESS
            title = f"✅ Task: {dto.task_id}"
            timing_badge = " (On-Time ⚡)" if dto.is_on_time else " (Late ⚠️)"
            if dto.verified_by:
                status_text = f"Verified Complete by <@{dto.verified_by}> at {dto.completed_at}{timing_badge}"
            else:
                status_text = f"Completed at {dto.completed_at}{timing_badge}"
    elif dto.is_in_progress:
        color = COLOR_WARNING
        title = f"🔄 Task: {dto.task_id}"
        status_text = "In Progress ⚙️"
    else:
        color = COLOR_PRIMARY
        title = f"📋 Task: {dto.task_id}"
        status_text = "Pending ⏳"

    embed = discord.Embed(
        title=title,
        description=f"**{dto.description}**",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 Assignee", value=f"<@{dto.assigned_to}>", inline=True)
    if dto.verifier_id:
        embed.add_field(name="🔍 Accountability Buddy", value=f"<@{dto.verifier_id}>", inline=True)
    embed.add_field(name="📌 Status", value=f"`{status_text}`", inline=True)
    embed.add_field(name="⏰ Due Date", value=f"{abs_ts} ({rel_ts})", inline=False)
    if dto.needs_verification:
        footer = f"Task ID: {dto.task_id} • Awaiting verifier sign-off via button or /task verify"
    elif dto.is_completed:
        footer = "Task completed"
    else:
        footer = f"Task ID: {dto.task_id} • Use buttons below or /task complete"
    embed.set_footer(text=footer)
    return embed

def build_preference_embed(dto: MemberPreferenceDTO, member: discord.Member) -> discord.Embed:
    """Builds a settings card for student timezone and quiet hours."""
    embed = discord.Embed(
        title=f"⚙️ Notification Preferences: {member.display_name}",
        color=COLOR_PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    quiet_status = "🌙 Active Now (DND)" if dto.is_currently_quiet else "☀️ Awake (Pings allowed)"
    embed.add_field(name="🌐 Timezone", value=f"`{dto.timezone_name}`", inline=True)
    embed.add_field(name="🌙 Quiet Hours Window", value=f"`{dto.quiet_hours_start:02d}:00` to `{dto.quiet_hours_end:02d}:00`", inline=True)
    embed.add_field(name="📡 Current Status", value=quiet_status, inline=False)
    embed.set_footer(text="Bot will hold DM reminders during quiet hours.")
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
    """Builds an individual student contribution scorecard embed with rank and streaks."""
    embed = discord.Embed(
        title=f"📊 Contribution Scorecard: {member.display_name}",
        description=f"Anti-free-riding metrics • Military Rank: 🎖️ **{dto.rank_title}**",
        color=COLOR_PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)

    bar_filled = min(10, max(0, dto.completion_rate // 10))
    bar_str = "🟩" * bar_filled + "⬜" * (10 - bar_filled)

    embed.add_field(
        name="✅ Tasks Delivered",
        value=f"**{dto.tasks_completed}** (Pending: {dto.pending_tasks})",
        inline=True
    )
    embed.add_field(
        name="🔥 On-Time Streak",
        value=f"**{dto.current_streak}** (Best: {dto.best_streak})",
        inline=True
    )
    embed.add_field(
        name="⏱️ On-Time Rate",
        value=f"**{dto.on_time_rate}%** ({dto.on_time_tasks}/{dto.tasks_completed})",
        inline=True
    )
    embed.add_field(name="💬 Messages", value=f"**{dto.message_count}**", inline=True)
    embed.add_field(name="📁 Vault Deliverables", value=f"**{dto.files_submitted}**", inline=True)
    embed.add_field(
        name="🏆 Contribution Score",
        value=f"**{dto.contribution_score:.1f}** pts",
        inline=True
    )
    embed.add_field(
        name="📈 Task Completion Rate",
        value=f"{bar_str} **{dto.completion_rate}%**",
        inline=False
    )
    last_act = dto.last_active.strftime('%Y-%m-%d %H:%M') if dto.last_active else "No activity"
    embed.set_footer(text=f"Rank: {dto.rank_title} • Last active: {last_act}")
    return embed

def build_guild_report_embed(dto: GuildReportDTO, guild: discord.Guild) -> discord.Embed:
    """Builds the team contribution leaderboard embed with ranks and streaks."""
    embed = discord.Embed(
        title=f"🏆 Team Contribution Standings: {guild.name}",
        description="Ranking group participation, deliverables, on-time streaks, and military ranks.",
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
        streak_str = f"🔥 `{item.current_streak}`" if item.current_streak > 0 else "❄️ `0`"
        lines.append(
            f"**{idx}. {name}** [🎖️ {item.rank_title}] — Score: `{item.contribution_score:.1f}` | "
            f"Streak: {streak_str} | ✅ `{item.tasks_completed}` | 📁 `{item.files_submitted}`"
        )
    embed.add_field(name="Leaderboard", value="\n".join(lines), inline=False)
    embed.set_footer(text="Complete deliverables on time to rank up and maintain your streak!")
    return embed

def build_wall_of_shame_embed(dto: OverdueShameActionDTO) -> discord.Embed:
    """Builds a public shaming embed for an overdue deliverable."""
    abs_ts, rel_ts = format_discord_timestamps(dto.due_date)
    embed = discord.Embed(
        title="🚨 WALL OF SHAME: Overdue Task Alert!",
        description=f"Attention team: <@{dto.user_id}> has failed to deliver their committed task on time.",
        color=COLOR_DANGER,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📋 Delinquent Task", value=f"**{dto.description}** (`{dto.task_id}`)", inline=False)
    embed.add_field(name="⏰ Deadline Was", value=f"{abs_ts} ({rel_ts})", inline=True)
    embed.add_field(name="⚠️ Overdue By", value=f"**{dto.hours_overdue} hour(s)**", inline=True)
    embed.add_field(name="💔 Penalty Applied", value="Consecutive on-time streak reset to **0**! 🔥 0", inline=False)
    embed.set_footer(text="Deliver your commitments promptly to maintain team accountability.")
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

def build_extension_vote_embed(dto: ExtensionResultDTO, task_desc: str) -> discord.Embed:
    """Builds an interactive peer voting card for deadline extension requests."""
    abs_ts, rel_ts = format_discord_timestamps(dto.proposed_due_date)
    if dto.status == "APPROVED":
        color = COLOR_SUCCESS
        status_label = "✅ Approved by Majority (Deadline Extended)"
    elif dto.status == "REJECTED":
        color = COLOR_DANGER
        status_label = "❌ Rejected by Majority (Original Deadline Maintained)"
    else:
        color = COLOR_PRIMARY
        status_label = "⏳ Voting In Progress (Majority Decides)"

    embed = discord.Embed(
        title=f"🗳️ Extension Request Vote: {dto.request_id}",
        description=f"<@{dto.requester_id}> has requested a deadline extension for task **{dto.task_id}**.",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📋 Task Deliverable", value=task_desc, inline=False)
    embed.add_field(name="⏰ Proposed Deadline", value=f"{abs_ts} ({rel_ts})", inline=False)
    embed.add_field(name="📝 Reason for Extension", value=f"*{dto.reason}*", inline=False)
    embed.add_field(
        name="📊 Team Vote Tally",
        value=f"👍 **Approve:** `{dto.approvals_count}`  |  👎 **Reject:** `{dto.rejections_count}`",
        inline=True
    )
    embed.add_field(name="📌 Status", value=f"`{status_label}`", inline=True)
    footer = "Voting concluded" if dto.is_resolved else f"Request ID: {dto.request_id} • Click buttons below to vote"
    embed.set_footer(text=footer)
    return embed

