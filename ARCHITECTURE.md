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
│   │   │   ├── task.py              # Task aggregate: status transitions, reminder thresholds, buddy verifier, extension
│   │   │   ├── deadline.py          # Milestone aggregate: alert thresholds, countdown status
│   │   │   ├── member_activity.py   # Member metrics aggregate: activity score calculation, streaks, ranks
│   │   │   ├── member_preference.py # Member preference aggregate: IANA timezone, quiet hours (DND) window
│   │   │   ├── project_state.py     # Project aggregate: sprint lifecycle (ACTIVE, ARCHIVED)
│   │   │   └── extension_request.py # ExtensionRequest aggregate: peer approvals, majority resolution
│   │   └── interfaces/
│   │       ├── __init__.py
│   │       ├── task_repository.py   # TaskRepository abstract protocol/interface
│   │       ├── deadline_repository.py# DeadlineRepository abstract protocol/interface
│   │       ├── activity_repository.py# ActivityRepository abstract protocol/interface
│   │       ├── preference_repository.py# PreferenceRepository abstract protocol/interface
│   │       ├── project_repository.py # ProjectRepository abstract protocol/interface
│   │       ├── extension_repository.py# ExtensionRepository abstract protocol/interface
│   │       └── vault_storage.py     # VaultStorage abstract protocol/interface
│   │
│   ├── application/                 # USE CASES: Orchestration, DTOs
│   │   ├── __init__.py
│   │   ├── dtos/
│   │   │   ├── __init__.py
│   │   │   ├── task_dtos.py         # CreateTaskDTO, TaskResultDTO, ReminderEvaluationDTO
│   │   │   ├── deadline_dtos.py     # CreateDeadlineDTO, DeadlineResultDTO, AlertEvaluationDTO
│   │   │   ├── preference_dtos.py   # SetTimezoneDTO, SetQuietHoursDTO, MemberPreferenceDTO
│   │   │   ├── report_dtos.py       # MemberReportDTO, GuildReportDTO
│   │   │   ├── project_dtos.py      # ProjectStatusDTO, ProjectArchiveSummaryDTO
│   │   │   └── extension_dtos.py    # CreateExtensionDTO, CastVoteDTO, ExtensionResultDTO
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── task_service.py      # Task use cases (assign, buddy verify, complete, list, process reminders)
│   │       ├── deadline_service.py  # Milestone use cases (schedule, evaluate alerts, complete)
│   │       ├── activity_service.py  # Metrics use cases (record message, generate reports)
│   │       ├── preference_service.py# Preference use cases (set timezone, quiet hours, DND evaluation)
│   │       ├── voice_service.py     # Voice use cases (speech synthesis, alert scripts, report briefings)
│   │       ├── squid_service.py     # Squid Game use cases (enrollment 001-456, elimination audio, pot tally, RLGL game)
│   │       ├── vault_service.py     # Vault use cases (verify SHA-256, store, record submission)
│   │       ├── project_service.py   # Lifecycle use cases (status dashboard, finish/archive)
│   │       └── extension_service.py # Extension use cases (request, cast vote, majority conclude)
│   │
│   ├── infrastructure/              # ADAPTERS: SQLite DB, File Vault, eSpeak-NG
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py        # aiosqlite connection management & schema migrations
│   │   │   ├── task_sqlite_repo.py  # SQLite implementation of TaskRepository
│   │   │   ├── deadline_sqlite_repo.py# SQLite implementation of DeadlineRepository
│   │   │   ├── activity_sqlite_repo.py# SQLite implementation of ActivityRepository
│   │   │   ├── preference_sqlite_repo.py# SQLite implementation of PreferenceRepository
│   │   │   ├── project_sqlite_repo.py # SQLite implementation of ProjectRepository
│   │   │   ├── extension_sqlite_repo.py# SQLite implementation of ExtensionRepository
│   │   │   └── squid_sqlite_repo.py # SQLite implementation of SquidRepository (players, season, games)
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   └── local_file_vault.py  # Local filesystem implementation of VaultStorage
│   │   └── speech/
│   │       ├── __init__.py
│   │       ├── espeak_synthesizer.py# Subprocess adapter executing espeak-ng binary
│   │       ├── mock_synthesizer.py  # Standard library in-memory WAV generator for test isolation
│   │       └── attachment_deliverer.py# Discord audio file attachment delivery adapter
│   │
│   └── interface/                   # ENTRY POINTS: Discord Cogs, Embeds, Client
│       ├── __init__.py
│       ├── bot.py                   # GroupAccountabilityBot Discord client subclass
│       ├── discord_formatters.py    # Discord Embed card formatters (Hot Pink #FF0090 Squid styling)
│       └── cogs/
│           ├── __init__.py
│           ├── task_buttons.py      # Persistent TaskActionView (Nudge, In-Progress, Complete, Verify, Extend)
│           ├── extension_buttons.py # Persistent ExtensionVoteView (Approve, Reject, Conclude)
│           ├── tasks_cog.py         # /task commands, buddy verification, escalation, voice nudges & Wall of Shame loop
│           ├── preference_cog.py    # /timezone commands (set, quiet, view)
│           ├── voice_cog.py         # /say command (arbitrary speech with tone/language flags)
│           ├── squid_cog.py         # /squid (join, status, announce, eliminate, redlight), /move command
│           ├── deadlines_cog.py     # /deadline add, /deadline list, 15m countdown update loop & voice alerts
│           ├── reports_cog.py       # /report (team leaderboard, military ranks, on-time streaks & voice briefing)
│           ├── tracker_cog.py       # on_message counting & in-server /submit deliverable receiver
│           └── admin_cog.py         # /setup, /guide, read-only protection, and /project commands
│
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── domain/
│   │   │   ├── test_task_entity.py
│   │   │   ├── test_deadline_entity.py
│   │   │   ├── test_activity_entity.py
│   │   │   ├── test_preference_entity.py
│   │   │   ├── test_voice_profile.py
│   │   │   ├── test_squid_entities.py
│   │   │   ├── test_project_state_entity.py
│   │   │   └── test_extension_entity.py
│   │   └── application/
│   │       ├── test_task_service.py
│   │       ├── test_deadline_service.py
│   │       ├── test_preference_service.py
│   │       ├── test_voice_service.py
│   │       ├── test_squid_service.py
│   │       ├── test_vault_service.py
│   │       ├── test_project_service.py
│   │       └── test_extension_service.py
│   └── integration/
│       ├── repositories/
│       │   ├── test_task_repository.py
│       │   ├── test_activity_repository.py
│       │   ├── test_preference_repository.py
│       │   ├── test_project_repository.py
│       │   ├── test_extension_repository.py
│       │   └── test_squid_repository.py
│       └── speech/
│           └── test_espeak_synthesizer.py
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

