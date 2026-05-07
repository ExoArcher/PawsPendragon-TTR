# User Tracking & Enforcement Feature — Mermaid Flowchart

## Flowchart: User Ban Enforcement & Welcome System

```mermaid
flowchart TD
    %% Entry Points
    EP1["Discord Slash Command Invoked<br/>(bot.py:1023, 1063, 1089, 1140, 1180)<br/>e.g., /ttrinfo, /doodleinfo"]
    EP2["Console Ban Command<br/>(console_commands.py:135-136)<br/>ban &lt;id&gt; &lt;reason&gt; / unban &lt;id&gt;"]
    
    %% Ban Check Flow
    BanCheck["_reject_if_banned<br/>(bot.py:987)<br/>Check interaction.user.id"]
    IsBanned["_is_banned<br/>(bot.py:983)<br/>Query db.get_ban"]
    DBQuery1["db.get_ban<br/>(db.py:230)<br/>SELECT FROM banned_users"]
    CheckResult{User Banned?}
    RejectEph["Send Ephemeral Rejection<br/>(bot.py:1001)<br/>interaction.response.send_message<br/>reason + banned_at"]
    Block["BLOCK: Return True<br/>Command stops"]
    Allow["ALLOW: Return False<br/>Continue to welcome check"]
    
    %% Welcome DM Flow
    WelcomeCheck["_maybe_welcome<br/>(bot.py:961)<br/>Check user.id in welcomed_users"]
    AlreadyWelcomed{User Already<br/>Welcomed?}
    SendDM["Send Welcome DM<br/>(bot.py:976)<br/>user.send<br/>Early Access notice"]
    AddToSet["welcomed_users.add<br/>(bot.py:977)<br/>In-memory set update"]
    AddToDB["db.add_welcomed<br/>(bot.py:978)<br/>INSERT INTO welcomed_users"]
    DMHandleError["Catch discord.Forbidden<br/>(bot.py:980)<br/>DMs closed, skip silently"]
    SkipWelcome["Skip welcome<br/>User already known"]
    ContinueCmd["Command continues"]
    
    %% Console Ban Flow
    ConsoleBanParse["Parse args<br/>(console_commands.py:267)<br/>user_id, reason"]
    ConsoleValidate{Valid<br/>UserID?}
    ConsoleGetTime["Get current UTC time<br/>(console_commands.py:278)"]
    ConsoleAddDB["db.add_ban<br/>(console_commands.py:282)<br/>INSERT OR REPLACE banned_users"]
    ConsoleUpdateCache["Update bot._user_system.banned_users<br/>(console_commands.py:290)<br/>In-memory cache sync"]
    ConsoleAudit["db.log_audit_event<br/>(console_commands.py:297)<br/>event_type='banned_user_added'"]
    ConsoleSuccess["Print success + audit<br/>(console_commands.py:304-305)"]
    ConsoleError1["Print error + return<br/>(console_commands.py:275, 285)"]
    
    %% Console Unban Flow
    ConsoleUnbanParse["Parse args<br/>(console_commands.py:312)<br/>user_id"]
    ConsoleUnbanValidate{Valid<br/>UserID?}
    ConsoleRemoveDB["db.remove_ban<br/>(console_commands.py:321)<br/>DELETE FROM banned_users"]
    ConsoleRemoveCache["bot._user_system.banned_users.pop<br/>(console_commands.py:329)<br/>Remove from cache"]
    ConsoleUnbanAudit["db.log_audit_event<br/>(console_commands.py:333)<br/>event_type='banned_user_removed'"]
    ConsoleUnbanCheck{Row deleted?}
    ConsoleUnbanSuccess["Print success + audit<br/>(console_commands.py:341-342)"]
    ConsoleUnbanWarning["Print warning: not in list<br/>(console_commands.py:344)"]
    ConsoleUnbanError["Print error + return<br/>(console_commands.py:316, 324)"]
    
    %% Startup Flow
    StartupInit["Bot Startup<br/>(bot.py + user_system.py)"]
    LoadWelcomed["load_welcomed<br/>(db.py)<br/>SELECT FROM welcomed_users"]
    HydrateCachew["Hydrate welcomed_users set<br/>(user_system.py:60)"]
    SyncConfig["_sync_banned_users_from_config<br/>(user_system.py:72)<br/>Read BANNED_USER_IDS env"]
    LoadAllBanned["_reload_banned_users_from_db<br/>(user_system.py:119)<br/>SELECT all FROM banned_users"]
    HydrateCacheb["Hydrate banned_users dict<br/>(user_system.py:52)"]
    
    %% DB Schema
    BannedUsersTable["banned_users Table<br/>(db.py schema)<br/>Columns:<br/>user_id TEXT PK<br/>reason TEXT<br/>banned_at TEXT<br/>banned_by TEXT<br/>banned_by_id TEXT"]
    WelcomedUsersTable["welcomed_users Table<br/>(db.py schema)<br/>Columns:<br/>user_id INTEGER PK"]
    
    %% Linking
    EP1 --> BanCheck
    EP2 --> BanOrUnban{Ban or<br/>Unban?}
    BanOrUnban -->|ban| ConsoleBanParse
    BanOrUnban -->|unban| ConsoleUnbanParse
    
    BanCheck --> IsBanned
    IsBanned --> DBQuery1
    DBQuery1 --> CheckResult
    CheckResult -->|Yes| RejectEph
    RejectEph --> Block
    Block --> EndBlock["❌ REJECTED"]
    
    CheckResult -->|No| Allow
    Allow --> WelcomeCheck
    WelcomeCheck --> AlreadyWelcomed
    AlreadyWelcomed -->|Yes| SkipWelcome
    SkipWelcome --> ContinueCmd
    AlreadyWelcomed -->|No| SendDM
    SendDM --> AddToSet
    AddToSet --> AddToDB
    AddToDB --> ContinueCmd
    SendDM --> DMHandleError
    DMHandleError --> ContinueCmd
    
    ContinueCmd --> EndAllow["✅ ALLOWED"]
    
    ConsoleBanParse --> ConsoleValidate
    ConsoleValidate -->|Invalid| ConsoleError1
    ConsoleError1 --> EndError1["❌ ERROR"]
    ConsoleValidate -->|Valid| ConsoleGetTime
    ConsoleGetTime --> ConsoleAddDB
    ConsoleAddDB --> ConsoleUpdateCache
    ConsoleUpdateCache --> ConsoleAudit
    ConsoleAudit --> ConsoleSuccess
    ConsoleSuccess --> EndSuccess1["✅ BANNED"]
    
    ConsoleUnbanParse --> ConsoleUnbanValidate
    ConsoleUnbanValidate -->|Invalid| ConsoleUnbanError
    ConsoleUnbanError --> EndError2["❌ ERROR"]
    ConsoleUnbanValidate -->|Valid| ConsoleRemoveDB
    ConsoleRemoveDB --> ConsoleRemoveCache
    ConsoleRemoveCache --> ConsoleUnbanAudit
    ConsoleUnbanAudit --> ConsoleUnbanCheck
    ConsoleUnbanCheck -->|Yes| ConsoleUnbanSuccess
    ConsoleUnbanSuccess --> EndSuccess2["✅ UNBANNED"]
    ConsoleUnbanCheck -->|No| ConsoleUnbanWarning
    ConsoleUnbanWarning --> EndWarning["⚠️ NOT IN LIST"]
    
    StartupInit --> LoadWelcomed
    LoadWelcomed --> HydrateCachew
    HydrateCachew --> SyncConfig
    SyncConfig --> LoadAllBanned
    LoadAllBanned --> HydrateCacheb
    HydrateCacheb --> StartupReady["🟢 READY: In-memory caches<br/>populated from DB"]
    
    DBQuery1 --> BannedUsersTable
    LoadWelcomed --> WelcomedUsersTable
    LoadAllBanned --> BannedUsersTable
    
    style EP1 fill:#4a9eff,stroke:#001f3f,color:#fff
    style EP2 fill:#ff6b6b,stroke:#5a0a0a,color:#fff
    style BanCheck fill:#ffb700,stroke:#664d00,color:#fff
    style WelcomeCheck fill:#ffb700,stroke:#664d00,color:#fff
    style EndBlock fill:#ff4444,stroke:#660000,color:#fff
    style EndAllow fill:#44ff44,stroke:#006600,color:#fff
    style EndSuccess1 fill:#44ff44,stroke:#006600,color:#fff
    style EndSuccess2 fill:#44ff44,stroke:#006600,color:#fff
    style BannedUsersTable fill:#e6f3ff,stroke:#0066cc,color:#000
    style WelcomedUsersTable fill:#e6f3ff,stroke:#0066cc,color:#000
    style StartupReady fill:#90EE90,stroke:#228B22,color:#000
```

