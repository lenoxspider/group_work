"""Games Discord embed formatters (Hot Pink #FF0090)."""

from datetime import datetime, timezone
from typing import Any, List, Optional

import discord

SQUID_PINK = discord.Color.from_rgb(255, 0, 144)      # #FF0090 hot pink
SQUID_TEAL = discord.Color.from_rgb(3, 122, 118)      # guard / track teal


def render_progress_bar(current: int, target: int, length: int = 10) -> str:
    clamped = max(0, min(current, target))
    ratio = clamped / target if target > 0 else 0
    filled = int(round(ratio * length))
    bar = "█" * filled + "░" * (length - filled)
    return f"`{bar}` {clamped}m / {target}m"


def build_enrollment_embed(player: Any, avatar_url: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title="○ △ □ GAMES • REGISTRATION CONFIRMED",
        description=f"Welcome to the games, <@{player.user_id}>.\nYour identity has been cataloged.",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc),
    )
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="Assigned Identifier", value=f"**`{player.display_tag}`**", inline=True)
    embed.add_field(name="Vital Status", value="`ALIVE`", inline=True)
    embed.add_field(name="Survival Streak", value=f"`{player.survival_streak} games`", inline=True)
    embed.set_footer(text="Follow all guard commands")
    return embed


def build_elimination_embed(result: Any, avatar_url: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title="○ △ □ PLAYER ELIMINATED",
        description=f"**`{result.display_tag}` (<@{result.user_id}>) HAS BEEN ELIMINATED.**",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc),
    )
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="Cause of Elimination", value=f"`{result.reason}`", inline=True)
    embed.add_field(name="Prize Pot", value=f"**`{result.pot_formatted}`**", inline=False)
    embed.set_footer(text="The games continue. Survivors will split the pot.")
    return embed


