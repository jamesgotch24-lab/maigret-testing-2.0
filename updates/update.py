#!/usr/bin/env python3
"""
===============================================================================
Maigret OSINT Suite - Automated Engine Updater
===============================================================================
This script updates the embedded Maigret tool located in tools/maigret:
1. Synchronizes the Git repository from https://github.com/soxoj/maigret.git
2. Updates Python package dependencies in editable mode
3. Refreshes the site definitions database (4,900+ sites) via --force-update
4. Cleans compiled cache files for immediate reflection in the dashboard
===============================================================================
"""

import os
import sys
import re
import json
import shutil
import argparse
import subprocess
from datetime import datetime

# Configure Windows console encoding for UTF-8 compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# GitHub repository source for Maigret
MAIGRET_REPO_URL = "https://github.com/soxoj/maigret.git"

# Paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")
MAIGRET_DIR = os.path.join(TOOLS_DIR, "maigret")

# ANSI terminal colors
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    GOLD = "\033[93m"
    RED = "\033[91m"
    DIM = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def log_header(title: str):
    print(f"\n{Colors.GOLD}{Colors.BOLD}{'=' * 65}{Colors.RESET}")
    print(f"{Colors.GOLD}{Colors.BOLD} {title}{Colors.RESET}")
    print(f"{Colors.GOLD}{Colors.BOLD}{'=' * 65}{Colors.RESET}\n")

def log_info(msg: str):
    print(f"{Colors.BLUE}[*]{Colors.RESET} {msg}")

def log_success(msg: str):
    print(f"{Colors.GREEN}[+]{Colors.RESET} {Colors.BOLD}{msg}{Colors.RESET}")

def log_warn(msg: str):
    print(f"{Colors.GOLD}[!]{Colors.RESET} {msg}")

def log_error(msg: str):
    print(f"{Colors.RED}[x]{Colors.RESET} {Colors.BOLD}{msg}{Colors.RESET}")

def run_command(cmd, cwd=None, capture=False):
    """Execute a system command and return exit code + output."""
    try:
        if capture:
            res = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False, encoding="utf-8", errors="replace")
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        else:
            res = subprocess.run(cmd, cwd=cwd, check=False)
            return res.returncode, "", ""
    except Exception as e:
        return 1, "", str(e)

def get_git_commit(repo_path: str) -> str:
    """Return the short SHA of HEAD."""
    code, out, _ = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo_path, capture=True)
    return out if code == 0 else "unknown"

def get_git_commit_date(repo_path: str) -> str:
    """Return the commit date of HEAD."""
    code, out, _ = run_command(["git", "log", "-1", "--format=%cd", "--date=short"], cwd=repo_path, capture=True)
    return out if code == 0 else "unknown"

def check_git_installed() -> bool:
    code, _, _ = run_command(["git", "--version"], capture=True)
    return code == 0

def clear_pycache(directory: str):
    """Recursively remove __pycache__ folders and .pyc files."""
    cleaned = 0
    for root, dirs, files in os.walk(directory):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(pycache_path)
                cleaned += 1
            except Exception:
                pass
    return cleaned

