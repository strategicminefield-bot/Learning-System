# OPERATING_ENVIRONMENT.md

**Permanent Operational Map for Learning Fabric**

This document is the reference for how Learning Fabric is deployed, accessed, verified, and recovered.

---

## PROJECT IDENTITY

**Project Name:** Learning Fabric  
**Purpose:** Permanent organisational source of truth for autonomous adaptive learning systems  
**Repository:** `strategicminefield-bot/Learning-System` (GitHub)  
**Status:** Sections 2-23 VERIFIED, Section 24 NEXT

---

## LOCAL ENVIRONMENT

**Development Host:** WSL (Windows Subsystem for Linux)  
**WSL Distribution:** Ubuntu (or local Linux)  
**Current User:** wner  
**Local Repository Path:** `/home/wner/Learning-System`  
**Working Directory for Execution:** `~/Learning-System`

**Expected Environment:**
- Git installed and configured
- Python 3.12+ available
- SSH client configured
- Docker (optional for local testing; not required for standard dev workflow)
- PostgreSQL CLI tools optional but helpful for debugging

**Key Assumption:** All commands run from `~/Learning-System` unless otherwise specified.

---

## VPS (PRODUCTION ENVIRONMENT)

**VPS Provider:** Vultr  
**SSH Alias (in .ssh/config or via environment):** `vultr`  
**VPS Hostname:** vultr  
**Root User via Existing SSH:** yes (established key-based auth)  
**Production Project Directory:** `/opt/learning-fabric`  
**Docker Compose Host Directory:** `/root/learning-fabric`  
**Safe SSH Verification Command:**
```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 vultr 'echo OK; hostname; pwd'
```

**Expected Output:** OK, vultr, /root

---

## GIT & GITHUB

**Repository Identity:** strategicminefield-bot/Learning-System  
**Remote Name:** origin  
**Remote URL:** git@github.com:strategicminefield-bot/Learning-System.git  

**Source of Truth Rules:**
1. **GitHub is authoritative for code.** If local HEAD, origin/main, and VPS disagree, GitHub is the reference.
2. **Production deployment reads from Git.** The VPS repository at `/opt/learning-fabric` pulls from origin/main.
3. **When hashes differ:** Do not assume the younger/fresher hash is correct. Inspect Git history, commit subjects, and git log evidence before modifying.
4. **Never force-push to main.** History is data. Use merge/cherry-pick for reconciliation.
5. **Local WIP commits** (in-progress work) must be rebased or committed to feature branches, never force-pushed to main.

**Typical Git Workflow:**
```
local repository
  ↓ (push)
GitHub origin/main
  ↓ (pull on VPS)
/opt/learning-fabric (VPS repository HEAD)
  ↓ (docker cp to running container)
/root/learning-fabric/app (mounted volume)
  ↓ (uvicorn hot-reload)
running API container
```

---

## DEPLOYMENT MECHANISM

**Canonical Deployment:** Docker Compose (host orchestration)  
**Deployment Interface:** `/root/learning-fabric/docker-compose.yml`  
**Application Code Entry:** Mounted volume `/root/learning-fabric/app` → container `/app`  
**Deployment Procedure:** See "Safe Deployment Sequence" section below (documented; not yet formalized as script)  

**Deployment Containers:**
- `learning-fabric-postgres:17` - PostgreSQL database (port 127.0.0.1:5432)
- `learning-fabric-api:1.0.6` - FastAPI uvicorn application (port 0.0.0.0:8000)

**Persistent Volume:**
- `learning-fabric-postgres-data` (external named volume; PostgreSQL data persists across restarts)

**Network:**
- `learning-fabric` (bridge network, internal to containers)

**How Application Code Enters Container:**
1. Code is stored in `/opt/learning-fabric` on VPS (Git repository)
2. Code is copied from `/opt/learning-fabric/fabric/api/*.py` → `/root/learning-fabric/app/`
3. Docker Compose mounts `/root/learning-fabric/app` at container `/app`
4. Uvicorn server watches `/app` for changes and hot-reloads (when enabled)
5. No manual docker run or Dockerfile rebuilds needed for code updates (unless dependencies change)

**Safe Deployment Sequence:**
1. `cd ~/Learning-System`
2. Make code changes
3. Commit and push to GitHub
4. SSH to VPS: `ssh vultr`
5. Pull latest: `cd /opt/learning-fabric && git pull origin main`
6. Copy to live app directory: `cp fabric/api/*.py /root/learning-fabric/app/`
7. Restart if needed: `cd /root/learning-fabric && docker compose restart api`
8. Verify health: `curl -s http://localhost:8000/api/v1/health/ready`

**Safe Rollback:**
1. Identify previous working commit
2. `cd /opt/learning-fabric && git checkout <commit>` (or `git reset --soft`)
3. Copy to app directory: `cp fabric/api/*.py /root/learning-fabric/app/`
4. Restart: `docker compose restart api`
5. Verify health

