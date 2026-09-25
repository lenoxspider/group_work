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

### 1. 📋 Task Ledger & Interactive Buttons
- **Command**: `/task add description:<str> member:<@member> due:<YYYY-MM-DD [HH:MM]> [verifier:<@buddy>]`
- Formats and posts an interactive task card into the `#tasks` channel with persistent action buttons:
  - 🔔 **Nudge Button**: Allows teammates to ping the assignee with a built-in 30-minute spam-prevention cooldown.
  - 🔄 **In Progress Toggle**: Assignee or team admin can toggle work status between `⏳ Pending` and `🔄 In Progress`.
  - ⏳ **Extend Button**: Initiates a formal, team-voted extension request.
  - ✅ **Complete Button**: Marks the task as submitted by assignee. If no buddy verifier was assigned, credits completion and streak immediately.
  - 🔍 **Verify Button**: Accountability buddy signs off on deliverable completion, awarding completion to assignee and buddy verification bonus (`+1.0 pt`) to the verifier!
- **Dual Ownership & Buddy Pairing**:
  - Assign deliverables with `verifier:@teammate`. Two people own every deliverable.
  - Assignee marks complete; status switches to `🔍 Awaiting Buddy Verification`.
  - Designated verifier signs off via card button or `/task verify task_id:<TASK-ID>`.
- **Escalating Reminders Ladder**:
  - **Tier 1 (T-24h)**: Friendly DM reminder to the assignee (respects Quiet Hours).
  - **Tier 2 (T-6h)**: Escalation alert ping in `#tasks` notifying the team.
  - **Tier 3 (T-1h)**: High-urgency DM reminder with countdown (respects Quiet Hours).
  - **Tier 4 (Overdue)**: Public shaming card posted to `#wall-of-shame`.
- **Complete Task via Slash**: `/task complete task_id:<TASK-ID>` updates the embed.
- **Verify Task via Slash**: `/task verify task_id:<TASK-ID>` signs off as designated verifier.
- **List Tasks**: `/task list [member:<@member>]` lists open tasks across the project or for a specific teammate.

### 2. 🌙 Timezone & Quiet Hours (DND) Respect
- **Commands**:
  - `/timezone set timezone:<IANA>` (e.g. `America/New_York`, `UTC`, `Europe/London`, `Asia/Tokyo`)
  - `/timezone quiet start_hour:<0-23> end_hour:<0-23>` (e.g. `start_hour:23 end_hour:8` for 11 PM to 8 AM)
  - `/timezone view`: Inspect your active timezone, quiet hours window, and live DND status.
- **DND Respect**: The background reminder loop checks each member's designated quiet hours in their local timezone before dispatching DM reminders. Pings are held until daylight hours so members aren't disturbed at 3am.

### 3. 🗳️ Extension Requests with Democratic Majority Voting
- **Command**: `/task extend task_id:<TASK-ID> new_due:<YYYY-MM-DD [HH:MM]> reason:<TEXT>`
- Assignee requests extra time on an active deliverable, logging a transparent paper trail.
- Posts an interactive voting card into `#tasks` with `👍 Approve`, `👎 Reject`, and `🏁 Conclude Vote` buttons (`ExtensionVoteView`).
- **Quorum & Resolution**: Majority of votes cast decides the outcome. Requester cannot vote on their own request.
- **Automatic Due Date Update**: When approved, the task's due date is updated, all reminder thresholds are reset, and the assignee's on-time streak remains intact!

### 4. 🚨 Wall of Shame & On-Time Streaks
- **Channel**: `#wall-of-shame` (auto-provisioned with read-only display protection).
- **Automated Overdue Detection**: Background loop scans every 2 minutes for delinquent tasks past their due date.
- **Punishment & Shaming**: Automatically posts a public red shaming card pinging the delinquent member with elapsed overdue hours and spoken audio warning.
- **Streak Break**: Consecutive on-time streak is immediately reset to `0` (`🔥 0`) upon hitting the Wall of Shame or late delivery.

