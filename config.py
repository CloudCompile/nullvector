#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v2.0 — Configuration Module

Loads settings from environment variables / .env file.
v2.0: Cost-conscious model routing, rate limiting, SQLite persistence.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# ── Discord ──────────────────────────────────────────────
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")

# ── Pollinations API ─────────────────────────────────────
POLLINATIONS_KEY: str = os.getenv("POLLINATIONS_KEY", "")
POLLINATIONS_BASE_URL: str = os.getenv("POLLINATIONS_BASE_URL", "https://gen.pollinations.ai")
POLLINATIONS_MEDIA_URL: str = os.getenv("POLLINATIONS_MEDIA_URL", "https://media.pollinations.ai")

# ── Admin IDs ────────────────────────────────────────────
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()
]

# ── Bot behaviour ────────────────────────────────────────
BOT_PREFIX: str = os.getenv("BOT_PREFIX", "!")

# ── Default model selections (v2.0: cost-conscious) ─────
DEFAULT_TEXT_MODEL: str = os.getenv("DEFAULT_TEXT_MODEL", "openai-fast")
DEFAULT_IMAGE_MODEL: str = os.getenv("DEFAULT_IMAGE_MODEL", "sana")

# ── Memory settings ──────────────────────────────────────
STM_MESSAGES: int = int(os.getenv("STM_MESSAGES", "8"))
LTM_SUMMARY_THRESHOLD: int = int(os.getenv("LTM_SUMMARY_THRESHOLD", "6"))
MAX_MEMORY: int = int(os.getenv("MAX_MEMORY", "50"))

# ── Rate limiting ────────────────────────────────────────
RATE_LIMIT_HOURLY: int = int(os.getenv("RATE_LIMIT_HOURLY", "30"))
RATE_LIMIT_DAILY: int = int(os.getenv("RATE_LIMIT_DAILY", "100"))

# ── Data paths ───────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "nullvector.db"

# ── Validation ───────────────────────────────────────────
if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
    print("WARNING: DISCORD_TOKEN is not set. Create a .env file from .env.example")