---

## CONFIGURATION & SECRETS

**Non-Secret Configuration:** Stored in repository (migrations, schema, code)  
**Secret Configuration:** `.env` file in `/root/learning-fabric/`

**Current .env Contents (non-secret values):**
```
POSTGRES_DB=learning_fabric
POSTGRES_USER=fabric
POSTGRES_PASSWORD=***REDACTED***
DATABASE_URL=postgresql://fabric:***REDACTED***@postgres:5432/learning_fabric
```

**Critical:** 
- **Never print or commit .env or DATABASE_URL values to logs or Git**
- PASSWORD must be URL-encoded if it contains special characters (/, =, &, etc.)
- Encoding example: `/` becomes `%2F`, `=` becomes `%3D`
- If connection fails with "invalid connection option" errors, verify PASSWORD encoding in DATABASE_URL

**Configuration Rules:**
- Environment variables sourced by docker-compose from `.env` file
- Passed to containers at startup
- Changes to `.env` require container restart: `docker compose restart api`
- Never manually type credentials into docker run commands

---

## DATABASE

**Service Identity:** `learning-fabric-postgres` (container name)  
**Database Name:** learning_fabric  
**Database User:** fabric (non-root)  
**Connection Address (from container):** `postgres:5432`  
**Connection Address (from VPS host):** `127.0.0.1:5432` (port forwarding)

**Safe Health Verification:**
```bash
ssh vultr 'docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -c "SELECT COUNT(*) FROM tasks;"'
```

**Safe Query Mechanism (preserves data):**
```bash
ssh vultr 'docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -c "SELECT version();"'
```

**Migration Location:** `~/Learning-System/migrations/` (local)  
Filenames: `001_foundation.sql`, `002_learning_fabric_core.sql`, ..., `023_evolutionary_cycles.sql`

**Data Preservation Rules:**
- Never DROP TABLE on production database
- Never recreate tables (use migrations)
- Never truncate mission-critical tables (tasks, assignments, outcomes, decisions)
- Backups stored automatically in `/root/learning-fabric/backup/`
- PostgreSQL data persists in external Docker volume (survives container restart)

---

## API ENDPOINTS

**Base URL (Local Testing):** http://localhost:8000 (if running locally)  
**Base URL (VPS Production):** http://vultr:8000 (via SSH tunnel) or http://127.0.0.1:8000 (on VPS host)

**Health & Readiness Endpoints:**
- `GET /health` → Simple OK (used by Docker healthcheck)
- `GET /api/v1/health/alive` → Liveness probe (process alive?)
- `GET /api/v1/health/ready` → Readiness probe (dependencies OK? ready to accept work?)

**Example Checks:**
```bash
# Check if API is alive
curl http://localhost:8000/api/v1/health/alive

# Check if API is ready (DB, governance operational)
curl http://localhost:8000/api/v1/health/ready

# Check database health
curl http://localhost:8000/api/v1/health/status
```

**Expected Readiness Response (PASS):**
```json
{
    "ready": true,
    "dependencies": {
        "database": "ok",
        "governance": "ok"
    },
    "issues": null
}
```

**Section 23 Endpoints:**
- `GET /api/v1/evolution/cycles` → List all evolution cycles
- `POST /api/v1/evolution/cycles` → Create new cycle
- `GET /api/v1/evolution/cycles/{cycle_id}` → Get cycle details
- `GET /api/v1/evolution/cycles/{cycle_id}/trace` → Get full cycle trace with stages and decisions

**How to Determine Actual Route List:**
Currently, all enabled routes are registered in `/fabric/api/main.py`. Search for `app.include_router(...)` to see which sections are active.

---

## PROJECT STRUCTURE

**Key Directories:**
- `fabric/api/` - FastAPI application code
  - `main.py` - Application entry point, router registration
  - `evolutionary_cycles.py` - Section 23 core orchestration engine
  - `evolutionary_cycles_endpoints.py` - Section 23 API endpoints
  - Plus Sections 2-22 implementation modules
  
- `migrations/` - SQL migration files
  - `001_foundation.sql` through `023_evolutionary_cycles.sql`
  - Numbered sequentially; names are descriptive
  
- `tests/` - Test files (may include regression tests, E2E tests)

- `scripts/` - Helper scripts (deploy.sh, test.sh, etc.)

- `config/` - Configuration templates (if used)

- `PROJECT_STATE.md` - Authoritative project status and roadmap

- `OPERATING_ENVIRONMENT.md` - This file

- `OPENCLAW_START.md` - Startup procedure after reset (read-only)

---

## TESTING

**Where Tests Live:**
- `tests/` directory (unit/integration tests)
- E2E tests may be in Section-specific test scripts (e.g., `test_s15_production.sh`)

