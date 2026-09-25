# Architecture Specification — Group Accountability Discord Bot

## 1. Purpose
A clean-architecture Discord bot designed to eliminate free-riding and miscommunication in student project groups by enforcing accountability through automated task tracking, deadline countdowns, multi-tier T-minus alerts, objective contribution metrics, and cryptographic deliverable verification.

## 2. Stack
- **Language**: Python 3.14
- **Runtime & Gateway Framework**: `discord.py` 2.7.1
- **Database**: SQLite 3 via `aiosqlite` 0.22.1 (async data access)
- **Configuration**: Standard library `dataclasses`, `python-dotenv` 1.2.3
- **Testing**: Python `unittest` / `unittest.mock` (isolated unit and repository integration tests)
- **Package Management**: `pip` with `requirements.txt`

## 3. Layering & Module Map

### 3.1 Layering Rules (Strict Inward Dependency Direction)
1. **Domain**: Pure business entities, value objects, domain errors, and abstract repository interfaces. Must not import from application, infrastructure, or interface. Zero third-party dependencies (no discord.py, no aiosqlite).
2. **Application**: Use-case orchestration services and Data Transfer Objects (DTOs). May import domain. Must not import infrastructure or interface.
3. **Infrastructure**: Database implementations (SQLite repositories), filesystem file vault, and external adapters. May import domain and application.
4. **Interface**: Discord Bot client, Cogs, slash commands, event handlers, and embed presentation formatters. May import application and infrastructure. Handlers only parse input, invoke application services, and serialize output.
5. **Config**: Strongly typed settings loaded and validated once at application boot.

### 3.2 Canonical Directory Tree
```text
discord_group_work/
├── ARCHITECTURE.md                  # This architecture specification document
├── README.md                        # Setup instructions, commands reference, developer guide
├── .env.example                     # Environment template with dummy values
├── .gitignore                       # Ignored files (.env, *.sqlite, uploads/*, caches)
├── requirements.txt                 # Project dependencies
├── src/
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py              # Typed configuration loaded from environment
│   │
│   ├── domain/                      # PURE CORE: Entities, errors, interfaces
│   │   ├── __init__.py
│   │   ├── errors.py                # Domain exception hierarchy (EntityNotFound, ValidationError)
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   ├── task.py              # Task aggregate: status transitions, reminder thresholds
│   │   │   ├── deadline.py          # Milestone aggregate: alert thresholds, countdown status
│   │   │   └── member_activity.py   # Member metrics aggregate: activity score calculation
│   │   └── interfaces/
│   │       ├── __init__.py
│   │       ├── task_repository.py   # TaskRepository abstract protocol/interface
│   │       ├── deadline_repository.py# DeadlineRepository abstract protocol/interface
│   │       ├── activity_repository.py# ActivityRepository abstract protocol/interface
│   │       └── vault_storage.py     # VaultStorage abstract protocol/interface
│   │
│   ├── application/                 # USE CASES: Orchestration, DTOs
│   │   ├── __init__.py
│   │   ├── dtos/
│   │   │   ├── __init__.py
│   │   │   ├── task_dtos.py         # CreateTaskDTO, TaskResultDTO, ReminderEvaluationDTO
│   │   │   ├── deadline_dtos.py     # CreateDeadlineDTO, DeadlineResultDTO, AlertEvaluationDTO
│   │   │   └── report_dtos.py       # MemberReportDTO, GuildReportDTO
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── task_service.py      # Task use cases (assign, complete, list, process reminders)
│   │       ├── deadline_service.py  # Milestone use cases (schedule, evaluate alerts, complete)
│   │       ├── activity_service.py  # Metrics use cases (record message, generate reports)
│   │       └── vault_service.py     # Vault use cases (verify SHA-256, store, record submission)
│   │
│   ├── infrastructure/              # ADAPTERS: SQLite DB, File Vault
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py        # aiosqlite connection management & schema migrations
│   │   │   ├── task_sqlite_repo.py  # SQLite implementation of TaskRepository
│   │   │   ├── deadline_sqlite_repo.py# SQLite implementation of DeadlineRepository
│   │   │   └── activity_sqlite_repo.py# SQLite implementation of ActivityRepository
│   │   └── storage/
│   │       ├── __init__.py
│   │       └── local_file_vault.py  # Local filesystem implementation of VaultStorage
│   │
│   └── interface/                   # ENTRY POINTS: Discord Cogs, Embeds, Client
│       ├── __init__.py
│       ├── bot.py                   # GroupAccountabilityBot Discord client subclass
│       ├── discord_formatters.py    # Discord Embed card formatters and relative timestamps
│       └── cogs/
│           ├── __init__.py
│           ├── tasks_cog.py         # /task add, /task complete, /task list & 2m reminder loop
│           ├── deadlines_cog.py     # /deadline add, /deadline list & 15m countdown update loop
│           ├── reports_cog.py       # /report (team leaderboard and individual scorecard)
│           ├── tracker_cog.py       # on_message counting & DM deliverable vault receiver
│           └── admin_cog.py         # /setup, /guide, and auto-channel setup on guild join
│
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── domain/
│   │   │   ├── test_task_entity.py
│   │   │   ├── test_deadline_entity.py
│   │   │   └── test_activity_entity.py
│   │   └── application/
│   │       ├── test_task_service.py
│   │       ├── test_deadline_service.py
│   │       └── test_vault_service.py
│   └── integration/
│       └── repositories/
│           ├── test_task_repository.py
│           └── test_activity_repository.py
│
├── uploads/
│   └── .gitkeep                     # Target directory for versioned, hashed deliverables
└── scripts/
    └── run.py                       # Application execution entry point
```

