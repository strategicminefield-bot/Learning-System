#!/usr/bin/env python3
"""Advisory watcher v1 manual — watch origin/vps-main on Learning-System.

Config (inside this file):
  repos = {"learning-system": {"path": "/opt/lf-watch/learning-system",
                               "remote": "origin", "branch": "vps-main"}}

State: /opt/lf-watch/state.json
Reports: /opt/lf-watch/reports/<YYYY-MM-DD>.log
"""
import sys, os, json, subprocess, pathlib, datetime

sys.path.insert(0, "/opt/learning-fabric")

REPOS = {
    "learning-system": {
        "path": "/opt/lf-watch/learning-system",
        "remote": "origin",
        "branch": "vps-main"
    }
}
STATE_FILE = "/opt/lf-watch/state.json"
REPORTS_DIR = "/opt/lf-watch/reports"

def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def run_git(args, cwd):
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        die("git " + " ".join(args) + " failed:\n" + r.stderr.strip())
    return r.stdout.rstrip("\n")

def run_advisory(base, head, repo_name):
    cmd = [sys.executable, "/opt/learning-fabric/scripts/advisory_run.py", base, head, repo_name]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout, r.stderr

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, datetime.datetime.utcnow().strftime("%Y-%m-%d") + ".log")

    for name, cfg in REPOS.items():
        clone_dir = cfg["path"]
        remote = cfg["remote"]
        branch = cfg["branch"]

        clone_parent = os.path.dirname(clone_dir)
        if not os.path.isdir(clone_dir):
            os.makedirs(clone_parent, exist_ok=True)
            url = "git@github-learning-system:strategicminefield-bot/Learning-System.git"
            run_git(["clone", "--bare", url, clone_dir], "/tmp")
            run_git(["fetch", remote, "refs/heads/" + branch + ":refs/heads/" + branch], clone_dir)
            print("Cloned " + name + " into " + clone_dir)

        run_git(["fetch", remote, "refs/heads/" + branch + ":refs/heads/" + branch], clone_dir)
        head = run_git(["rev-parse", branch], clone_dir)
        print(name + ": " + branch + " at " + head[:7])

        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                state = json.load(f)

        last_sha = state.get(name, {}).get("last_sha") if name in state else None

        if last_sha is None:
            state[name] = {"last_sha": head}
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
            print("Initialised state for " + name + " at " + head[:7])
            continue

        if last_sha == head:
            print("No new commits for " + name)
            continue

        stdout, stderr = run_advisory(last_sha, head, name)

        now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(report_path, "a") as f:
            f.write("=== " + now + " ===\n")
            f.write(stdout)
            if stderr:
                f.write("\nSTDERR:\n" + stderr)
            f.write("\n")

        state[name] = {"last_sha": head}
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print("Reviewed " + last_sha[:7] + ".." + head[:7] + " for " + name)

if __name__ == "__main__":
    main()