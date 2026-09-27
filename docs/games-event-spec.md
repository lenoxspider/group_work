# Games Event Specification

The reference spec for the games/event system. Sourced from the Netflix
series *Squid Game* (season 1 games, seasons 1-3 voting mechanic) and
translated into the bot's plugin architecture.

Status: **design spec** - build against this when implementing the `games`
plugin.

---

## 1. Source mechanics

Facts that define the shape of the system:

| Concept | Series rule | Bot mapping |
|---|---|---|
| Players | 456, all recruited, numbered `001`-`456` | `Player` entity with a sequential number |
| Prize | Won 100,000,000 per eliminated player, max Won 45.6B | `Pot`, grows per elimination |
| Prize visibility | A giant transparent piggy bank that fills as people die | Public pot, announced every elimination |
| Guards | Pink suits; circle = worker, triangle = soldier, square = manager; Front Man in black | `guard_voice` + masked announcements (existing TTS) |
| Doll | A giant motion-sensing doll runs game 1 | RLGL round state machine (existing) |
| Consent clause 3 | Players may vote to terminate the games by majority | `vote` between rounds |

---

## 2. Core concepts

### Event
One run of the games. Members register, get numbers, play the games in
order, and the last survivor (or a stop-vote) ends it.

- `status`: `REGISTERING -> ONGOING -> VOTING -> (loop) -> CONCLUDED`
- `pot`: total prize, grows per elimination
- `winner`: last player alive (or `null` if the event ended on a stop-vote)
- `current_game`: index into the ordered game list

### Player
A registered member. Losing *any* game eliminates them **from the event**,
not just that round - this is the core rule.

- `player_number`: sequential `001`-`456` style
- `is_alive`: false once eliminated
- `eliminated_game`: which round killed them
- `elimination_reason`: human-readable
- `survival_streak`: how many rounds they outlived

### Game (round)
A module registered into the arena. Owns its rules and its move/command
handlers. The arena owns players, pot, elimination, and voice.

- Ordered: `[red light green light, ..., next game]`
- Runs only with the still-alive players
- Produces a set of eliminations, then survivors advance

### Pot
Accumulates per elimination. Awarded either to the last survivor
(`/event conclude`) or split among survivors on a stop-vote.

### Vote
The democratic checkpoint between rounds. Survivors decide to continue
or stop. Majority rules, tie means revote. Public, not anonymous.

---

## 3. Event lifecycle

```
REGISTERING   /event open + /event join (members get numbers)
      |
      v
ONGOING       /event start (locks registration, begins round 1)
      |
      v        round plays -> losers eliminated -> pot grows
      |
      v
VOTING        survivors vote CONTINUE or STOP
      |
      +-- majority CONTINUE -> next round (ONGOING)
      |
      +-- majority STOP     -> CONCLUDED (split pot among survivors)
      |
      +-- tie               -> VOTING revote (nothing resolved)
      |
      v
CONCLUDED     one survivor remains -> winner takes whole pot
```

Terminal conditions:
1. Exactly one player remains alive - winner takes the pot.
2. Survivors vote STOP by majority - pot split among survivors.

---

## 4. The vote (clause 3)

Rules mirroring the series:

- Only **alive** players may vote.
- Vote is **public** (announced in the game hub with names), not anonymous.
- Choices: `CONTINUE` (next round) or `STOP` (split pot, end event).
- **Majority decides.** If votes tie, the vote is unresolved and reopens.
- STOP payout: pot divided among survivors.

Design note: this is the same majority-vote pattern already used by
extension requests (groupwork) and spending proposals (society). It is a
third instance of a consistent primitive, scoped to "survivors only, tie
means revote."

---

## 5. Game rounds (ordered, season 1)

Implemented status for the bot is noted per game. RLGL is the existing
`squid`/`move` implementation, to be generalised.

