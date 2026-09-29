#!/usr/bin/env python3
"""Advisory Judge v1 — Record OWNER verdicts on advisories.

Usage:
  python3 scripts/advisory_judge.py --open
  python3 scripts/advisory_judge.py ADVISORY_ID VERDICT "NOTE"

Verdicts: useful | noise | false_positive | accepted_risk
Records owner observations only. Never edits advisories or generates judgments.
"""
import sys, os, json, uuid, subprocess as sp
from datetime import datetime, timezone

VALID_VERDICTS = {"useful", "noise", "false_positive", "accepted_risk"}
PSQL = ["docker", "exec", "learning-fabric-postgres",
        "psql", "-U", "fabric", "-d", "learning_fabric", "-t"]

def run_sql(query):
    cmd = PSQL + ["-c", query]
    r = sp.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("SQL ERROR: " + r.stderr.strip())
    return r.stdout

def open_unadjudicated():
    query = """
    SELECT a.id, a.reason AS summary, a.severity, a.created_at, coalesce(a.requested_action, '')
    FROM advisory a
    LEFT JOIN advisory_observation ao
        ON ao.advisory_id = a.id AND ao.observation_type = 'owner_verdict'
    WHERE ao.id IS NULL
    ORDER BY a.created_at DESC;
    """
    out = run_sql(query)
    rows = [line.strip() for line in out.splitlines() if line.strip()]
    if not rows:
        print("No unadjudicated advisories found.")
        return
    print("Unadjudicated advisories ({}):".format(len(rows)))
    print("{:<40} {:<50} {:<10} {:<20} {}".format("ID", "Reason", "Severity", "Created", "Action"))
    print("-" * 130)
    for row in rows:
        parts = [p.strip() for p in row.split("|")]
        if len(parts) >= 5:
            print("{:<40} {:<50} {:<10} {:<20} {}".format(
                parts[0], parts[1][:48], parts[2], parts[3], parts[4]))

def record_verdict(advisory_id, verdict, note=""):
    if verdict not in VALID_VERDICTS:
        sys.exit("ERROR: Invalid verdict. Must be one of: " +
                 ", ".join(sorted(VALID_VERDICTS)))
    oid = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    detail = json.dumps({"verdict": verdict, "note": note, "observer": "owner (Brian)"})
    detail_escaped = detail.replace("'", "''")
    query = ("INSERT INTO advisory_observation "
             "(id, advisory_id, observation_type, detail, created_at) "
             "VALUES ('{oid}', '{aid}', 'owner_verdict', '{detail}', '{ts}');").format(
        oid=oid, aid=advisory_id, detail=detail_escaped, ts=ts)
    run_sql(query)
    print("OK: Verdict '{v}' recorded for advisory {a}".format(v=verdict, a=advisory_id))
    if note:
        print("  Note: " + note)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if sys.argv[1] == "--open":
        open_unadjudicated()
        return
    if len(sys.argv) < 3:
        sys.exit("Usage: {prog} ADVISORY_ID VERDICT \"NOTE\"".format(prog=sys.argv[0]))
    advisory_id = sys.argv[1]
    verdict = sys.argv[2]
    note = sys.argv[3] if len(sys.argv) >= 4 else ""
    record_verdict(advisory_id, verdict, note)

if __name__ == "__main__":
    main()