### 5. 🎙️ Voice Synthesis & Spoken Alerts (eSpeak-NG)
- **Base Command**: `/say text:<str> [tone:serious|drill_sergeant|deadpan|friendly] [lang:en-us|ru]`
  - Synthesizes arbitrary text into a `.wav` file uploaded directly to Discord with an interactive announcement card embed.
- **Voice Task Reminders**:
  - T-1h urgent reminder DMs and Wall of Shame overdue posts include an attached spoken audio clip alerting the member.
- **Voice Deadline Alerts**:
  - Milestone countdown alerts at T-24h, T-6h, and T-0 include escalating spoken audio broadcasts attached directly to the alert.
- **Voice Leaderboard Briefing**:
  - `/report voice:True`: Synthesizes an executive audio summary of the team standings, naming the top contributor and highlighting tasks needing attention.
- **Per-User Vocal Signatures**:
  - Each teammate is pinned to a deterministic voice pitch and speed offset derived from their Discord ID, allowing members to recognize by ear who is being addressed.
- **Tone & Language Presets**:
  - `serious` (clear, neutral, assertive)
  - `drill_sergeant` (fast, deep, commanding)
  - `deadpan` (flat, slow, monotonous)
  - `friendly` (upbeat, cheerful)
  - Language toggle: English (`en-us`) and Russian (`ru`).

### 3. 🎯 Deadline Countdowns & Milestone Alerts
- **Command**: `/deadline add name:<str> due:<YYYY-MM-DD HH:MM>`
- Generates a live countdown message with dynamic Discord markdown (`<t:TIMESTAMP:R>`) and pins it in `#deadlines`.
- Automatically broadcasts team `@everyone` alert pings at **T-72h**, **T-24h**, and **T-6h**.
- **Complete Deadline**: `/deadline complete deadline_id:<DL-ID>` marks milestone as finished and unpins it.
- **List Deadlines**: `/deadline list` views upcoming project milestones.

### 4. 📊 Anti-Free-Riding Reports & Military Ranks
- **Command**: `/report [member:<@member>]`
- **Team Standings**: `/report` displays a team-wide leaderboard ranking members by composite contribution score with on-time streaks (`🔥 {streak}`) and military ranks.
- **XP Military Ranks**:
  - `Comrade 🎖️` (0–9.9 pts)
  - `Sergeant 🎗️` (10–24.9 pts)
  - `Colonel ⚔️` (25–49.9 pts)
  - `Marshal 🌟` (50–99.9 pts)
  - `General Secretary 👑` (100+ pts)
- **Member Scorecard**: `/report member:@Alice` generates a detailed personal scorecard with:
  - Current rank title and badge
  - Consecutive on-time streak and personal best streak
  - On-time delivery rate percentage (`⏱️ On-Time Rate: X%`)
  - Deliverable completion rate with visual progress bar (`🟩🟩⬜⬜`)
  - Messages sent in project channels and verified file deliverables

### 5. 📥 File Deliverable Vault (`/submit`)
- **Command**: `/submit file:<attachment> [notes:<optional description>]`
- Students submit project files directly in their Discord server.
- The bot computes a SHA-256 cryptographic hash, renames the file (`draft_v1_YYYYMMDD_<hash[:8]>.ext`), archives it safely into `./uploads/`, and posts an embed card into `#submissions` with the verification details and submitter information.
- Transparent for the whole team and increments the student's `files_submitted` counter in the `/report` anti-free-riding metrics.

### 6. 🔒 Read-Only Display Protection & Auto-Setup
- **Display Protection**: `#tasks`, `#deadlines`, `#submissions`, and `#wall-of-shame` are automatically configured as **Read-Only** for members (`@everyone`).
- Eliminates chat clutter: members view cards and countdowns cleanly without distracting chatter, while interacting through slash commands and persistent buttons.
- Run `/setup` anytime to verify or enforce channel display protection.

### 7. 🚀 Project / Sprint Lifecycle (`/project`)
- **`/project status`**: Displays an active project health dashboard showing completion rates, open tasks, files submitted, and the next upcoming milestone.
- **`/project finish`**: Concludes the project sprint, updates channel topics to `[ARCHIVED]`, preserves channels in read-only mode, and posts a comprehensive **Final Project Retrospective & Contribution Report** to `#submissions`.

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
