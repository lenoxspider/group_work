"""
Squid Game Discord embed presentation formatters.

What it does:
- Serializes Squid Game DTOs into high-contrast Hot Pink (#FF0090) Discord Embeds.
- Formats enrollment, elimination notices, piggy-bank pot status, and Red Light Green Light indicators.

What it does NOT do:
- Does NOT execute game rules or database operations.
"""

from typing import Optional, List
from datetime import datetime, timezone
import discord
from src.application.dtos.squid_dtos import (
    PlayerResultDTO,
    EliminationResultDTO,
    SquidStatusDTO,
    RedLightMoveResultDTO
)

SQUID_PINK = discord.Color.from_rgb(255, 0, 144)      # #FF0090 Iconic hot pink
SQUID_TEAL = discord.Color.from_rgb(3, 122, 118)      # #037A76 Guard / track teal
SQUID_DARK = discord.Color.from_rgb(15, 15, 15)

def render_progress_bar(current: int, target: int, length: int = 10) -> str:
    """Generates a monospace ASCII progress bar in backticks."""
    clamped = max(0, min(current, target))
    ratio = clamped / target if target > 0 else 0
    filled = int(round(ratio * length))
    bar = "█" * filled + "░" * (length - filled)
    return f"`{bar}` {clamped}m / {target}m"

def build_squid_enrollment_embed(dto: PlayerResultDTO, avatar_url: Optional[str] = None) -> discord.Embed:
    """Creates a player registration card with assigned 3-digit tag and avatar."""
    embed = discord.Embed(
        title="○ △ □ SQUID GAME • REGISTRATION CONFIRMED",
        description=f"Welcome to the games, <@{dto.user_id}>.\nYour identity has been cataloged.",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc)
    )
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="🏷️ Assigned Identifier", value=f"**`{dto.display_tag}`**", inline=True)
    embed.add_field(name="❤️ Vital Status", value="`ALIVE (🟢)`", inline=True)
    embed.add_field(name="🔥 Survival Streak", value=f"`{dto.survival_streak} games`", inline=True)
    embed.set_footer(text="Elimination on terminal overdue task • Follow all guard commands")
    return embed

def build_squid_elimination_embed(dto: EliminationResultDTO, avatar_url: Optional[str] = None) -> discord.Embed:
    """Creates a death notification card with reason, bounty contribution, and avatar."""
    embed = discord.Embed(
        title="○ △ □ PLAYER ELIMINATED",
        description=f"**`{dto.display_tag}` (<@{dto.user_id}>) HAS BEEN ELIMINATED.**",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc)
    )
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="💀 Cause of Elimination", value=f"`{dto.reason}`", inline=True)
    embed.add_field(name="💰 Added to Piggy Bank", value="`+₩ 100,000,000`", inline=True)
    embed.add_field(name="🏆 Total Accumulated Pot", value=f"**`{dto.pot_formatted}`**", inline=False)
    embed.set_footer(text="The games continue. One player will take the pot.")
    return embed

def build_squid_status_embed(dto: SquidStatusDTO) -> discord.Embed:
    """Builds season overview dashboard."""
    embed = discord.Embed(
        title="○ △ □ SQUID GAME • ARENA DASHBOARD",
        description="Live status of the accountability arena and accumulated bounty.",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="💰 Piggy Bank Prize Pool", value=f"### `{dto.pot_formatted}`", inline=False)
    embed.add_field(name="🟢 Active Survivors", value=f"**{dto.alive_count}** players", inline=True)
    embed.add_field(name="💀 Eliminated", value=f"**{dto.eliminated_count}** players", inline=True)
    embed.add_field(name="🎮 Next / Active Game", value=f"`{dto.current_game}`", inline=True)
    embed.set_footer(text="Stay on schedule. Missed deliverables result in termination.")
    return embed

