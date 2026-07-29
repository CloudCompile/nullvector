#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════
  Lily v8.5 & NullVector v2.0 — Pterodactyl All-in-One Startup
═══════════════════════════════════════════════════════════════════

  Upload this file to your Pterodactyl server (HidenCloud etc.)
  Set your startup command to:  python startup.py

  Set these environment variables in the Pterodactyl "Startup" tab:
    BOT                  = lily | nullvector | both
    LILY_DISCORD_TOKEN   = your Lily bot token
    NV_DISCORD_TOKEN     = your NullVector bot token
    LILY_POLLINATIONS_KEY= your Pollinations key (or leave blank for free tier)
    NV_POLLINATIONS_KEY  = your Pollinations key (or leave blank for free tier)
    ADMIN_IDS            = your Discord user ID (comma-separated)

  That's it. The script does everything else:
    ✅ Clones repos from GitHub
    ✅ Installs pip dependencies
    ✅ Creates .env files
    ✅ Creates data directories
    ✅ Starts the bot(s)
    ✅ Auto-restarts on crash
    ✅ Survives Pterodactyl container restarts (won't re-clone)

═══════════════════════════════════════════════════════════════════
"""

import os
import sys
import subprocess
import shutil
import zipfile
import io
import urllib.request
import urllib.error
import time
import signal
import json
from pathlib import Path

# ────────────────────────────────────────────────────────────────
#  CONFIGURATION — change these if you want hard-coded values
#  instead of Pterodactyl environment variables
# ────────────────────────────────────────────────────────────────

BOT = os.environ.get("BOT", "lily").lower().strip()

LILY_DISCORD_TOKEN    = os.environ.get("LILY_DISCORD_TOKEN", "")
NV_DISCORD_TOKEN      = os.environ.get("NV_DISCORD_TOKEN", "")
LILY_POLLINATIONS_KEY = os.environ.get("LILY_POLLINATIONS_KEY", "sk_yqlTb7e7zyZCF7AkJ9GYcOfWhFLlB7zw")
NV_POLLINATIONS_KEY   = os.environ.get("NV_POLLINATIONS_KEY", "sk_yqlTb7e7zyZCF7AkJ9GYcOfWhFLlB7zw")
ADMIN_IDS             = os.environ.get("ADMIN_IDS", "")

# GitHub repos (public, no auth needed to clone)
LILY_REPO = "https://github.com/cloudcompile/Lily.git"
NV_REPO   = "https://github.com/cloudcompile/nullvector.git"

# GitHub ZIP URLs (fallback if git is not installed)
LILY_ZIP = "https://github.com/cloudcompile/Lily/archive/refs/heads/main.zip"
NV_ZIP   = "https://github.com/cloudcompile/nullvector/archive/refs/heads/main.zip"

# Working directory inside Pterodactyl container
WORK_DIR = os.environ.get("HOME", "/home/container")

# ────────────────────────────────────────────────────────────────
#  HELPERS
# ────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
YELLOW= "\033[93m"
RESET = "\033[0m"

def log(msg, color=GREEN):
    print(f"{color}{BOLD}[Lily/NV Setup]{RESET} {msg}")

def warn(msg):
    print(f"{YELLOW}{BOLD}[Warning]{RESET} {msg}")

def error(msg):
    print(f"{RED}{BOLD}[Error]{RESET} {msg}")

def run(cmd, check=False, capture=False):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, shell=True,
            capture_output=capture,
            text=True,
            timeout=300,
        )
        if check and result.returncode != 0:
            error(f"Command failed: {cmd}")
            if capture and result.stderr:
                error(result.stderr.strip())
            sys.exit(1)
        return result
    except subprocess.TimeoutExpired:
        error(f"Command timed out: {cmd}")
        return None
    except Exception as e:
        error(f"Command error: {e}")
        return None

def has_git():
    """Check if git is available."""
    result = run("which git", capture=True)
    return result and result.returncode == 0

def clone_or_pull(repo_url, target_dir, branch="main"):
    """Clone a repo, or pull if it already exists."""
    if os.path.isdir(os.path.join(target_dir, ".git")):
        log(f"Pulling updates for {target_dir}...")
        run(f"cd {target_dir} && git fetch --all && git reset --hard origin/{branch}", check=False)
        return True
    else:
        log(f"Cloning {repo_url} into {target_dir}...")
        result = run(f"git clone -b {branch} {repo_url} {target_dir}", check=False)
        return result and result.returncode == 0

def download_zip(zip_url, target_dir, repo_name):
    """Download a GitHub repo as ZIP and extract it (fallback when git isn't available)."""
    # If the directory already exists and has files, skip
    if os.path.isdir(target_dir) and os.listdir(target_dir):
        log(f"{target_dir} already exists, skipping download.")
        return True

    log(f"Downloading {repo_name} from {zip_url}...")
    try:
        req = urllib.request.Request(zip_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_data = resp.read()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # GitHub ZIPs have a top-level dir like "Lily-main/"
            # We extract and then move contents up
            extract_to = f"{target_dir}_tmp"
            zf.extractall(extract_to)

            # Find the top-level dir inside the ZIP
            top_dir = None
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) > 1:
                    top_dir = parts[0]
                    break

            if top_dir:
                src = os.path.join(extract_to, top_dir)
                os.makedirs(target_dir, exist_ok=True)
                # Move all contents up
                for item in os.listdir(src):
                    shutil.move(os.path.join(src, item), os.path.join(target_dir, item))
                shutil.rmtree(extract_to, ignore_errors=True)
            else:
                # Fallback: just rename
                shutil.move(extract_to, target_dir)

        log(f"Downloaded {repo_name} successfully!")
        return True

    except Exception as e:
        error(f"Failed to download {repo_name}: {e}")
        return False

def install_deps(target_dir):
    """Install pip dependencies from requirements.txt."""
    req_file = os.path.join(target_dir, "requirements.txt")
    if not os.path.exists(req_file):
        warn(f"No requirements.txt found in {target_dir}")
        return

    log(f"Installing dependencies from {req_file}...")
    run(f"pip install -q -r {req_file}", check=False)

def create_lily_env(target_dir):
    """Create .env file for Lily v8.5."""
    env_path = os.path.join(target_dir, ".env")
    if os.path.exists(env_path):
        log(f"Lily .env already exists, skipping creation.")
        return

    log(f"Creating Lily .env file...")
    content = f"""# Lily v8.5 Configuration — Auto-generated by startup.py

# ── Discord ──────────────────────────────────────────────
DISCORD_TOKEN={LILY_DISCORD_TOKEN}

# ── Pollinations API ─────────────────────────────────────
POLLINATIONS_KEY={LILY_POLLINATIONS_KEY}
POLLINATIONS_BASE_URL=https://gen.pollinations.ai
POLLINATIONS_MEDIA_URL=https://media.pollinations.ai

# ── Admin IDs (comma-separated) ──────────────────────────
ADMIN_IDS={ADMIN_IDS}

# ── Bot behaviour ────────────────────────────────────────
BOT_PREFIX=!lily

# ── Default models (v8.5: cheap models by default!) ──────
DEFAULT_TEXT_MODEL=openai-fast
DEFAULT_IMAGE_MODEL=sana

# ── v8.5 Features ────────────────────────────────────────
PROACTIVE_DM_ENABLED=true
PROACTIVE_DM_CHECK_INTERVAL=300
DAILY_RECAP_ENABLED=true
DAILY_RECAP_HOUR=23
DREAM_JOURNAL_ENABLED=true
DREAM_JOURNAL_HOUR=3
MOOD_STATUS_ENABLED=true
MOOD_STATUS_INTERVAL=300
"""
    with open(env_path, "w") as f:
        f.write(content)
    log(f"Created {env_path}")

def create_nv_env(target_dir):
    """Create .env file for NullVector v2.0."""
    env_path = os.path.join(target_dir, ".env")
    if os.path.exists(env_path):
        log(f"NullVector .env already exists, skipping creation.")
        return

    log(f"Creating NullVector .env file...")
    content = f"""# NullVector v2.0 Configuration — Auto-generated by startup.py

# ── Discord ──────────────────────────────────────────────
DISCORD_TOKEN={NV_DISCORD_TOKEN}

# ── Pollinations API ─────────────────────────────────────
POLLINATIONS_KEY={NV_POLLINATIONS_KEY}
POLLINATIONS_BASE_URL=https://gen.pollinations.ai
POLLINATIONS_MEDIA_URL=https://media.pollinations.ai

# ── Admin IDs (comma-separated) ──────────────────────────
ADMIN_IDS={ADMIN_IDS}

# ── Bot behaviour ────────────────────────────────────────
BOT_PREFIX=!

# ── Default models (v2.0: cost-conscious routing) ───────
DEFAULT_TEXT_MODEL=openai-fast
DEFAULT_IMAGE_MODEL=sana

# ── Memory settings ──────────────────────────────────────
STM_MESSAGES=8
LTM_SUMMARY_THRESHOLD=6
MAX_MEMORY=50

# ── Rate limiting ────────────────────────────────────────
RATE_LIMIT_HOURLY=30
RATE_LIMIT_DAILY=100
"""
    with open(env_path, "w") as f:
        f.write(content)
    log(f"Created {env_path}")

def create_data_dir(target_dir):
    """Create the data directory for SQLite databases."""
    data_dir = os.path.join(target_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    log(f"Data directory ready: {data_dir}")

# ────────────────────────────────────────────────────────────────
#  BOT SETUP
# ────────────────────────────────────────────────────────────────

def setup_lily():
    """Set up Lily v8.5."""
    log(f"{CYAN}═══ Setting up Lily v8.5 ═══{RESET}")

    # The Lily repo has a nested structure: Lily/Lily/bot.py
    repo_dir = os.path.join(WORK_DIR, "Lily")     # git clone target
    lily_dir = os.path.join(repo_dir, "Lily")      # actual bot code

    # Clone or download
    if has_git():
        clone_or_pull(LILY_REPO, repo_dir)
    else:
        warn("git not found, downloading ZIP instead...")
        download_zip(LILY_ZIP, repo_dir, "Lily")

    if not os.path.isdir(lily_dir):
        # Fallback: maybe the repo doesn't have the nested structure
        if os.path.exists(os.path.join(repo_dir, "bot.py")):
            lily_dir = repo_dir
        else:
            error(f"Lily bot directory not found at {lily_dir} — something went wrong!")
            sys.exit(1)

    # Install dependencies
    install_deps(lily_dir)

    # Create .env
    create_lily_env(lily_dir)

    # Create data dir
    create_data_dir(lily_dir)

    log(f"Lily v8.5 setup complete!")
    return lily_dir

def setup_nullvector():
    """Set up NullVector v2.0."""
    log(f"{CYAN}═══ Setting up NullVector v2.0 ═══{RESET}")

    nv_dir = os.path.join(WORK_DIR, "nullvector")

    # Clone or download
    if has_git():
        clone_or_pull(NV_REPO, nv_dir)
    else:
        warn("git not found, downloading ZIP instead...")
        download_zip(NV_ZIP, nv_dir, "NullVector")

    if not os.path.isdir(nv_dir):
        error(f"NullVector directory not found at {nv_dir} — something went wrong!")
        sys.exit(1)

    # Install dependencies
    install_deps(nv_dir)

    # Create .env
    create_nv_env(nv_dir)

    # Create data dir
    create_data_dir(nv_dir)

    log(f"NullVector v2.0 setup complete!")
    return nv_dir

# ────────────────────────────────────────────────────────────────
#  BOT RUNNER
# ────────────────────────────────────────────────────────────────

def run_bot(name, bot_dir, bot_script="bot.py"):
    """Run a bot and return its process."""
    script_path = os.path.join(bot_dir, bot_script)
    if not os.path.exists(script_path):
        error(f"Bot script not found: {script_path}")
        return None

    log(f"Starting {name} from {script_path}...")
    try:
        proc = subprocess.Popen(
            [sys.executable, bot_script],
            cwd=bot_dir,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return proc
    except Exception as e:
        error(f"Failed to start {name}: {e}")
        return None

def run_with_restart(name, bot_dir, bot_script="bot.py", max_restarts=5):
    """Run a bot with auto-restart on crash."""
    restarts = 0
    while restarts < max_restarts:
        proc = run_bot(name, bot_dir, bot_script)
        if proc is None:
            error(f"Could not start {name}, giving up.")
            break

        proc.wait()
        exit_code = proc.returncode

        if exit_code == 0:
            log(f"{name} shut down cleanly.")
            break

        restarts += 1
        warn(f"{name} crashed (exit code {exit_code}). Restarting ({restarts}/{max_restarts})...")
        time.sleep(5)

    if restarts >= max_restarts:
        error(f"{name} crashed too many times. Stopping.")

# ────────────────────────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────────────────────────

def main():
    print()
    print(f"{BOLD}{'═' * 60}")
    print(f"  Lily v8.5 & NullVector v2.0 — Pterodactyl Startup")
    print(f"{'═' * 60}{RESET}")
    print()

    # Change to working directory
    os.chdir(WORK_DIR)
    log(f"Working directory: {WORK_DIR}")

    # Validate BOT choice
    if BOT not in ("lily", "nullvector", "both"):
        error(f"Invalid BOT value: '{BOT}'")
        error("Set BOT environment variable to: lily, nullvector, or both")
        sys.exit(1)

    log(f"Mode: {BOT}")

    # ── Validate tokens ──────────────────────────────────────
    if BOT in ("lily", "both") and not LILY_DISCORD_TOKEN:
        error("LILY_DISCORD_TOKEN is not set!")
        error("Set it in the Pterodactyl Startup tab as an environment variable,")
        error("or edit this script and hard-code it in the CONFIGURATION section.")
        sys.exit(1)

    if BOT in ("nullvector", "both") and not NV_DISCORD_TOKEN:
        error("NV_DISCORD_TOKEN is not set!")
        error("Set it in the Pterodactyl Startup tab as an environment variable,")
        error("or edit this script and hard-code it in the CONFIGURATION section.")
        sys.exit(1)

    # ── Make sure pip is up to date ──────────────────────────
    log("Updating pip...")
    run(f"{sys.executable} -m pip install -q --upgrade pip", check=False)

    # ── Setup bots ───────────────────────────────────────────
    lily_dir = None
    nv_dir = None

    if BOT in ("lily", "both"):
        lily_dir = setup_lily()

    if BOT in ("nullvector", "both"):
        nv_dir = setup_nullvector()

    # ── Print summary ────────────────────────────────────────
    print()
    log(f"{BOLD}Setup complete!{RESET}")
    print()
    if lily_dir:
        log(f"Lily v8.5  →  {lily_dir}")
    if nv_dir:
        log(f"NullVector v2.0  →  {nv_dir}")
    print()

    # ── Start bots ───────────────────────────────────────────
    if BOT == "both":
        # Run both bots concurrently
        import threading

        lily_thread = threading.Thread(
            target=run_with_restart,
            args=("Lily", lily_dir),
            daemon=True,
        )
        nv_thread = threading.Thread(
            target=run_with_restart,
            args=("NullVector", nv_dir),
            daemon=True,
        )

        lily_thread.start()
        nv_thread.start()

        # Keep main thread alive
        try:
            while lily_thread.is_alive() or nv_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            log("Shutting down...")

    elif BOT == "lily":
        run_with_restart("Lily", lily_dir)

    elif BOT == "nullvector":
        run_with_restart("NullVector", nv_dir)


if __name__ == "__main__":
    main()
