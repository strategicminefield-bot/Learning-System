#!/usr/bin/env python3
"""Advisory runner v1 — review a git push range and record advisories in Fabric.

Usage: python3 scripts/advisory_run.py <base_sha> <head_sha>

Read-only git commands only. Exits 0 unless recording fails.
"""
import sys, os, re, subprocess, pathlib
sys.path.insert(0, "/opt/learning-fabric")

ROOT = pathlib.Path("/opt/learning-fabric")
ENV_FILE = ROOT / ".env"

def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def run_git(args):
    cmd = ["git"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if r.returncode != 0:
        err = " ".join(cmd) + "\n" + r.stderr.strip()
        die(err)
    return r.stdout.rstrip("\n")

def get_author_info(sha):
    return run_git(["log", "-1", "--format=%an <%ae>", sha])

def count_commits(base, head):
    raw = run_git(["rev-list", "--count", base + ".." + head])
    return int(raw.strip())

def count_files(base, head):
    out = run_git(["diff", "--stat", base + ".." + head])
    lines = out.strip().split("\n")
    if not lines:
        return 0
    last = lines[-1]
    m = re.search(r"(\d+)\s+files?\s+changed", last)
    return int(m.group(1)) if m else 0

def load_env():
    if not ENV_FILE.exists():
        die(".env not found at " + str(ENV_FILE))
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            val = line.split("=", 1)[1]
            val = re.sub(r"@[^:]+:(\d+)", "@127.0.0.1:\\1", val)
            return val
    die("DATABASE_URL not found in .env")

def run():
    if len(sys.argv) != 3:
        die("Usage: " + sys.argv[0] + " <base_sha> <head_sha>")
    base_sha, head_sha = sys.argv[1], sys.argv[2]
    base7 = base_sha[:7] if len(base_sha) >= 7 else base_sha
    head7 = head_sha[:7] if len(head_sha) >= 7 else head_sha

    run_git(["rev-parse", "--verify", base_sha])
    run_git(["rev-parse", "--verify", head_sha])

    author = get_author_info(head_sha)
    n_commits = count_commits(base_sha, head_sha)
    n_files = count_files(base_sha, head_sha)

    os.environ["DATABASE_URL"] = load_env()

    from fabric.api.advisory_engine import record_run, generate_advisories, list_run

    run_id = record_run(base_sha, head_sha)
    generate_advisories(run_id, base_sha, head_sha)
    report = list_run(run_id)

    sep = " "
    print("Advisory review " + base7 + ".." + head7 + " run " + run_id)
    print(sep + "Author: " + author + sep + "Commits: " + str(n_commits) + sep + "Files changed: " + str(n_files))
    print(sep + "Checks run: 3 (migration-endpoint, port-binding, dirty-tree)")

    for a in report.get("advisories", []):
        print(sep + "[" + a["severity"] + "] " + a["check_name"] + " -")
        print(sep + "  Why: " + a["reason"] + " (advisory " + a["id"] + ")")

    if not report.get("advisories"):
        print(sep + "Result: no advisories")
    else:
        print(sep + "Result: " + str(len(report["advisories"])) + " advisories")

if __name__ == "__main__":
    run()