## 4. Data Flow

### 4.1 Task Creation (`/task add`)
1. User enters `/task add description:"Write intro" member:@Alice due:"2026-10-15 18:00"` in Discord.
2. `interface/cogs/tasks_cog.py`:
   - Validates input format and parses timezone-aware ISO string.
   - Creates `CreateTaskDTO`.
   - Calls `TaskService.create_task(dto)`.
3. `application/services/task_service.py`:
   - Instantiates `Task` domain entity with generated ID and initial state.
   - Calls `TaskRepository.save(task)`.
   - Returns `TaskResultDTO`.
4. `infrastructure/database/task_sqlite_repo.py`:
   - Persists task row in SQLite via `aiosqlite`.
5. `interface/cogs/tasks_cog.py`:
   - Formats embed card via `discord_formatters.py`.
   - Sends task message to `#tasks` channel and records `message_id`.
   - DMs assignee confirmation.
   - Replies to Discord interaction with success confirmation.

### 4.2 Background Reminders Loop (Every 2 Minutes)
1. `interface/cogs/tasks_cog.py` ticks `reminder_loop`.
2. Calls `TaskService.get_due_reminders(current_time)`.
3. `TaskService` retrieves active tasks from `TaskRepository`, evaluates domain entity reminder states (`needs_24h_reminder()`, `needs_1h_reminder()`).
4. `TaskService` returns list of `ReminderActionDTO`.
5. `tasks_cog.py` sends Discord DMs to users.
6. `tasks_cog.py` calls `TaskService.mark_reminder_sent(task_id, tier)`.
7. `TaskRepository` updates database.

### 4.3 In-Server Deliverable Vault (`/submit`)
1. Student enters `/submit file:<attachment> [notes:<optional>]` in their Discord server.
2. `interface/cogs/tracker_cog.py` validates server context and file size limit (25MB).
3. Reads file bytes, passes filename, bytes, and notes to `VaultService.store_deliverable(guild_id, user_id, filename, bytes, notes)`.
4. `VaultService` calls `VaultStorage.save(filename, bytes)` -> computes SHA-256 hash, renames as `draft_v1_YYYYMMDD_<hash>.ext`, saves to disk in `./uploads/`.
5. `VaultService` calls `ActivityRepository.record_file_submission(guild_id, user_id)`.
6. `tracker_cog.py` formats a verified submission embed via `discord_formatters.py` and posts it to `#submissions` for transparent team peer review.

## 5. External Dependencies
- **Discord Gateway**: Connected through `discord.py` Client in `interface/bot.py`.
- **Local File System Storage**: Managed via `infrastructure/storage/local_file_vault.py`.
- **SQLite Database**: Managed via `infrastructure/database/connection.py`.

## 6. Open Questions & Design Decisions
- *Q: How are deadlines refreshed in Discord without hitting rate limits?*
  - **A**: The pinned message in `#deadlines` uses Discord dynamic timestamp markdown (`<t:TIMESTAMP:R>`), which renders live client-side countdowns automatically without bot edits. The background loop performs a safety update every 15 minutes to refresh text and trigger alert pings at 72h, 24h, and 6h.
- *Q: What timezone is assumed if none is supplied?*
  - **A**: UTC is the system internal standard. The config specifies `DEFAULT_TIMEZONE=UTC`.