def _ordinal(n: int) -> str:
    """Returns ordinal string e.g. 1st, 2nd, 3rd, 7th."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def build_red_light_embed(
    light: str,
    target: int,
    progress: dict,
    round_num: int = 1,
    max_rounds: int = 5,
    alive_count: int = 0,
    eliminated_names: Optional[List[str]] = None,
    viewer_id: Optional[str] = None
) -> discord.Embed:
    """Builds mobile-first footer-centric track embed."""
    if light == "GREEN":
        embed = discord.Embed(
            title=f"🟢 GREEN LIGHT — Round {round_num}/{max_rounds}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        # Top-5 leaderboard only with `← you` marker
        top_players = sorted(progress.items(), key=lambda x: x[1], reverse=True)[:5]
        board_lines = []
        for uid, dist in top_players:
            bar_str = render_progress_bar(dist, target, length=8)
            marker = " ← you" if str(uid) == str(viewer_id) else ""
            status = "🏁" if dist >= target else "🏃"
            board_lines.append(f"{status} <@{uid}>: {bar_str}{marker}")

        content = "\n".join(board_lines) if board_lines else "*Tap MOVE to sprint!*"
        embed.description = content
        embed.set_footer(text="🟢 ends ~5s · tap MOVE")
    else:
        embed = discord.Embed(
            title=f"🔴 RED LIGHT — Round {round_num}/{max_rounds}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        elims = eliminated_names or []
        frozen_count = max(0, alive_count - len(elims))
        desc_lines = [
            "**FREEZE. Tapping MOVE now eliminates you.**",
            f"Still alive: **{alive_count}** · Frozen this round: **{frozen_count}**"
        ]
        embed.description = "\n".join(desc_lines)
        elim_str = ", ".join(f"<@{u}>" for u in elims) if elims else "*None this round*"
        embed.add_field(name="💀 Eliminated this round", value=elim_str, inline=False)
        embed.set_footer(text="🔴 tap MOVE = eliminated")

    return embed

def build_ephemeral_move_feedback(res: RedLightMoveResultDTO) -> str:
    """Builds 3-line private feedback positioned above the mobile keyboard."""
    if res.status_code == "double_tap":
        return "⚠️ **Double-tap ignored.**\nOnly one tap per 0.5s is registered.\n*Steady your fingers.*"

    if res.status_code == "sprint_limit":
        return "⚠️ **Sprint limit reached for this round!**\nYou took your safe step and sprint burst.\n*Freeze and wait for the doll.*"

    if res.status_code == "finished" or res.is_finished:
        bar = "█" * 10
        return (
            f"🏁 **Crossed the finish line!** ({res.distance}m/{res.target}m)\n"
            f"`{bar}`\n"
            f"🏆 You survived Red Light Green Light!"
        )

    if not res.survived or res.status_code == "eliminated":
        return (
            "💀 **MOVEMENT DETECTED DURING RED LIGHT!**\n"
            "You have been terminated by the doll.\n"
            "💰 +₩ 100,000,000 added to the piggy bank."
        )

    if res.status_code == "grace":
        ratio = max(0, min(res.distance, res.target)) / res.target if res.target > 0 else 0
        filled = int(round(ratio * 10))
        bar = "█" * filled + "░" * (10 - filled)
        return (
            f"⚠️ **Close call!** Stopped within latency grace window.\n"
            f"`{bar}` {res.distance}m/{res.target}m\n"
            f"🚨 Freeze immediately! Sensors are active."
        )

    # Standard green light step
    remaining = max(0, res.target - res.distance)
    ratio = max(0, min(res.distance, res.target)) / res.target if res.target > 0 else 0
    filled = int(round(ratio * 10))
    bar = "█" * filled + "░" * (10 - filled)
    
    line1 = f"+{res.advance}m → {res.distance}m/{res.target}m"
    line2 = f"`{bar}`"
    line3 = f"{_ordinal(res.rank)} of {res.total_racers} still running · +{remaining}m to finish"
    return f"**{line1}**\n{line2}\n{line3}"

