# 🤖 Group Accountability Discord Bot

An automated Discord bot engineered to manage group assignments with task tracking, deadline countdowns, automated DM reminders, and contribution reporting to eliminate free-riding and miscommunication in student teams.

---

## 🌟 Key Features

### 1. 📋 Task Ledger
- **Command:** `/task add <description> <@member> <due:YYYY-MM-DD [HH:MM]>`
- **Ledger Posting:** Automatically formats and posts an interactive task card into the `#tasks` channel.
- **Automated DM Reminders:** Assignees receive background DM reminders at **T-24 hours** and **T-1 hour**.
- **Task Completion:** `/task complete <TASK-ID>` updates the `#tasks` ledger card to finished status and credits the member's contribution score.
- **Task Listing:** `/task list [@member]` displays active responsibilities for the whole team or a filtered member.

### 2. 🎯 Deadline Countdown & Alerts
- **Command:** `/deadline add <"milestone name"> <due:YYYY-MM-DD HH:MM>`
- **Live Countdown Pin:** Generates and pins a real-time countdown card in `#deadlines` with Discord dynamic timestamps (`<t:TIMESTAMP:R>`).
- **Hourly Auto-Updates:** A background loop updates the countdown card continuously.
- **Milestone Alert Pings:** Sends `@everyone` alerts at **T-72 hours**, **T-24 hours**, and **T-6 hours**.
- **List & Complete:** `/deadline list` and `/deadline complete <DL-ID>`.

### 3. 📊 Anti-Free-Riding Contribution Reports
- **Command:** `/report [@member]`
- **Team Standings:** Running `/report` generates a team-wide activity leaderboard ranking completed tasks, message volume, and deliverables submitted.
- **Member Scorecard:** Running `/report @member` displays a detailed personal breakdown:
  - Tasks Completed vs. Pending (with visual completion bar)
  - Messages sent in project channels
  - Deliverables and files submitted
  - Last activity timestamp

### 4. 📥 File Deliverable Vault (DM Submission)
- **Direct DM Submission:** Members DM project files (drafts, reports, code, slides) directly to the bot.
- **Cryptographic Hash Verification:** The bot computes a SHA-256 hash of the upload, renames the file as `draft_v1_YYYYMMDD_<hash>.ext`, and archives it in `./uploads/`.
- **Receipt & Transparency:** Sends a DM receipt with the hash to the sender and logs an announcement in `#submissions`.
- **Activity Credit:** Increments the user's `files_submitted` counter in the contribution report.

### 5. 🛠️ Auto-Channel Setup
- Automatically creates or verifies `#tasks`, `#deadlines`, and `#submissions` when added to a server.
- Server admins can re-trigger channel setup anytime with `/setup`.
- Full command cheat-sheet available with `/guide`.

---

## 🗄️ SQLite Database Schema

The bot uses an asynchronous SQLite database (`bot_database.sqlite`) managed via `aiosqlite`:

```sql
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    guild_id TEXT,
    channel_id TEXT,
    message_id TEXT,
    description TEXT NOT NULL,
    assigned_to TEXT NOT NULL,
    due_date TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT NULL,
    reminded_24h INTEGER DEFAULT 0,
    reminded_1h INTEGER DEFAULT 0
);

CREATE TABLE deadlines (
    deadline_id TEXT PRIMARY KEY,
    guild_id TEXT,
    channel_id TEXT,
    message_id TEXT,
    name TEXT NOT NULL,
    due_datetime TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_completed INTEGER DEFAULT 0,
    reminded_72h INTEGER DEFAULT 0,
    reminded_24h INTEGER DEFAULT 0,
    reminded_6h INTEGER DEFAULT 0
);

CREATE TABLE member_activity (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    files_submitted INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    last_active TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE submissions (
    submission_id TEXT PRIMARY KEY,
    guild_id TEXT,
    user_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.14)
- Dependencies installed from `requirements.txt`:
  ```bash
  python -m pip install -r requirements.txt
  ```

### 2. Discord Developer Portal Setup
1. Visit the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and give your bot a name (e.g. `Accountability Bot`).
3. Under the **Bot** tab:
   - Click **Reset Token** and copy your bot token.
   - Under **Privileged Gateway Intents**, enable:
     - ✅ **Message Content Intent** (Required for message count tracking)
     - ✅ **Server Members Intent** (Required for member resolution)
     - ✅ **Presence Intent**
4. Under **OAuth2 -> URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions:
     - `Manage Channels` (for auto-creating `#tasks`, `#deadlines`, `#submissions`)
     - `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`
     - `Manage Messages` (for pinning countdown messages)
   - Copy the generated URL and invite the bot to your student project server.

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your values:
```env
DISCORD_BOT_TOKEN=your_token_from_step_2

# Optional: Add your server's Guild ID for instant slash command sync during dev
# Right-click your server in Discord -> Copy Server ID (Developer Mode on)
GUILD_ID=123456789012345678

TASKS_CHANNEL_NAME=tasks
DEADLINES_CHANNEL_NAME=deadlines
SUBMISSIONS_CHANNEL_NAME=submissions
DATABASE_PATH=bot_database.sqlite
```

### 4. Run the Bot
```bash
python -m bot.main
```

### 5. Running the Test Suite
Run the test suite to verify database operations, reminders logic, and helpers:
```bash
python -m unittest tests/test_database_and_helpers.py
```
