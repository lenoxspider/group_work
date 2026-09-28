"""Pulse modules - each one is a short, one-action moment.

A module builds a pulse spec: {kind, label, mode, embed, content, answer,
reactions}. mode is "reaction" (first correct reaction wins) or "message"
(first correct message wins).
"""

import random

import discord

PINK = discord.Color.from_rgb(255, 0, 144)

_ODD_PAIRS = [
    ("🍏", "🍎"), ("🔵", "🔷"), ("⭐", "🌟"), ("😀", "😃"),
    ("🐱", "🐈"), ("🟩", "🟢"), ("🔴", "🔺"), ("🌕", "🌖"),
    ("🐶", "🐕"), ("💧", "💦"),
]

_GRID = 25
_COLS = 5


def _odd_one_out() -> dict:
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
        "reactions": [base, odd],
    }


MODULES = [_odd_one_out]


def build_random() -> dict:
    return random.choice(MODULES)()