"""
Database backup script.

What it does:
- Takes a consistent online backup of the bot database using the SQLite backup
  API, so the copy is valid even while the bot is mid-write.
- Verifies the copy with PRAGMA integrity_check and deletes it if that fails.
- Prunes old backups down to a retention window.

What it does NOT do:
- Does NOT stop the bot or lock the live database.
- Does NOT ship the copy off-box; point GROUPWORK_BACKUP_DIR at a mount if you
  want that.

Intended to be run by the groupwork-backup.timer systemd unit. Override with:
    GROUPWORK_DB, GROUPWORK_BACKUP_DIR, GROUPWORK_BACKUP_KEEP
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = os.environ.get("GROUPWORK_DB", "/opt/group_work/bot_database.sqlite")
BACKUP_DIR = os.environ.get("GROUPWORK_BACKUP_DIR", "/var/backups/groupwork")
KEEP = int(os.environ.get("GROUPWORK_BACKUP_KEEP", "14"))
PREFIX = "bot_database-"
SUFFIX = ".sqlite"


def _backup(dest: str) -> None:
    source = sqlite3.connect(DB_PATH)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _integrity_ok(path: str) -> bool:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def _prune() -> int:
    names = sorted(
        n for n in os.listdir(BACKUP_DIR) if n.startswith(PREFIX) and n.endswith(SUFFIX)
    )
    for stale in names[:-KEEP] if KEEP > 0 else names:
        os.remove(os.path.join(BACKUP_DIR, stale))
    return min(len(names), KEEP) if KEEP > 0 else 0


def main() -> int:
    if not os.path.exists(DB_PATH):
        print(f"database not found at {DB_PATH}", file=sys.stderr)
        return 1

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"{PREFIX}{stamp}{SUFFIX}")

    try:
        _backup(dest)
    except Exception as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1

    if not _integrity_ok(dest):
        os.remove(dest)
        print(f"integrity_check failed; removed {dest}", file=sys.stderr)
        return 1

    kept = _prune()
    print(f"{os.path.getsize(dest)} bytes -> {dest} (integrity ok, {kept} kept)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
