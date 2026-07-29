#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v2.0 — Database Module

SQLite database for persistent conversation memory, user settings,
and generation tracking. v2.0: Replaces in-memory dict storage.
"""

from __future__ import annotations
import sqlite3
import json
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import DB_PATH, DATA_DIR


class Database:
    """Thread-safe SQLite database for NullVector v2.0."""

    def __init__(self, db_path: Path = DB_PATH):
        DATA_DIR.mkdir(exist_ok=True)
        self.db_path = str(db_path)
        self._local = threading.local()
        self._init_tables()

    # ── Connection management ────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """Get a thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_tables(self):
        """Initialize all database tables."""
        conn = self._conn()
        conn.executescript("""
            -- Conversation memory per channel
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id  TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                model_used  TEXT DEFAULT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_conv_channel ON conversations(channel_id);
            CREATE INDEX IF NOT EXISTS idx_conv_channel_time ON conversations(channel_id, created_at);

            -- User settings
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id  TEXT PRIMARY KEY,
                preferred_model  TEXT DEFAULT NULL,
                language         TEXT DEFAULT 'en',
                created_at       TEXT DEFAULT (datetime('now'))
            );

            -- Generation log (rate limiting + cost tracking)
            CREATE TABLE IF NOT EXISTS generation_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id  TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                gen_type    TEXT NOT NULL,
                model_used  TEXT NOT NULL,
                prompt_snip TEXT DEFAULT NULL,
                cost_pollen REAL DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_gen_user_time ON generation_log(user_id, created_at);

            -- LTM summaries per channel
            CREATE TABLE IF NOT EXISTS ltm_summaries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id  TEXT NOT NULL,
                summary     TEXT NOT NULL,
                msg_count   INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_ltm_channel ON ltm_summaries(channel_id);
        """)
        conn.commit()

    # ── Conversation memory ──────────────────────────────

    def add_conversation(self, channel_id: int, user_id: int, role: str,
                         content: str, model_used: str = None):
        """Add a message to conversation history."""
        conn = self._conn()
        conn.execute(
            "INSERT INTO conversations (channel_id, user_id, role, content, model_used) VALUES (?, ?, ?, ?, ?)",
            (str(channel_id), str(user_id), role, content, model_used)
        )
        conn.commit()

    def get_conversations(self, channel_id: int, limit: int = 50) -> List[Dict]:
        """Get recent conversation messages for a channel."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT role, content, model_used, created_at FROM conversations WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
            (str(channel_id), limit)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def clear_conversations(self, channel_id: int):
        """Clear all conversation history for a channel."""
        conn = self._conn()
        conn.execute("DELETE FROM conversations WHERE channel_id = ?", (str(channel_id),))
        conn.execute("DELETE FROM ltm_summaries WHERE channel_id = ?", (str(channel_id),))
        conn.commit()

    def get_conversation_count(self, channel_id: int) -> int:
        """Get the number of messages in a channel's history."""
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE channel_id = ?",
            (str(channel_id),)
        ).fetchone()
        return row["cnt"] if row else 0

    # ── LTM summaries ────────────────────────────────────

    def save_ltm_summary(self, channel_id: int, summary: str, msg_count: int):
        """Save a long-term memory summary for a channel."""
        conn = self._conn()
        conn.execute(
            "INSERT INTO ltm_summaries (channel_id, summary, msg_count) VALUES (?, ?, ?)",
            (str(channel_id), summary, msg_count)
        )
        conn.commit()

    def get_latest_ltm_summary(self, channel_id: int) -> Optional[str]:
        """Get the most recent LTM summary for a channel."""
        conn = self._conn()
        row = conn.execute(
            "SELECT summary FROM ltm_summaries WHERE channel_id = ? ORDER BY id DESC LIMIT 1",
            (str(channel_id),)
        ).fetchone()
        return row["summary"] if row else None

    # ── Generation tracking ──────────────────────────────

    def log_generation(self, channel_id: int, user_id: int, gen_type: str,
                       model_used: str, prompt_snip: str = None, cost_pollen: float = 0):
        """Log a generation for rate limiting and cost tracking."""
        conn = self._conn()
        conn.execute(
            "INSERT INTO generation_log (channel_id, user_id, gen_type, model_used, prompt_snip, cost_pollen) VALUES (?, ?, ?, ?, ?, ?)",
            (str(channel_id), str(user_id), gen_type, model_used, prompt_snip, cost_pollen)
        )
        conn.commit()

    def get_generation_count(self, user_id: int, hours: int = 1) -> int:
        """Get the number of generations by a user in the last N hours."""
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM generation_log WHERE user_id = ? AND created_at >= datetime('now', ?)",
            (str(user_id), f"-{hours} hours")
        ).fetchone()
        return row["cnt"] if row else 0

    def get_daily_cost(self, user_id: int) -> float:
        """Get total pollen cost for a user today."""
        conn = self._conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_pollen), 0) as total FROM generation_log WHERE user_id = ? AND created_at >= datetime('now', '-24 hours')",
            (str(user_id),)
        ).fetchone()
        return row["total"] if row else 0.0

    # ── User settings ────────────────────────────────────

    def get_user_setting(self, user_id: int, key: str, default=None):
        """Get a user setting."""
        conn = self._conn()
        row = conn.execute(
            f"SELECT {key} FROM user_settings WHERE user_id = ?",
            (str(user_id),)
        ).fetchone()
        return row[key] if row and row[key] is not None else default

    def set_user_setting(self, user_id: int, key: str, value: str):
        """Set a user setting."""
        conn = self._conn()
        # Upsert
        conn.execute(
            "INSERT INTO user_settings (user_id, {col}) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET {col} = ?".format(col=key),
            (str(user_id), value, value)
        )
        conn.commit()
