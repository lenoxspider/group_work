"""Pulse modules - each one is a short, one-action moment.

A module builder is async and receives (community, guild_id). It returns a
pulse spec dict, or None when the module cannot run right now (the engine then
falls through to the next module).

Modes:
- "reaction": first person to react with `answer` wins.
- "message": first person whose chat message normalizes into `accept` wins.
- "vote": reactions are ballots; the engine tallies at expiry and resolves.
"""

import random
import re
from typing import Optional

import discord

from src.plugins.pulse.domain import (
    SNAP_COMPENSATION_SPI,
    SNAP_FINE_SPI,
    SNAP_GUILTY_EMOJI,
    SNAP_INNOCENT_EMOJI,
    SNAP_TIMEOUT_SECONDS,
)

PINK = discord.Color.from_rgb(255, 0, 144)


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


# --- Odd One Out ---

_ODD_PAIRS = [
    ("🍏", "🍎"), ("🔵", "🔷"), ("⭐", "🌟"), ("😀", "😃"),
    ("🐱", "🐈"), ("🟩", "🟢"), ("🔴", "🔺"), ("🌕", "🌖"),
    ("🐶", "🐕"), ("💧", "💦"),
]

_GRID = 25
_COLS = 5


async def _odd_one_out(community, guild_id) -> dict:
    base, odd = random.choice(_ODD_PAIRS)
    cells = [base] * _GRID
    cells[random.randrange(_GRID)] = odd
    rows = [" ".join(cells[r * _COLS:(r + 1) * _COLS]) for r in range(_GRID // _COLS)]
    embed = discord.Embed(
        title="👁️ ODD ONE OUT",
        description="One emoji is different.\n**First to click the odd one wins the pot.**\n\n" + "\n".join(rows),
        color=PINK,
    )
    return {
        "kind": "odd_one_out",
        "label": "Odd One Out",
        "mode": "reaction",
        "embed": embed,
        "content": None,
        "answer": odd,
        "accept": (),
        "reactions": [base, odd],
    }


# --- Cipher Sprint ---

_RIDDLES = [
    {"q": "I speak without a mouth and hear without ears. What am I?", "a": "echo"},
    {"q": "What gets wetter the more it dries?", "a": "towel"},
    {"q": "What has keys but no locks?", "a": "piano"},
    {"q": "I'm tall when I'm young and short when I'm old. What am I?", "a": "candle"},
    {"q": "What has a head and a tail but no body?", "a": "coin"},
    {"q": "The more you take, the more you leave behind. What are they?", "a": "footsteps", "aliases": ["footprints", "steps"]},
    {"q": "What has many teeth but cannot bite?", "a": "comb"},
    {"q": "What can you catch but never throw?", "a": "cold"},
    {"q": "What begins with T, ends with T, and is full of T?", "a": "teapot"},
    {"q": "How many months of the year have 28 days?", "a": "12", "aliases": ["twelve", "all", "every", "everyone"]},
    {"q": "What must be broken before you can use it?", "a": "egg"},
    {"q": "A kilogram of feathers or a kilogram of steel: which weighs more?", "a": "same", "aliases": ["neither", "equal", "both", "thesameweight"]},
    {"q": "What 5-letter word gets shorter when you add two letters?", "a": "short"},
    {"q": "What goes up but never comes down?", "a": "age"},
    {"q": "What has one eye but cannot see?", "a": "needle"},
    {"q": "What runs but never walks?", "a": "water", "aliases": ["river"]},
]


async def _cipher_sprint(community, guild_id) -> dict:
    r = random.choice(_RIDDLES)
    accept = [normalize(r["a"])] + [normalize(x) for x in r.get("aliases", [])]
    embed = discord.Embed(
        title="🔐 CIPHER SPRINT",
        description=f"**{r['q']}**\n\nFirst correct answer in chat wins the pot.",
        color=PINK,
    )
    return {
        "kind": "cipher_sprint",
        "label": "Cipher Sprint",
        "mode": "message",
        "embed": embed,
        "content": None,
        "answer": r["a"],
        "accept": tuple(accept),
        "reactions": [],
    }


# --- Snap Trial ---

_CRIMES = [
    "excessive lounging during work hours",
    "hoarding snacks from the common room",
    "speaking ill of the Front Man",
    "plotting to defect to the spectators",
    "dancing without a permit",
    "wasting the collective's time with riddles",
    "wearing the wrong color on game day",
    "embezzling crumbs from the treasury",
    "consorting with the masked guards",
    "falsifying a task completion",
    "unauthorized napping in the dormitory",
    "spreading rumors about the VIP room",
]


async def _snap_trial(community, guild_id) -> Optional[dict]:
    if not community:
        return None
    try:
        citizens = await community.list_citizens(guild_id)
    except Exception:
        return None
    if not citizens:
        return None
    accused_id = random.choice(citizens)
    crime = random.choice(_CRIMES)
    embed = discord.Embed(
        title="⚖️ SNAP TRIAL",
        description=(
            f"**<@{accused_id}>** stands accused of **{crime}**.\n\n"
            "Comrades, cast your verdict:\n"
            f"{SNAP_GUILTY_EMOJI} **GUILTY**    {SNAP_INNOCENT_EMOJI} **INNOCENT**\n\n"
            f"*Voting closes in 5 minutes. Simple majority rules.*\n"
            f"*Guilty pays {SNAP_FINE_SPI} spi to the treasury; innocent earns {SNAP_COMPENSATION_SPI} spi.*"
        ),
        color=PINK,
    )
    return {
        "kind": "snap_trial",
        "label": "Snap Trial",
        "mode": "vote",
        "embed": embed,
        "content": None,
        "answer": "",
        "accept": (),
        "reactions": [SNAP_GUILTY_EMOJI, SNAP_INNOCENT_EMOJI],
        "vote_options": {SNAP_GUILTY_EMOJI: "guilty", SNAP_INNOCENT_EMOJI: "innocent"},
        "timeout_seconds": SNAP_TIMEOUT_SECONDS,
        "data": {"accused_id": accused_id, "crime": crime},
    }


MODULES = [_odd_one_out, _cipher_sprint, _snap_trial]


async def build_random(community, guild_id) -> Optional[dict]:
    builders = list(MODULES)
    random.shuffle(builders)
    for builder in builders:
        try:
            spec = await builder(community, guild_id)
        except Exception:
            spec = None
        if spec:
            return spec
    return None
