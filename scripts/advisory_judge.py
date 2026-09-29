#!/usr/bin/env python3
"""Advisory Judge v1 — Record OWNER verdicts on advisories via observations.

Usage:
  python3 scripts/advisory_judge.py --open
  python3 scripts/advisory_judge.py <advisory_id> <verdict> "<note>"

Verdicts: useful | noise | false_positive | accepted_risk
Records owner observations only. Never edits advisories.
"""
import sys, os, json, uuid, re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")
VALID_VERDICTS = {"useful", "noise", "false_positive", "accepted_risk"}


def load_env():
    """Read DATABASE_URL from .env and rewrite host for local Docker bridge."""
    if not os.path.exists(ENV_FILE):
        sys.exit("ERROR: .env not found at " + ENV_FILE)
    for line in open(ENV_FILE):
        if line.startswith("DATABASE_URL="):
            val = line.split("=", 1)[1].strip()
            val = re.sub(r"@[^:]+:(\d+)", "@127.0.0.1:\1", val)
            return val
    sys.exit("ERROR: DATABASE_URL not found in .env")


def open_unadjudicated(db_url):
    """List advisories with no owner_verdict observation_type entry."""
    import subprocess
    query = """
    SELECT a.id, a.name, a.severity, a.created_at, a.summary
    FROM advisory a
    LEFT JOIN advisory_observation ao
        ON ao.advisory_id = a.id AND ao.observation_type = 'owner_verdict'
    WHERE ao.id IS NULL
    ORDER BY a.created_at DESC;
    """
    cmd = ["psql", db_url, "-t", "-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ERROR: " + r.stderr.strip())

    rows = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    if not rows:
        print("No unadjudicated advisories found.")
        return

    print("Unadjudicated advisories ({}):".format(len(rows)))
    header = "{:<40} {:<20} {:<10} {:<20} {}".format("ID", "Name", "Severity", "Created", "Summary")
    print(header)
    print("-" * 120)
    for row in rows:
        parts = [p.strip() for p in row.split("|")]
        if len(parts) >= 5:
            print("{:<40} {:<20} {:<10} {:<20} {}".format(
                parts[0], parts[1], parts[2], parts[3], parts[4]))


def record_verdict(db_url, advisory_id, verdict, note=""):
    """Record an owner verdict as an advisory_observation row."""
    if verdict not in VALID_VERDICTS:
        sys.exit("ERROR: Invalid verdict. Must be one of: " +
                 ", ".join(sorted(VALID_VERDICTS)))

    import subprocess
    oid = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    detail = json.dumps({"verdict": verdict, "note": note, "observer": "owner (Brian)"})

    # Escape single quotes in detail for SQL safety
    detail_escaped = detail.replace("'", "''")

    query = "INSERT INTO advisory_observation (id, advisory_id, observation_type, detail, created_at) VALUES ('{oid}', '{aid}', 'owner_verdict', '{detail}', '{ts}');".format(
        oid=oid, aid=advisory_id, detail=detail_escaped, ts=ts
    )

    cmd = ["psql", db_url, "-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ERROR: " + r.stderr.strip())

    print("OK: Verdict '{v}' recorded for advisory {a}".format(v=verdict, a=advisory_id))
    if note:
        print("  Note: " + note)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    db_url = load_env()

    if sys.argv[1] == "--open":
        open_unadjudicated(db_url)
        return

    if len(sys.argv) < 3:
        sys.exit("Usage: {prog} <advisory_id> <verdict> \"<note>\"".format(prog=sys.argv[0]))

    advisory_id = sys.argv[1]
    verdict = sys.argv[2]
    note = sys.argv[3] if len(sys.argv) >= 4 else ""
    record_verdict(db_url, advisory_id, verdict, note)


if __name__ == "__main__":
    main()