---

## External Dependencies

| Dependency | Purpose | Location |
|---|---|---|
| **Discord.py** | Interaction handling, DM sending, ephemeral messages | `bot.py`, `discord` module |
| **aiosqlite** | Async SQLite connection pooling | `db.py`, `Features/Core/db/` |
| **datetime, timezone** | UTC timestamp generation for ban records | `console_commands.py:20` |
| **Config** | `BANNED_USER_IDS` at startup | `Features/Core/config/config.py` |
| **DB Schema** | `banned_users` and `welcomed_users` tables | `db.py:_SCHEMA` |

---

## Key Data Flows

### 1. Ban Check on Command (Lines 987–1009, 1023–1026)
- **Trigger**: Every slash command (`/ttrinfo`, `/doodleinfo`, etc.)
- **Check**: `_is_banned()` → `db.get_ban(user_id)` → SQLite query
- **Result**: If banned, send ephemeral rejection; if not, continue to welcome check
- **Caching**: `db.get_ban()` is non-cached (always queries DB); in-memory `banned_users` dict in `user_system.py` exists but is not currently used in the command path

### 2. Welcome DM on First Command (Lines 961–981, 1026)
- **Trigger**: Immediately after ban check passes
- **Check**: `user.id in self.welcomed_users` (in-memory set)
- **Action**: If not in set, send DM, add to set, persist to DB
- **Handling**: Catches `discord.Forbidden` (DMs closed) silently