### 1. Red Light, Green Light  (IMPLEMENTED, to reframe as round 1)
- Doll calls "Mugunghwa kkoci pieot seumnida" then turns.
- Move while it faces away, freeze when it turns.
- Move on red light, or fail to cross in time = eliminated.
- Bot mapping: a timed state machine cycling `GREEN_LIGHT` / `RED_LIGHT`,
  `/move` advances progress, any move during `RED_LIGHT` = elimination.

### 2. Sugar Honeycombs (Dalgona)  (planned)
- Pick a shape (circle / triangle / star / umbrella) before the game.
- Carve the shape from honeycomb candy without cracking it. Crack = out.
- Bot mapping: a timed precision task; a `shape` choice + a series of
  careful actions; a "crack" event eliminates.

### 3. Tug of War  (planned)
- Two teams on elevated platforms pull a rope over a pit. Losing team out.
- Bot mapping: team formation, then an aggregated strength/timing/strategy
  resolution between the two teams; one side is fully eliminated.

### 4. Marbles  (planned)
- Players pair up (often with friends), 10 marbles each, any agreed game,
  win all 20 to survive; the loser of the pair is out.
- Bot mapping: player pairing, then a per-pair head-to-head minigame;
  one half of every pair eliminated. Odd player out passes through.

### 5. Glass Stepping Stones  (planned)
- Bridge of 18 pairs of panels: one tempered (safe), one shatters.
- Cross in vest-number order. Wrong panel = fall = out. Time limited.
- Bot mapping: ordered turns, per-step choose left/right with a known set
  of safe panels; wrong pick eliminates the jumper, reveals the safe panel.

### 6. Squid Game  (planned, final round)
- Physical offense vs defense on a squid-shaped court; final is one-on-one.
- Bot mapping: a final head-to-head showdown. Last one standing wins.

---

## 6. Domain model (proposed)

Entities and persistence, to be finalised during implementation.

```
Event
  event_id, guild_id, status, pot_amount, current_game_index,
  started_at, concluded_at, winner_id

Player
  guild_id, event_id, user_id, player_number, is_alive,
  eliminated_game_index, eliminated_at, elimination_reason,
  survival_streak

Vote
  guild_id, event_id, user_id, choice (continue|stop), voted_at
  (reset each voting round)
```

The ordered **game list** is code, not data: each game module registers
itself (name, description, round handling) into the arena. `current_game_index`
is the event's cursor into that list.

---

## 7. Design principles

1. **Elimination is game-driven and event-scoped.** Lose one round, out of
   the whole event. The "overdue task eliminates player" rule is **removed**
   - accountability and games do not touch. Homework hits your spi, never
   your life.

2. **The arena knows nothing about specific games.** It knows players, pot,
   elimination, voice, and voting. Each game declares its own rules and
   commands. Adding a game = registering a module, never editing the arena.

3. **The pot is visible, not hidden.** Every elimination announces the new
   total. The growing pot is what makes the vote-to-continue heavy.

4. **Games run in order with survivors only.** A round ignores dead players.

5. **Guard/doll voice** reuses the shared TTS core (existing `voice_service`
   / espeak), not a game-specific synthesizer.

6. **Two escape hatches.** Last survivor takes all, or survivors vote to
   split and leave. Both are first-class outcomes.

---

## 8. Open decisions

- **Pot currency**: integrate with `spi` (entry fee + bounties paid from
  the bank) or keep a separate game "won" ledger. Undecided.
- **Entry cost**: free registration, or an spi entry fee that seeds the pot.
- **Min/max players**: whether an event requires a minimum to start, and
  whether registration is capped (canonical cap is 456).

---

## 9. Command surface (target)

```
/event open            open registration
/event join            claim a player number
/event start           lock registration, begin round 1
/event status          event state, alive count, pot, current round
/event vote <continue|stop>    survivors vote (public)
/event conclude        resolve the event, payout
/game move             per-round action (RLGL first)
```

The `/guide` manifest should list the games plugin and, ideally, enumerate
the registered game rounds automatically.