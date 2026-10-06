"""Shop domain - the cosmetic catalogue.

Each item maps to a Discord role created on demand. Prices are set against the
balances actually sitting idle in wallets, so the rich have something to spend
on and the broke have a visible goal.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    item_id: str
    name: str      # also the Discord role name
    price: int
    color: int     # role colour
    hoist: bool    # show as its own group in the member list
    blurb: str


CATALOGUE = [
    Item("circle", "○ Circle", 300, 0x00E5FF, False,
         "The mark of the labourer. Wear it."),
    Item("triangle", "△ Triangle", 300, 0xFF3D3D, False,
         "The mark of the soldier."),
    Item("square", "□ Square", 300, 0xF5F5F5, False,
         "The mark of the manager."),
    Item("pink", "▢ Pink", 400, 0xFF0090, False,
         "The Front Man's colour. Your name, in it."),
    Item("guard", "▢ Guard", 700, 0xE4002B, True,
         "Hoisted hot pink. Everyone sees you in the list."),
    Item("gold", "▢ Gold", 900, 0xFFD700, False,
         "A golden name. Nothing else."),
    Item("vip", "▢ VIP", 1500, 0xFFB300, True,
         "Hoisted title. You sit above the players."),
    Item("player456", "▢ Player 456", 2500, 0x00FF88, True,
         "The top of the ledger. One colour, one legend."),
]

BY_ID = {item.item_id: item for item in CATALOGUE}
