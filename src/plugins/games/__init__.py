"""Games plugin - the Squid Game arena.

Self-contained feature module. Owns the event lifecycle, player roster,
entry-fee pot escrow, voting, and the Red Light Green Light round. The
arena is game-agnostic: games register as modules and the arena owns
players, pot, elimination, voice, and votes.
"""