# 🤖 Group Accountability Discord Bot

A clean-architecture Discord bot engineered to eliminate free-riding and miscommunication in student teams through automated task tracking, deadline countdowns, multi-tier T-minus alerts, objective contribution reporting, and verified deliverable archiving.

---

## 🏗️ Architecture & Clean Design

This project strictly adheres to Domain-Driven Design (DDD) and Clean Architecture principles:
- **`src/domain/`**: Pure domain aggregates (`Task`, `Deadline`, `MemberActivity`), domain exceptions (`errors.py`), and abstract repository interfaces. Zero dependencies on Discord or databases.
- **`src/application/`**: Use cases and orchestration services (`TaskService`, `DeadlineService`, `ActivityService`, `VaultService`) and typed Data Transfer Objects (DTOs).
- **`src/infrastructure/`**: Asynchronous SQLite repositories (`aiosqlite`), database connection and schema lifecycle, and local file storage vault.
- **`src/interface/`**: Discord Bot client, presentation formatters (`discord_formatters.py`), and Cogs (`tasks_cog.py`, `deadlines_cog.py`, `reports_cog.py`, `tracker_cog.py`, `admin_cog.py`). Command handlers do exactly three things: parse input → call application service → serialize Discord response.
- **`src/config/`**: Strongly typed, validated `Settings` loaded once from environment variables.

---

## 🌟 Features

### 1. 📋 Task Ledger
- **Command**: `/task add description:<str> member:<@member> due:<YYYY-MM-DD [HH:MM]>`
- Formats and posts an interactive task card into the `#tasks` channel.
- Automatically schedules background DM reminders to the assignee at **T-24h** and **T-1h**.
- **Complete Task**: `/task complete task_id:<TASK-ID>` updates the `#tasks` embed card to completed and increments the member's completed task count.
- **List Tasks**: `/task list [member:<@member>]` lists open tasks across the project or for a specific teammate.

### 2. 🎯 Deadline Countdowns & Milestone Alerts
- **Command**: `/deadline add name:<str> due:<YYYY-MM-DD HH:MM>`
- Generates a live countdown message with dynamic Discord markdown (`<t:TIMESTAMP:R>`) and pins it in `#deadlines`.
- Automatically broadcasts team `@everyone` alert pings at **T-72h**, **T-24h**, and **T-6h**.
- **Complete Deadline**: `/deadline complete deadline_id:<DL-ID>` marks milestone as finished and unpins it.
- **List Deadlines**: `/deadline list` views upcoming project milestones.

### 3. 📊 Anti-Free-Riding Contribution Reports
- **Command**: `/report [member:<@member>]`
- **Team Standings**: `/report` displays a team-wide leaderboard ranking members by composite contribution score (completed tasks, file submissions, message frequency).
- **Member Scorecard**: `/report member:@Alice` generates a detailed personal scorecard with:
  - Task completion rate with visual progress bar (`🟩🟩⬜⬜`)
  - Messages sent in project channels
  - File deliverables submitted
  - Last activity timestamp

### 4. 📥 File Deliverable Vault (DM Submission)
- Students DM files (PDF, docx, code, zip) directly to the bot.
- The bot computes a SHA-256 hash, renames the file (`draft_v1_YYYYMMDD_<hash[:8]>.ext`), saves it into `./uploads/`, sends a verified receipt in DM, and announces the submission in `#submissions`.
- Credits the member's `files_submitted` counter in the contribution report.

### 5. 🛠️ Server Setup & Auto-Provisioning
- Automatically provisions `#tasks`, `#deadlines`, and `#submissions` when joining a server.
- Administrators can manually verify or re-create channels anytime with `/setup`.
- Full command cheat sheet available via `/guide`.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.14)
- Install dependencies:
  ```bash
  python -m pip install -r requirements.txt
  ```

### 2. Discord Developer Portal Setup
1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications).
2. Under the **Bot** tab:
   - Click **Reset Token** and copy your bot token.
   - Under **Privileged Gateway Intents**, enable:
     - ✅ **Message Content Intent**
     - ✅ **Server Members Intent**
3. Under **OAuth2 -> URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Manage Channels`, `Send Messages`, `Manage Messages`, `Embed Links`, `Attach Files`, `Read Message History`
   - Invite the bot to your group server.

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Configure your `.env`:
```env
DISCORD_BOT_TOKEN=your_bot_token_here
GUILD_ID=your_optional_server_id_for_instant_command_sync
TASKS_CHANNEL_NAME=tasks
DEADLINES_CHANNEL_NAME=deadlines
SUBMISSIONS_CHANNEL_NAME=submissions
DATABASE_PATH=bot_database.sqlite
DEFAULT_TIMEZONE=UTC
```

### 4. Running the Bot
```bash
python scripts/run.py
```

### 5. Running Tests
Run the comprehensive test suite (unit and integration tests):
```bash
python -m unittest discover -s tests -p "test_*.py"
```