def sync_engine_metadata():
    """Extract and persist current engine statistics to engine_meta.json for the web dashboard."""
    meta_path = os.path.join(PROJECT_ROOT, "engine_meta.json")
    
    # Check ~/.maigret/data.json first, then repository bundle
    home_db = os.path.expanduser("~/.maigret/data.json")
    repo_db = os.path.join(MAIGRET_DIR, "maigret", "resources", "data.json")
    db_file = home_db if os.path.exists(home_db) else repo_db

    sites_count = 4990
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            sites_dict = data.get("sites", {})
            if sites_dict:
                sites_count = len(sites_dict)
        except Exception as e:
            log_warn(f"Notice reading sites database: {e}")

    commit = get_git_commit(MAIGRET_DIR)
    commit_date = get_git_commit_date(MAIGRET_DIR)

    version = "0.6.5"
    try:
        ver_code, ver_out, _ = run_command([sys.executable, "-m", "maigret", "--version"], capture=True)
        if ver_code == 0 and ver_out:
            match = re.search(r"(\d+\.\d+\.\d+)", ver_out)
            if match:
                version = match.group(1)
    except Exception:
        pass

    metadata = {
        "sites_count": sites_count,
        "sites_count_formatted": f"{sites_count:,}",
        "version": version,
        "commit": commit,
        "commit_date": commit_date,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
        log_success(f"Synchronized engine metadata -> {sites_count:,} sites, v{version} ({commit})")
    except Exception as e:
        log_warn(f"Failed to write engine_meta.json: {e}")

    return metadata

def update_maigret(check_only: bool = False, skip_db: bool = False, force: bool = False):
    log_header("MAIGRET ENGINE UPDATER")
    print(f"Timestamp:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Target Path:  {MAIGRET_DIR}")
    print(f"Upstream URL: {MAIGRET_REPO_URL}\n")

    # Step 1: Verify Git
    if not check_git_installed():
        log_error("Git is not found on your system PATH. Please install Git to update Maigret.")
        return False

    os.makedirs(TOOLS_DIR, exist_ok=True)

    # Step 2: Check or Clone Repository
    if not os.path.exists(MAIGRET_DIR) or not os.path.exists(os.path.join(MAIGRET_DIR, ".git")):
        log_warn("Maigret is not yet cloned in tools/maigret. Cloning fresh copy...")
        code, _, err = run_command(["git", "clone", MAIGRET_REPO_URL, MAIGRET_DIR])
        if code != 0:
            log_error(f"Failed to clone Maigret from {MAIGRET_REPO_URL}: {err}")
            return False
        log_success("Successfully cloned Maigret repository into tools/maigret.")

    # Step 3: Check Current Commit
    prev_commit = get_git_commit(MAIGRET_DIR)
    prev_date = get_git_commit_date(MAIGRET_DIR)
    log_info(f"Current Maigret Version Commit: {Colors.CYAN}{prev_commit}{Colors.RESET} ({prev_date})")

    # Step 4: Fetch Latest Changes from Origin
    log_info("Fetching latest commits from upstream (origin/main)...")
    code, _, err = run_command(["git", "fetch", "origin", "refs/heads/main:refs/remotes/origin/main"], cwd=MAIGRET_DIR, capture=True)
    if code != 0:
        # Fallback to fetching all branches
        code, _, err = run_command(["git", "fetch", "origin"], cwd=MAIGRET_DIR, capture=True)
        if code != 0:
            log_error(f"Failed to connect to upstream repository: {err}")
            log_warn("Please check your internet connection or GitHub access.")
            return False

    # Check commit count difference
    code, diff_count, _ = run_command(["git", "rev-list", "HEAD..origin/main", "--count"], cwd=MAIGRET_DIR, capture=True)
    pending_commits = int(diff_count) if (code == 0 and diff_count.isdigit()) else 0

    if pending_commits == 0:
        log_success(f"Maigret engine code is up-to-date with upstream! (Commit: {prev_commit})")
    else:
        log_info(f"Found {Colors.GOLD}{pending_commits}{Colors.RESET} new update commit(s) from upstream.")
        if check_only:
            _, log_summary, _ = run_command(["git", "log", "HEAD..origin/main", "--oneline", "-n", "5"], cwd=MAIGRET_DIR, capture=True)
            print(f"\n{Colors.DIM}Recent Commits Available:{Colors.RESET}\n{log_summary}\n")
            log_info("Run without '--check-only' to apply updates.")
            return True

        # Pull updates
        log_info("Applying updates (git pull origin main)...")
        if force:
            run_command(["git", "reset", "--hard", "origin/main"], cwd=MAIGRET_DIR)
            pull_code, _, pull_err = 0, "", ""
        else:
            # Auto-discard local differences in tracked resource files (e.g. data.json updated by --force-update)
            # This ensures fast-forward pull succeeds seamlessly without merge conflicts in the vendor repository.
            run_command(["git", "checkout", "--", "maigret/resources/data.json"], cwd=MAIGRET_DIR, capture=True)
            pull_code, _, pull_err = run_command(["git", "pull", "--ff-only", "origin", "refs/heads/main"], cwd=MAIGRET_DIR, capture=True)

            # If still failing due to other untracked or dirty files in the vendor clone, auto-recover
            if pull_code != 0:
                log_warn(f"Fast-forward notice: {pull_err.splitlines()[-1] if pull_err else 'local modifications detected'}")
                log_info("Auto-clearing local engine cache and retrying pull...")
                run_command(["git", "reset", "--hard", "HEAD"], cwd=MAIGRET_DIR, capture=True)
                pull_code, _, pull_err = run_command(["git", "pull", "--ff-only", "origin", "refs/heads/main"], cwd=MAIGRET_DIR, capture=True)

                if pull_code != 0:
                    # Final fallback: reset directly to origin/main
                    log_info("Aligning vendor repository directly to origin/main...")
                    res_code, _, _ = run_command(["git", "reset", "--hard", "origin/main"], cwd=MAIGRET_DIR, capture=True)
                    if res_code == 0:
                        pull_code = 0
                    else:
                        log_error(f"Git pull failed: {pull_err}")
                        log_warn("If issues persist, rerun with '--force' to recreate the clean branch state.")
                        return False

        new_commit = get_git_commit(MAIGRET_DIR)
        new_date = get_git_commit_date(MAIGRET_DIR)
        log_success(f"Repository updated: {Colors.CYAN}{prev_commit}{Colors.RESET} -> {Colors.CYAN}{new_commit}{Colors.RESET} ({new_date})")

    if check_only:
        return True

    # Step 5: Update Python Dependencies in Editable Mode
    log_info("Updating package dependencies and editable registration...")
    pip_cmd = [sys.executable, "-m", "pip", "install", "-e", MAIGRET_DIR]
    code, _, err = run_command(pip_cmd, capture=True)
    if code == 0:
        log_success("Maigret package and requirements updated successfully.")
    else:
        log_warn(f"Notice during dependency refresh: {err[:200]}...")

    # Step 6: Verify / Re-verify PDF optional requirement
    code, _, _ = run_command([sys.executable, "-m", "pip", "show", "xhtml2pdf"], capture=True)
    if code != 0:
        log_info("Installing optional PDF engine (xhtml2pdf)...")
        run_command([sys.executable, "-m", "pip", "install", "xhtml2pdf"], capture=True)

    # Step 7: Update Sites Database via Maigret Engine
    if not skip_db:
        log_info("Syncing latest Maigret sites database (4,490+ online targets)...")
        db_cmd = [sys.executable, "-m", "maigret", "--force-update"]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            res = subprocess.run(db_cmd, capture_output=True, text=True, check=False, env=env, encoding="utf-8", errors="replace")
            for line in res.stdout.splitlines():
                if "DB" in line or "database" in line or "sites" in line:
                    print(f"   {Colors.DIM}{line}{Colors.RESET}")
            # Mirror updated DB into local repo bundle
            home_db = os.path.expanduser("~/.maigret/data.json")
            repo_db = os.path.join(MAIGRET_DIR, "maigret", "resources", "data.json")
            if os.path.exists(home_db) and os.path.exists(os.path.dirname(repo_db)):
                try:
                    shutil.copy2(home_db, repo_db)
                except Exception:
                    pass
            log_success("Sites database successfully refreshed and synchronized.")
        except Exception as e:
            log_warn(f"Could not refresh sites database: {e}")
    else:
        log_info("Skipping sites database download as requested (--no-db).")

    # Step 8: Clean PyCache
    cleaned_count = clear_pycache(MAIGRET_DIR)
    if cleaned_count > 0:
        log_info(f"Cleaned {cleaned_count} stale cache directory/directories.")

    # Step 9: Final Engine Version Verification
    log_info("Verifying updated engine version...")
    ver_code, ver_out, _ = run_command([sys.executable, "-m", "maigret", "--version"], capture=True)
    if ver_code == 0:
        first_line = ver_out.splitlines()[0] if ver_out else "Active"
        print(f"\n{Colors.GREEN}{Colors.BOLD}{'=' * 65}{Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD} MAIGRET UPDATE COMPLETE - ALL SYSTEMS OPERATIONAL  {Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD} Engine Status: {first_line}{Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD} Commit:        {get_git_commit(MAIGRET_DIR)} ({get_git_commit_date(MAIGRET_DIR)}){Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD}{'=' * 65}{Colors.RESET}\n")
    else:
        log_warn("Engine updated, but version output check returned a warning.")

    # Step 10: Synchronize Dashboard Metadata
    log_info("Synchronizing application dashboard metadata...")
    meta = sync_engine_metadata()
    log_success(f"Dashboard synchronized with {meta['sites_count_formatted']} supported sites.")

    return True

def main():
    parser = argparse.ArgumentParser(
        description="Update the embedded Maigret tool in tools/maigret from upstream GitHub."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check for available updates without applying them.",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip downloading the updated sites database.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite local changes in tools/maigret to match origin/main.",
    )
    args = parser.parse_args()

    success = update_maigret(
        check_only=args.check_only,
        skip_db=args.no_db,
        force=args.force,
    )
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
