# OPENCLAW_START.md

**Deterministic Startup Verification for Learning Fabric**

After `/reset` or when reopening the session, follow this procedure **exactly and in order**. This is **READ-ONLY verification** until a discrepancy is discovered.

---

## STARTUP PROCEDURE (READ-ONLY)

### Phase 1: Context Establishment

```bash
cd ~/Learning-System
```

**Verify you are in the correct repository:**
```bash
pwd                          # Should output: /home/wner/Learning-System
git remote -v                # Should show: origin git@github.com:strategicminefield-bot/Learning-System.git
git status --short           # Should output nothing (clean working tree)
```

**If output differs: STOP. REPORT DISCREPANCY.**

---

### Phase 2: Read Permanent Documentation

**In this exact order:**

1. **Read PROJECT_STATE.md**
   ```bash
   head -100 PROJECT_STATE.md
   ```
   Verify:
   - Current section number
   - "VERIFIED" sections listed
   - "NEXT" section clearly stated
   - No contradictions with memory

2. **Read OPERATING_ENVIRONMENT.md**
   ```bash
   head -50 OPERATING_ENVIRONMENT.md
   ```
   Verify:
   - VPS is "vultr"
   - Local path is "/home/wner/Learning-System"
   - Production path is "/opt/learning-fabric"
   - All environment variables match expectations

3. **Read OPENCLAW_START.md**
   - You are reading it now; continue this procedure

**If any document is missing or corrupted: STOP. DO NOT PROCEED.**

---

### Phase 3: Verify Local Git State

```bash
echo "=== LOCAL GIT HEAD ==="
git log -1 --oneline

echo "=== BRANCHES ==="
git branch -a

echo "=== WORKING TREE ==="
git status --short
```

**Expected:**
- LOCAL HEAD: Some commit hash (note it)
- BRANCHES: `* main` (checked out), `remotes/origin/main`
- WORKING TREE: Empty (no modifications)

**If working tree has changes: STOP. DO NOT PUSH OR COMMIT ANYTHING.**

---

### Phase 4: Verify Remote State

```bash
echo "=== REMOTE BRANCHES ==="
git ls-remote origin main | awk '{print $1}'
```

**Expected:** A commit hash (record it; call it REMOTE_HEAD)

**Verify local HEAD matches remote HEAD:**
```bash
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin main | awk '{print $1}')
if [ "$LOCAL" = "$REMOTE" ]; then
  echo "LOCAL and REMOTE are synchronized ✓"
else
  echo "MISMATCH: local=$LOCAL remote=$REMOTE"
fi
```

**If mismatch and local is ahead: STOP. DO NOT PUSH; investigate.**  
**If mismatch and remote is ahead: STOP. Fetch and investigate before merging.**

---

### Phase 5: Verify SSH Access to VPS

```bash
echo "=== VPS SSH ACCESS ==="
ssh -o BatchMode=yes -o ConnectTimeout=10 vultr 'echo OK; hostname; whoami; pwd'
```

**Expected Output:**
```
OK
vultr
root
/root
```

**If this fails: SSH is broken. DO NOT PROCEED. Investigate SSH configuration.**

---

### Phase 6: Verify VPS Git State

```bash
echo "=== VPS GIT HEAD ==="
ssh vultr 'cd /opt/learning-fabric && git log -1 --oneline && echo "---" && git status --short'
```

**Expected:**
- Some commit hash (call it VPS_HEAD)
- Clean status (no output from status)

**Verify VPS HEAD matches local/remote:**
```bash
ssh vultr 'cd /opt/learning-fabric && git rev-parse HEAD'
```

**If VPS HEAD differs from LOCAL/REMOTE: STOP. REPORT DISCREPANCY before proceeding.**

---

### Phase 7: Verify API Health & Readiness

```bash
echo "=== API LIVENESS ==="
ssh vultr 'curl -s http://localhost:8000/api/v1/health/alive' | python3 -m json.tool

echo "=== API READINESS ==="
ssh vultr 'curl -s http://localhost:8000/api/v1/health/ready' | python3 -m json.tool
```

**Expected:**
- Liveness: `{"status": "alive", ...}`
- Readiness: `{"ready": true, "dependencies": {"database": "ok", "governance": "ok"}, "issues": null}`

**If readiness is FALSE or dependencies are failed: STOP. INVESTIGATE before proceeding.**

---

### Phase 8: Verify Database Health