def build_status_embed(status: Any) -> discord.Embed:
    embed = discord.Embed(
        title="○ △ □ GAMES • ARENA DASHBOARD",
        description="Live status of the arena and the entry-fee pot.",
        color=SQUID_PINK,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Prize Pot (spi)", value=f"### `{status.pot_formatted}`", inline=False)
    embed.add_field(name="Active Survivors", value=f"**{status.alive_count}**", inline=True)
    embed.add_field(name="Eliminated", value=f"**{status.eliminated_count}**", inline=True)
    embed.add_field(name="Current Game", value=f"`{status.current_game}`", inline=True)
    embed.add_field(name="Event Status", value=f"`{status.status}`", inline=True)
    embed.add_field(name="Entry Fee", value=f"`{status.entry_fee} spi`", inline=True)
    embed.set_footer(text="Obey all directives from the Masked Guards.")
    return embed


def _ordinal(n: int) -> str:
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
    viewer_id: Optional[str] = None,
) -> discord.Embed:
    if light == "GREEN":
        embed = discord.Embed(
            title=f"GREEN LIGHT - Round {round_num}/{max_rounds}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        top_players = sorted(progress.items(), key=lambda x: x[1], reverse=True)[:5]
        board_lines = []
        for uid, dist in top_players:
            marker = " <- you" if str(uid) == str(viewer_id) else ""
            status = "🏁" if dist >= target else "🏃"
            board_lines.append(f"{status} <@{uid}>: {render_progress_bar(dist, target, length=8)}{marker}")
        embed.description = "\n".join(board_lines) if board_lines else "*Tap MOVE to sprint!*"
        embed.set_footer(text="green ends ~5s · tap MOVE")
    else:
        embed = discord.Embed(
            title=f"RED LIGHT - Round {round_num}/{max_rounds}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        elims = eliminated_names or []
        frozen_count = max(0, alive_count - len(elims))
        desc_lines = [
            "**FREEZE. Tapping MOVE now eliminates you.**",
            f"Still alive: **{alive_count}** · Frozen this round: **{frozen_count}**",
        ]
        embed.description = "\n".join(desc_lines)
        elim_str = ", ".join(f"<@{u}>" for u in elims) if elims else "*None this round*"
        embed.add_field(name="Eliminated this round", value=elim_str, inline=False)
        embed.set_footer(text="red · tap MOVE = eliminated")
    return embed


def build_ephemeral_move_feedback(res: Any) -> str:
    if res.status_code == "double_tap":
        return "**Double-tap ignored.**\nOnly one tap per 0.5s is registered.\n*Steady your fingers.*"

    if res.status_code == "sprint_limit":
        return "**Sprint limit reached for this round!**\nYou took your safe step and sprint burst.\n*Freeze and wait for the doll.*"

    if res.status_code == "finished" or res.is_finished:
        bar = "█" * 10
        return (
            f"**Crossed the finish line!** ({res.distance}m/{res.target}m)\n"
            f"`{bar}`\n"
            f"**You survived Red Light Green Light!**"
        )

    if not res.survived or res.status_code == "eliminated":
        return (
            "**MOVEMENT DETECTED DURING RED LIGHT!**\n"
            "You have been terminated by the doll.\n"
            "The arena has recorded your elimination."
        )

    if res.status_code == "grace":
        ratio = max(0, min(res.distance, res.target)) / res.target if res.target > 0 else 0
        filled = int(round(ratio * 10))
        bar = "█" * filled + "░" * (10 - filled)
        return (
            f"**Close call!** Stopped within latency grace window.\n"
            f"`{bar}` {res.distance}m/{res.target}m\n"
            f"*Freeze immediately! Sensors are active.*"
        )

    remaining = max(0, res.target - res.distance)
    ratio = max(0, min(res.distance, res.target)) / res.target if res.target > 0 else 0
    filled = int(round(ratio * 10))
    bar = "█" * filled + "░" * (10 - filled)
    line1 = f"+{res.advance}m -> {res.distance}m/{res.target}m"
    line2 = f"`{bar}`"
    line3 = f"{_ordinal(res.rank)} of {res.total_racers} still running · +{remaining}m to finish"
    return f"{line1}\n{line2}\n{line3}"


def build_bridge_embed(board: dict) -> discord.Embed:
    """Render the glass bridge: rows near to far, revealed panels, whose turn it is."""
    rows = board["rows"]
    known = board["known"]
    current_row = board["current_row"]
    current = board["current_player"]

    grid = ["```", "🏁 FAR SIDE"]
    for r in range(rows - 1, -1, -1):
        panel = known[r]
        if panel == "left":
            cells = "✅ ┃ 💥"
        elif panel == "right":
            cells = "💥 ┃ ✅"
        else:
            cells = "❓ ┃ ❓"
        marker = "  ◀ here" if (current and r == current_row) else ""
        grid.append(f"{r:>2}  {cells}{marker}")
    grid.append("🚪 NEAR SIDE")
    grid.append("```")

    head = (
        f"<@{current}> is at row **{current_row}**. Choose **Left** or **Right**."
        if current else "The crossing is complete."
    )
    embed = discord.Embed(
        title="○ △ □ GLASS BRIDGE",
        description="\n".join(grid) + "\n" + head,
        color=SQUID_PINK,
    )
    queue = board.get("queue", [])
    if len(queue) > 1:
        embed.add_field(
            name="Waiting", value=", ".join(f"<@{u}>" for u in queue[1:]), inline=False
        )
    if board.get("fell"):
        embed.add_field(
            name="Fallen", value=", ".join(f"<@{u}>" for u in board["fell"]), inline=True
        )
    if board.get("crossed"):
        embed.add_field(
            name="Crossed", value=", ".join(f"<@{u}>" for u in board["crossed"]), inline=True
        )
    embed.set_footer(text="A panel someone dies on is known to everyone behind them.")
    return embed


def build_bridge_feedback(move) -> str:
    """Ephemeral line shown to the player who just chose."""
    if move.outcome == "safe":
        return f"✅ Tempered glass. You step forward to row {move.row + 1}. Keep going."
    if move.outcome == "crossed":
        return "🏁 **You crossed the bridge.** Step off and watch the rest."
    if move.outcome == "fell":
        return "💥 The panel shatters. You fall. The next player now knows which side was safe."
    if move.outcome == "stalled":
        return "⌛ You did not choose in time. The glass gives way beneath you."
    return "Move recorded."