### 3. Ban Command from Console (Lines 266–306)
- **Trigger**: `ban <user_id> <reason>` console input
- **Flow**:
  1. Parse user ID and reason
  2. Get current UTC timestamp
  3. `db.add_ban()` → INSERT OR REPLACE into `banned_users`
  4. Update in-memory `bot._user_system.banned_users` cache
  5. Log audit event
  6. Print success
- **Persistence**: Writes immediately to SQLite

### 4. Unban Command from Console (Lines 311–345)
- **Trigger**: `unban <user_id>` console input
- **Flow**:
  1. Parse user ID
  2. `db.remove_ban()` → DELETE from `banned_users`
  3. Remove from in-memory `bot._user_system.banned_users` cache
  4. Log audit event
  5. Print success or warning if not in list
- **Persistence**: Deletes immediately from SQLite

### 5. Startup Initialization (user_system.py:54–70)
- **Load** `welcomed_users` set from DB
- **Sync** `BANNED_USER_IDS` from config to DB (add missing entries)
- **Load** all `banned_users` from DB into in-memory dict
- Caches are hydrated at bot startup for fast lookups

---

## Sources

### Code Files
- **bot.py** (lines 961–1009, 1023–1026, 1063–1066, 1089, 1140, 1180)
  - `_maybe_welcome()`, `_is_banned()`, `_reject_if_banned()`
  - Command decorators calling ban/welcome checks

- **console_commands.py** (lines 135–138, 266–345)
  - `_handle_ban()`, `_handle_unban()`
  - Command dispatcher

- **user_system.py** (lines 39–134)
  - `UserSystem` class
  - `load_at_startup()`, `_sync_banned_users_from_config()`, `_reload_banned_users_from_db()`

- **db.py** (lines 230–294)
  - `get_ban()`, `load_all_banned()`, `add_ban()`, `remove_ban()`, `save_banned()`
  - Database schema for `banned_users` and `welcomed_users` tables

### Configuration Files
- **.env** keys: `BANNED_USER_IDS`, `BOT_ADMIN_IDS`
- **Config** class: Frozen dataclass in `Features/Core/config/config.py`

