"""Chronicle domain - the kinds of entry the state records.

Kinds are stable identifiers so the digest can tally them; the human-readable
text is composed by whoever records the entry, because only they have the
context (who was convicted, under which law, for how much).
"""

CITIZEN_SIGNED = "citizen_signed"
COURT_VERDICT = "court_verdict"
GAMES_CONCLUDED = "games_concluded"
SNAP_TRIAL = "snap_trial"
LAW_ENACTED = "law_enacted"
LAW_REPEALED = "law_repealed"
PROPOSAL_CONCLUDED = "proposal_concluded"