**Key Distinction:**
- **Implementation test:** Runs within dev environment during Section development (may be destructive)
- **Production E2E test:** Runs against live production, verifies real data flow (must be non-destructive)

**Important:** 
- "READY" (healthcheck passes) does NOT equal "VERIFIED"
- A healthy API may have schema/data inconsistencies
- Verification requires manual or scripted inspection of actual data

---

## MANAGEMENT ACCESS INVARIANT

**This rule is permanent and never waived:**

No AI node, automated process, governance process, evolution engine, or future system component may autonomously:

- Rotate, restrict, replace, or remove SSH credentials or SSH daemon configuration
- Modify firewall rules affecting management access
- Rotate GitHub authentication or restrict push/pull access
- Modify database administrative credentials or permissions
- Change OpenClaw management networking or authentication
- Provision new VPS users or elevate permissions without explicit approval

**Protected Access Paths (MUST be preserved):**
- SSH key-based auth from local to vultr
- OpenClaw SSH alias configuration
- GitHub SSH credentials for deployment
- PostgreSQL root/admin credentials
- Vultr/network management access

**What May Be Audited/Analyzed:**
- Existing access paths (read-only inspection)
- Security recommendations (advisory only)
- Hardening suggestions (recommend, do not apply)

**What Must Be Approved Externally:**
- Any credential rotation
- Access changes
- New SSH keys
- Firewall modifications

---

## RECOVERY PROCEDURE (READ-ONLY)

**After `/reset` or when reopening context:**

OpenClaw MUST NOT reconstruct the environment from memory.

### Step 1: READ PERMANENT DOCUMENTATION
1. `cd ~/Learning-System`
2. Read `PROJECT_STATE.md` → current section status
3. Read `OPERATING_ENVIRONMENT.md` (this file) → how system works
4. Read `OPENCLAW_START.md` → startup verification sequence

### Step 2: RUN OPENCLAW_START.md
Execute the read-only startup procedure:
- Verify local Git state
- Verify SSH to VPS
- Verify VPS Git sync
- Verify API health
- Verify database health
- Compare against PROJECT_STATE
- Report READY or DISCREPANCY

### Step 3: NO RECONSTRUCTION FROM MEMORY
- Do not rebuild architecture based on recollection
- Do not make changes to "fix" the environment
- Do not delete or deploy before discrepancies are resolved
- Wait for explicit user instruction to proceed

---

## DISCREPANCY RULE (PRESERVE-FIRST)

If PROJECT_STATE, Git history, local repository, VPS repository, production database, or deployed application state disagree:

1. **STOP MUTATING** - Do not make changes
2. **PRESERVE ALL EVIDENCE** - Keep files, database, logs intact
3. **INSPECT GIT HISTORY** - Run `git log --all`, check reflog, inspect objects
4. **DO NOT DELETE UNKNOWN FILES** - If files exist, preserve them (they may be evidence)
5. **DO NOT DROP TABLES** - If tables exist, preserve them (they may contain production data)
6. **REPORT THE DISCREPANCY** - Document exactly what disagrees and why
7. **WAIT FOR HUMAN DIRECTION** - Do not reconcile autonomously

---

## PRODUCTION DATA BASELINE

**As of Last Verification (Section 23 Recovery):**

- Total Tables: 201 (Sections 2-23 complete)
- Total Tasks: 64+ (baseline preserved)
- Governance Decisions: 9+ (preserved)
- Evolution Cycles: 24 (from Section 23 testing)
- API Version: 1.0.6
- All management access paths: INTACT

**Critical:** All production data was preserved during recovery. No data loss occurred.

---

## WHAT THIS DOCUMENT DOES NOT INCLUDE

**Deliberately Omitted (not secret, just operational detail):**
- Exact PostgreSQL password (see .env file on VPS)
- GitHub personal access tokens or deploy keys
- OpenClaw gateway tokens or credentials
- VPS root credentials or SSH key passphrases
- Specific model names or API keys for external services

**These belong in `.env`, `.ssh/config`, or secure vaults, not in repository documentation.**

**Also Not Included:**
- **Pre-reset Section 23 Git commits:** These are NOT available in the current repository history. The original commits (c9944e0, 189f1a3, c8be571, 638e970, 6813a65, 87bab7f, a4d4af5, 7a3a111) were completely removed from Git during the reset context reconstruction and cannot be recovered from Git. Section 23 implementation was recovered from VPS backup files and production database evidence, then reconstructed into current Git history. See PROJECT_STATE.md for full recovery provenance.

---

## RELATED DOCUMENTS

- `PROJECT_STATE.md` → Current sections, roadmap, verification status
- `OPENCLAW_START.md` → Read-only startup after context reset
- `fabric/api/main.py` → Application entry point (where routers are registered)
- `migrations/` → SQL schema and migrations