### 4.4 Squid Game Player Enrollment & Elimination Flow
1. Member joins games via `/squid join` in `#game-hub`.
2. `SquidService.enroll_player(guild_id, user_id)` assigns next available sequential 3-digit identifier (`"001"` through `"456"`).
3. `SquidRepository` stores `SquidPlayer` entity in SQLite.
4. Overdue Task Elimination integration: When a task hits terminal overdue threshold in `tasks_cog.py`, `SquidService.eliminate_player(guild_id, user_id, reason="Terminal task overdue")` executes:
   - Marks player as eliminated.
   - Increases guild prize pot (+100,000,000 ₩ per eliminated player).
   - Generates masked guard elimination audio via `espeak-ng` (`-s 110 -p 15 -v en-us`, e.g., *"Player zero six seven. Eliminated."*).
   - Dispatches elimination embed styled in Squid Game Pink (`#FF0090`) to `#game-hub` with audio attachment.

### 4.5 Red Light Green Light Minigame Flow
1. Front Man or group launches game via `/squid redlight start`.
2. Dedicated game thread `#red-light-green-light` is spawned.
3. Bot plays doll voice cue: *"Green light. Advance now."* (or Korean prompt *"무궁화 꽃이 피었습니다"*). State transitions to `GREEN_LIGHT`.
4. Players execute `/move`. Each valid move during Green Light advances distance progress.
5. Bot abruptly plays warning audio: *"Red light. Remain still."* State transitions to `RED_LIGHT`.
6. Any `/move` registered while in `RED_LIGHT` immediately triggers player elimination with guard audio and pot escalation.
7. Players who reach target distance before timer expires survive and advance their `survival_streak`.

## 5. External Dependencies
- **Discord Gateway**: Connected through `discord.py` Client in `interface/bot.py`.
- **Local File System Storage**: Managed via `infrastructure/storage/local_file_vault.py`.
- **SQLite Database**: Managed via `infrastructure/database/connection.py`.
- **eSpeak-NG Binary**: Standalone speech synthesizer executing guard lines at low speed/pitch (`-s 110 -p 15`).

## 6. Open Questions & Design Decisions
- *Q: How does Squid Game integrate with the serious academic accountability tracking?*
  - **A**: It acts as an optional, high-engagement motivational layer. Academic accountability records (tasks, submissions, hashes) remain completely pristine in SQLite. In Squid Game mode, terminal overdue tasks translate into in-fiction player eliminations with masked guard audio announcements.
- *Q: What timezone is assumed if none is supplied?*
  - **A**: UTC is the system internal standard. The config specifies `DEFAULT_TIMEZONE=UTC`.
