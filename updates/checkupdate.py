#!/usr/bin/env python3
"""
===============================================================================
Maigret OSINT Suite - Update Checker
===============================================================================
Checks the embedded Maigret repository against upstream (https://github.com/soxoj/maigret.git).
- If an update is detected: Prints current version and updated version.
- If up-to-date: Prints current version and states that there is no update.
===============================================================================
"""

import os
import sys
import re
import subprocess
from typing import Optional, Tuple, Dict, Any

# Configure Windows console encoding for UTF-8 compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")
MAIGRET_DIR = os.path.join(TOOLS_DIR, "maigret")


def run_cmd(cmd: list, cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Run a system command and return (returncode, stdout, stderr)."""
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace"
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def extract_version_from_toml(content: str) -> str:
    """Extract version = "X.Y.Z" from pyproject.toml content."""
    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else "0.6.5"


def get_local_version_info() -> Dict[str, str]:
    """Get version, commit SHA, and commit date for local Maigret repository."""
    toml_path = os.path.join(MAIGRET_DIR, "pyproject.toml")
    version = "0.6.5"
    if os.path.exists(toml_path):
        try:
            with open(toml_path, "r", encoding="utf-8") as f:
                version = extract_version_from_toml(f.read())
        except Exception:
            pass

    code, commit, _ = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=MAIGRET_DIR)
    local_commit = commit if code == 0 and commit else "unknown"

    code, date_str, _ = run_cmd(["git", "log", "-1", "--format=%cd", "--date=short"], cwd=MAIGRET_DIR)
    commit_date = date_str if code == 0 and date_str else ""

    return {
        "version": version,
        "commit": local_commit,
        "commit_date": commit_date,
        "full_version": f"v{version} ({local_commit}{', ' + commit_date if commit_date else ''})"
    }


def get_remote_version_info() -> Optional[Dict[str, str]]:
    """Fetch remote references and extract upstream version info."""
    # Fetch latest remote commits for main without touching working files
    code, _, err = run_cmd(
        ["git", "fetch", "origin", "refs/heads/main:refs/remotes/origin/main"],
        cwd=MAIGRET_DIR
    )
    if code != 0:
        return None

    # Get remote commit hash and date
    code, commit, _ = run_cmd(["git", "rev-parse", "--short", "origin/main"], cwd=MAIGRET_DIR)
    remote_commit = commit if code == 0 and commit else "unknown"

    code, date_str, _ = run_cmd(["git", "log", "-1", "--format=%cd", "--date=short", "origin/main"], cwd=MAIGRET_DIR)
    remote_date = date_str if code == 0 and date_str else ""

    # Get remote version from upstream pyproject.toml
    remote_version = "0.6.5"
    code, toml_content, _ = run_cmd(["git", "show", "origin/main:pyproject.toml"], cwd=MAIGRET_DIR)
    if code == 0 and toml_content:
        remote_version = extract_version_from_toml(toml_content)

    return {
        "version": remote_version,
        "commit": remote_commit,
        "commit_date": remote_date,
        "full_version": f"v{remote_version} ({remote_commit}{', ' + remote_date if remote_date else ''})"
    }


def check_update():
    """Main check update routine."""
    if not os.path.exists(MAIGRET_DIR) or not os.path.exists(os.path.join(MAIGRET_DIR, ".git")):
        print("Error: Embedded Maigret repository not found in tools/maigret.")
        return

    local = get_local_version_info()
    remote = get_remote_version_info()

    if remote is None:
        print("Unable to connect to upstream repository (offline or check timed out).")
        print(f"Current version: {local['full_version']}")
        return

    # Check commit difference
    code, diff_out, _ = run_cmd(
        ["git", "rev-list", "HEAD..origin/main", "--count"],
        cwd=MAIGRET_DIR
    )
    pending_count = int(diff_out) if (code == 0 and diff_out.isdigit()) else 0

    if pending_count > 0 or local["commit"] != remote["commit"]:
        print("Update detected!")
        print(f"Current version: {local['full_version']}")
        print(f"Updated version: {remote['full_version']}")
        if pending_count > 0:
            print(f"New commits available: {pending_count}")
    else:
        print(f"Current version: {local['full_version']}")
        print("Up to date.")


if __name__ == "__main__":
    check_update()
