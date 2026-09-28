"""Pulse modules - each one is a short, one-action moment.

A module builds a pulse spec: {kind, label, mode, embed, content, answer,
accept, reactions}.

- mode "reaction": first person to react with `answer` wins.
- mode "message": first person whose chat message normalizes into `accept` wins.
"""

import random
import re

import discord

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


def _cipher_sprint() -> dict:
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


MODULES = [_odd_one_out, _cipher_sprint]


def build_random() -> dict:
    return random.choice(MODULES)()