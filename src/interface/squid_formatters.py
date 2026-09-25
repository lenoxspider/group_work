"""
Squid Game Discord embed presentation formatters.

What it does:
- Serializes Squid Game DTOs into high-contrast Hot Pink (#FF0090) Discord Embeds.
- Formats enrollment, elimination notices, piggy-bank pot status, and Red Light Green Light indicators.

What it does NOT do:
- Does NOT execute game rules or database operations.
"""

from datetime import datetime, timezone
import discord
from src.application.dtos.squid_dtos import (
    PlayerResultDTO,
    EliminationResultDTO,
    SquidStatusDTO
)

SQUID_PINK = discord.Color.from_rgb(255, 0, 144)      # #FF0090 Iconic hot pink
SQUID_TEAL = discord.Color.from_rgb(3, 122, 118)      # #037A76 Guard / track teal
SQUID_DARK = discord.Color.from_rgb(15, 15, 15)

def build_squid_enrollment_embed(dto: PlayerResultDTO) -> discord.Embed:
    """Creates a player registration card with assigned 3-digit tag."""
    embed = discord.Embed(
        title="○ △ □ SQUID GAME • REGISTRATION CONFIRMED",
        description=f"Welcome to the games, <@{dto.user_id}>.\nYour identity has been cataloged.",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏷️ Assigned Identifier", value=f"**`{dto.display_tag}`**", inline=True)
    embed.add_field(name="❤️ Vital Status", value="`ALIVE (🟢)`", inline=True)
    embed.add_field(name="🔥 Survival Streak", value=f"`{dto.survival_streak} games`", inline=True)
    embed.set_footer(text="Elimination on terminal overdue task • Follow all guard commands")
    return embed

def build_squid_elimination_embed(dto: EliminationResultDTO) -> discord.Embed:
    """Creates a death notification card with reason and bounty contribution."""
    embed = discord.Embed(
        title="○ △ □ PLAYER ELIMINATED",
        description=f"**`{dto.display_tag}` (<@{dto.user_id}>) HAS BEEN ELIMINATED.**",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc)
    )
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

def build_red_light_embed(light: str, target: int, progress: dict) -> discord.Embed:
    """Builds the live Red Light Green Light track status embed."""
    if light == "GREEN":
        color = discord.Color.green()
        title = "🟢 GREEN LIGHT • ADVANCE NOW!"
        desc = "Type `/move` to advance across the field. **Stop when the doll turns.**"
    else:
        color = discord.Color.red()
        title = "🔴 RED LIGHT • REMAIN STILL!"
        desc = "🚨 **DO NOT MOVE.** Any `/move` executed now triggers **instant elimination!**"

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    leaderboard_lines = []
    for user_id, dist in sorted(progress.items(), key=lambda x: x[1], reverse=True)[:10]:
        finished = "🏁 FINISHED" if dist >= target else f"{dist}/{target}m"
        leaderboard_lines.append(f"<@{user_id}>: `{finished}`")

    embed.add_field(
        name="🏃 Field Positions",
        value="\n".join(leaderboard_lines) if leaderboard_lines else "*No movements yet.*",
        inline=False
    )
    embed.set_footer(text=f"Target distance: {target}m")
    return embed
