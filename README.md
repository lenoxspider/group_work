# 🤖 Group Accountability Discord Bot

A clean-architecture Discord bot engineered to eliminate free-riding and miscommunication in student teams through automated task tracking, deadline countdowns, multi-tier T-minus alerts, objective contribution reporting, verified deliverable archiving, a spi economy, an entry-fee Squid Game arena, a citizen constitution with a working tribunal, bot-fired engagement pulses, and a cosmetic spi sink.

---

## 🏗️ Architecture & Clean Design

This project strictly adheres to Domain-Driven Design (DDD) and Clean Architecture principles:
- **`src/domain/`**: Pure domain aggregates (`Task`, `Deadline`, `MemberActivity`), domain exceptions (`errors.py`), and abstract repository interfaces. Zero dependencies on Discord or databases.
- **`src/application/`**: Use cases and orchestration services (`TaskService`, `DeadlineService`, `ActivityService`, `VaultService`) and typed Data Transfer Objects (DTOs).
- **`src/infrastructure/`**: Asynchronous SQLite repositories (`aiosqlite`), database connection and schema lifecycle, and local file storage vault.
- **`src/interface/`**: Discord Bot client, presentation formatters (`discord_formatters.py`), and Cogs (`tasks_cog.py`, `deadlines_cog.py`, `reports_cog.py`, `tracker_cog.py`, `admin_cog.py`). Command handlers do exactly three things: parse input → call application service → serialize Discord response.
- **`src/plugins/`**: Self-contained feature modules (`bank`, `community`, `games`, `groupwork`, `pulse`, `radio`, `shop`, `society`). Each plugin owns its schema, services, and cogs, registers itself into the bot runtime, and wires cross-plugin dependencies (e.g. the games arena escrows spi through the bank, and the shop burns spi through it). Adding a feature means one package plus one entry in `get_plugins()` - `/setup` and `/guide` both pick it up automatically.
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

### 8. 🎮 Games Arena (Squid Game Events)
A self-contained arena where the team plays entry-fee elimination games for the spi pot. The arena is game-agnostic: survivors fight for the escrowed pot, and games register as modules (currently just Round 1).

- **Channels**: `#game-hub` (active players) and `#spectators` (eliminated contestants).
- **Commands**:
  - `/event open [entry_fee:<int>]` - open registration for a new event. Entry fee defaults to `100 spi`.
  - `/event join` - pay the entry fee and claim a player number (`001`-`456`).
  - `/event start` - lock registration and begin **Round 1: Red Light Green Light**.
  - `/event status` - the escrowed pot, survivor count, and current game.
  - `/event vote <continue|stop>` - surviving players vote between rounds (scaffolded for when later games land).
  - `/event conclude` - resolve the event and pay out the pot.
  - `/move` - advance in Red Light Green Light (safe only during `GREEN LIGHT`, or tap the MOVE button).
- **Economy (zero-inflation escrow)**: entry fees transfer into a `POT` account in the bank (tax-exempt). No minting or burning - the pot is just the sum of entry fees, paid out on conclusion. Last survivor takes all, or the survivors split it evenly. On total extinction the pot carries to the next event.
- **Red Light Green Light (Round 1)**: a 5-round, timed state machine. Move on green, freeze on red. Move during red light (outside the 0.5s latency grace window) or fail to cross the 100m line before time expires, and you're eliminated with guard voice (`Player zero six seven. Eliminated.`).
- **Decoupled from accountability**: games never touch your homework. Overdue tasks hit your spi balance and the Wall of Shame, never the arena.

### 9. 🐱 Community, Citizenship & Onboarding
Members join as **catizens**; signing the constitution makes them **citizens**. Only citizens vote in `/society`, sit on a jury, or spend in `/shop`.

- **`/intro`**: a prompted four-question introduction - pick an option or write your own. Completes Task #1 and pays **+50 spi**. Posted to the private `#new-recruits` and bridged to `#town-hall`.
- **`/join`**: sign the constitution. Pays a **100 spi** stipend so a new citizen can play rather than only be fined, swaps the `Catizen` role for `Citizen`, and announces the moment to `#town-hall`.
- **`/me`**: your membership status, intro task, and wallet.
- **`/citizens setup mode:grandfather`**: enrol existing members as citizens without making them onboard.
- **Stranded-catizen recovery**: a six-hourly loop DMs anyone who finished their intro but never signed (with a one-click sign button that also works from a DM), and anyone who joined and then went silent. Citizenship is exempt from the Wall of Shame, so this is the only thing that notices.
- A reconcile pass keeps the `Citizen` role in step with the registry in both directions, so roles cannot drift from the database.

### 10. ⚖️ The Tribunal
A real court, judged by citizens rather than admins.

- **`/court accuse member:@x law:<LAW-ID> evidence:<text>`** opens a case in `#tribunal`.
- Citizens judge by reacting ✅ / ❌ on the case card, or with **`/court vote`**. The accuser and the accused are excluded from the jury. Quorum is 3; the vote window is 24h.
- **`/court defend`** (accused), **`/court evidence`** (accuser), **`/court close`** (magistrate), **`/court appeal`** (one fresh vote, 12h window), **`/court case`**, **`/court docket`**.
- Conviction burns the law's fine, scaled up for repeat offenders. A convict who cannot pay is shamed instead. False witnesses are fined 25 spi.
- **`/law list`** reads the constitution; nine founding laws are on the books.

### 11. ⚡ The Pulse
The bot is the missing player. When the hall goes quiet it fires a short moment on its own initiative, names a winner, and pays them - so the server has a heartbeat without anyone hosting.

- **Trigger**: fires only when there is an **audience** - someone must have spoken or reacted within the last 25 min - and never more than once per 2h. It used to fire on *silence*, which in practice meant firing into an empty room at 03:00 and on the first tick after every restart; unclaimed pulses just train people to ignore the channel. Each module declares its own open window.
- **Modules**, rolled at random:
  - 👁️ **Odd One Out** - *reaction* mode. One emoji in a 5×5 grid differs; first to click it wins **100 spi**.
  - 🔐 **Cipher Sprint** - *message* mode. A riddle; the first correct answer typed in chat wins **100 spi**. Answers are normalized and carry aliases, and an expired puzzle reveals its answer.
  - ⚖️ **Snap Trial** - *vote* mode. The bot charges a random citizen with a made-up crime and the jury has 5 minutes. Guilty pays **50 spi** to the treasury; innocent earns **25 spi**.
- **`/pulse status`**, **`/pulse fire`** (admin).
- Adding a module means adding one function to `src/plugins/pulse/modules.py`.

### 12. 🛍️ The Shop (the spi sink)
The economy's only sink - wealth finally has somewhere to go.

- **`/shop view`**, **`/shop buy item:<id>`**, **`/shop inventory`**.
- Eight cosmetics at 300-2,500 spi: the three marks ○ △ □, name colours, and hoisted titles.
- **Purchases burn spi into the bank's SINK**, so it leaves circulation permanently rather than moving to the treasury.
- Roles are created on demand and ordered priciest-highest, so the most expensive cosmetic a member owns wins their name colour. That needs headroom below the bot's top role; `/setup` warns when the guild has not left enough.
- Delivery is deliver-then-charge: the role is granted first and rolled back if the burn fails, so spi is never taken without delivery. Gated behind citizenship.

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
