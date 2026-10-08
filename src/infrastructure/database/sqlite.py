"""Shared SQLite connection helper.

Every repository used to call ``aiosqlite.connect()`` directly. This centralises
connection setup so there is one place to tune pragmas instead of eighty-odd.

Note on the busy timeout: ``aiosqlite`` inherits ``sqlite3.connect(timeout=5.0)``,
so connections already waited 5s for a lock rather than failing instantly. Setting
it here does not change that behaviour - it makes the value explicit and tunable
in one place rather than relying on a library default.

The actual concurrency win is WAL, enabled once in ``DatabaseManager``. The
default journal mode is ``delete``, under which a writer blocks readers; this bot
has seven background loops plus user commands sharing one file.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

# How long a connection waits for a lock. Matches aiosqlite's inherited default;
# declared here so it is explicit and adjustable from one place.
BUSY_TIMEOUT_MS = 5000


async def open_connection(db_path: str) -> aiosqlite.Connection:
    """Return an open connection with the busy timeout applied.

    The caller owns the lifecycle and must close it. Prefer ``connect()`` unless
    the connection has to outlive a single ``async with`` block.
    """
    db = await aiosqlite.connect(db_path)
    try:
        await db.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    except BaseException:
        await db.close()
        raise
    return db


@asynccontextmanager
async def connect(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Drop-in replacement for ``async with aiosqlite.connect(path) as db``."""
    db = await open_connection(db_path)
    try:
        yield db
    finally:
        await db.close()