```bash
echo "=== DATABASE CONNECTION ==="
ssh vultr 'docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema='\'\'public'\'\';"'

echo "=== BASELINE DATA ==="
ssh vultr 'docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -c "SELECT COUNT(*) FROM tasks; SELECT COUNT(*) FROM evolution_cycles;"'
```

**Expected:**
- Table count: 201 or more (Sections 2-23)
- Tasks: 64 or more
- Evolution cycles: 24 or more (from Section 23)

**If table count is significantly lower: STOP. INVESTIGATE schema/migrations.**

---

### Phase 9: Compare Against PROJECT_STATE

```bash
echo "=== CHECK PROJECT_STATE ==="
head -50 PROJECT_STATE.md | grep -E "Sections|VERIFIED|Section 23"
```

**Verify:**
- "Sections 2-23 VERIFIED" is stated (or similar)
- No section is claimed as NOT YET STARTED that shows production data
- Roadmap matches expectations

**If PROJECT_STATE contradicts observed production state: REPORT DISCREPANCY.**

---

### Phase 10: Verify Section 23 Specifically

```bash
echo "=== SECTION 23 ENDPOINTS ==="
ssh vultr 'curl -s http://localhost:8000/api/v1/evolution/cycles | python3 -m json.tool | head -20'
```

**Expected:**
- Returns JSON array of cycles
- At least one cycle present
- Cycle schema includes: cycle_id, trigger_source, status, created_at

**If no cycles or endpoint returns 404: Section 23 may not be fully deployed.**

---

## READINESS DETERMINATION

### READY (Proceed)

You are READY if ALL of the following are true:

✅ Local Git is clean and at LATEST commit  
✅ Local/Remote/VPS are at the SAME commit  
✅ SSH to vultr succeeds  
✅ API health/alive returns OK  
✅ API health/ready returns ready: true  
✅ Database connection succeeds  
✅ Baseline data (64+ tasks) is present  
✅ Evolution cycles (24+) are present  
✅ Section 23 endpoints respond correctly  
✅ PROJECT_STATE accurately describes the verified sections  
✅ No discrepancies between Git/VPS/DB state  

**Report:** "LEARNING FABRIC READY FOR WORK"

---

### DISCREPANCY DETECTED

If **ANY** of the above is false, you have found a discrepancy.

**DO NOT:**
- Attempt to "fix" the environment
- Delete files or tables
- Rebuild components
- Deploy or commit changes
- Rotate credentials
- Restart services

**DO:**
- **Document the discrepancy exactly**
- Include specific commands that showed the problem
- Include expected vs actual output
- Preserve all files and state
- **Report to user with full evidence**
- **Wait for explicit instruction**

---

## EXAMPLE: DISCREPANCY RESPONSE

**Example discrepancy:**

```
Local HEAD: abc1234
Remote HEAD: def5678
VPS HEAD: def5678

DISCREPANCY:
Local repository is 1 commit behind origin/main.

EVIDENCE:
$ git log -1 --oneline
abc1234 Fix: something
$ git ls-remote origin main
def5678

ACTION REQUIRED:
- User must decide: should local fetch latest, or is remote wrong?
- OpenClaw will NOT pull/push/force without user direction
```

---

## IF ALL SYSTEMS READY

After confirming readiness above, report:

```
========================================
LEARNING FABRIC STARTUP VERIFICATION
========================================

LOCAL GIT HEAD:    [hash from step 3]
REMOTE GIT HEAD:   [hash from step 4]
VPS GIT HEAD:      [hash from step 6]
SYNC:              ✓ ALL THREE MATCH

API HEALTH:        ✓ ALIVE & READY
DATABASE:          ✓ HEALTHY
BASELINE DATA:     ✓ PRESERVED (64 tasks)
SECTION 23:        ✓ OPERATIONAL (24 cycles)

PROJECT_STATE:     ✓ CONSISTENT

STATUS:            🟢 READY FOR WORK

NEXT:              Awaiting user instructions
========================================
```

---

## DO NOT DEVIATE FROM THIS PROCEDURE

This process is deterministic and read-only. It takes approximately 2-3 minutes.

- Do not skip steps
- Do not assume the environment is correct because you remember it
- Do not make changes until verification is complete
- Do not proceed if any step reports a problem

**If you are unsure about any output, STOP and ask for clarification.**

The purpose of this startup is to ensure you have accurate, verified information before proceeding with any work or changes.

---

## RELATED DOCUMENTS

- `OPERATING_ENVIRONMENT.md` → How the system actually works
- `PROJECT_STATE.md` → Current status and roadmap
