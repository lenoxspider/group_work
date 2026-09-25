from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import discord
from bot.utils.helpers import to_discord_timestamps, format_countdown_string

COLOR_PRIMARY = discord.Color.from_rgb(88, 101, 242)   # Blurple
COLOR_SUCCESS = discord.Color.from_rgb(87, 242, 135)   # Green
COLOR_WARNING = discord.Color.from_rgb(254, 231, 92)   # Amber
COLOR_DANGER  = discord.Color.from_rgb(237, 66, 69)    # Red
COLOR_INFO    = discord.Color.from_rgb(0, 176, 244)    # Cyan

def create_task_embed(task: Dict[str, Any], assignee: Optional[discord.Member] = None) -> discord.Embed:
    """Creates a sleek task card for #tasks ledger."""
    due_dt = datetime.fromisoformat(task["due_date"])
    abs_ts, rel_ts = to_discord_timestamps(due_dt)
    is_completed = task.get("completed_at") is not None
    
    color = COLOR_SUCCESS if is_completed else COLOR_PRIMARY
    title = f"{'✅' if is_completed else '📋'} Task: {task['task_id']}"
    
    embed = discord.Embed(
        title=title,
        description=f"**{task['description']}**",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    
    assignee_mention = f"<@{task['assigned_to']}>" if not assignee else assignee.mention
    embed.add_field(name="👤 Assigned To", value=assignee_mention, inline=True)
    
    status_str = f"Completed at {task['completed_at']}" if is_completed else "In Progress"
    embed.add_field(name="📌 Status", value=f"`{status_str}`", inline=True)
    
    embed.add_field(name="⏰ Due Date", value=f"{abs_ts} ({rel_ts})", inline=False)
    
    footer_text = "Mark complete with /task complete " + task["task_id"]
    if is_completed:
        footer_text = "Task completed successfully"
    embed.set_footer(text=footer_text)
    return embed

def create_deadline_embed(deadline: Dict[str, Any]) -> discord.Embed:
    """Creates a pinned countdown card for #deadlines channel."""
    due_dt = datetime.fromisoformat(deadline["due_datetime"])
    abs_ts, rel_ts = to_discord_timestamps(due_dt)
    countdown_str = format_countdown_string(due_dt)
    
    now = datetime.now(timezone.utc)
    is_overdue = due_dt < now
    
    embed = discord.Embed(
        title=f"🎯 Target Deadline: {deadline['name']}",
        color=COLOR_DANGER if is_overdue else COLOR_INFO,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.add_field(name="⏳ Live Countdown", value=f"### {countdown_str}", inline=False)
    embed.add_field(name="📅 Due Date & Time", value=f"{abs_ts}\n{rel_ts}", inline=True)
    embed.add_field(name="🆔 Deadline ID", value=f"`{deadline['deadline_id']}`", inline=True)
    embed.set_footer(text="Auto-updates hourly • Reminders at 72h, 24h & 6h")
    return embed

def create_member_report_embed(member: discord.Member, stats: Dict[str, Any]) -> discord.Embed:
    """Creates a contribution report card for an individual member."""
    embed = discord.Embed(
        title=f"📊 Contribution Report: {member.display_name}",
        description="Summary of task accountability, team communication, and submitted assets.",
        color=COLOR_PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
        
    tasks_done = stats.get("tasks_completed", 0)
    tasks_pending = stats.get("pending_tasks", 0)
    msg_count = stats.get("message_count", 0)
    files_count = stats.get("files_submitted", 0)
    
    # Visual mini bar
    total_tasks = tasks_done + tasks_pending
    rate = int((tasks_done / total_tasks * 100)) if total_tasks > 0 else 0
    bar_filled = int(rate / 10)
    progress_bar = "🟩" * bar_filled + "⬜" * (10 - bar_filled)
    
    embed.add_field(name="✅ Tasks Completed", value=f"**{tasks_done}** (Pending: {tasks_pending})", inline=True)
    embed.add_field(name="💬 Messages Sent", value=f"**{msg_count}** messages", inline=True)
    embed.add_field(name="📁 Files Submitted", value=f"**{files_count}** submissions", inline=True)
    
    if total_tasks > 0:
        embed.add_field(name="📈 Task Completion Rate", value=f"{progress_bar} **{rate}%**", inline=False)
    
    last_active = stats.get("last_active")
    if last_active:
        embed.set_footer(text=f"Last activity recorded: {last_active}")
    else:
        embed.set_footer(text="Accountability score is tracked automatically")
        
    return embed

def create_guild_report_embed(guild_name: str, report_data: List[Dict[str, Any]], bot: discord.Client) -> discord.Embed:
    """Creates a summary leaderboard of team contributions."""
    embed = discord.Embed(
        title=f"🏆 Group Contribution Overview: {guild_name}",
        description="Tracking active participation, task completions, and deliverables.",
        color=COLOR_PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    
    if not report_data:
        embed.description = "No activity logged yet! Start sending messages, assigning tasks, and uploading drafts."
        return embed

    lines = []
    for idx, row in enumerate(report_data[:10], start=1):
        user = bot.get_user(int(row["user_id"]))
        name = user.display_name if user else f"User {row['user_id']}"
        lines.append(
            f"**{idx}. {name}** — ✅ `{row.get('tasks_completed', 0)}` tasks | "
            f"💬 `{row.get('message_count', 0)}` msgs | "
            f"📁 `{row.get('files_submitted', 0)}` files"
        )
        
    embed.add_field(name="Member Standings", value="\n".join(lines), inline=False)
    embed.set_footer(text="Keep contributing to maintain team momentum!")
    return embed

def create_file_submission_embed(original_filename: str, stored_name: str, file_hash: str, file_size: int, member: discord.User) -> discord.Embed:
    """Creates a submission receipt embed for DM vault."""
    embed = discord.Embed(
        title="📥 Deliverable Verified & Stored",
        description=f"Your file has been secured in the group submission vault.",
        color=COLOR_SUCCESS,
        timestamp=datetime.now(timezone.utc)
    )
    size_kb = round(file_size / 1024, 2)
    embed.add_field(name="📄 Original Filename", value=f"`{original_filename}`", inline=True)
    embed.add_field(name="🏷️ Vault Filename", value=f"`{stored_name}`", inline=True)
    embed.add_field(name="📦 Size", value=f"{size_kb} KB", inline=True)
    embed.add_field(name="🔐 SHA-256 Hash", value=f"```{file_hash}```", inline=False)
    embed.set_footer(text=f"Submitted by {member.name} • Version verified")
    return embed
