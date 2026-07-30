#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v3.0 — Rate Limiter

Per-user rate limiting for API generations.
"""

from __future__ import annotations
from datetime import datetime
from typing import Dict, Tuple

from config import RATE_LIMIT_HOURLY, RATE_LIMIT_DAILY


class RateLimiter:
    """Simple per-user rate limiter."""

    def __init__(self, db):
        self.db = db

    def can_generate(self, user_id: int) -> Tuple[bool, str]:
        """Check if a user can make a generation request."""
        hourly = self.db.get_generation_count(user_id, hours=1)
        daily = self.db.get_generation_count(user_id, hours=24)

        if hourly >= RATE_LIMIT_HOURLY:
            return False, f"Hourly limit reached ({hourly}/{RATE_LIMIT_HOURLY}). Try again later."
        if daily >= RATE_LIMIT_DAILY:
            return False, f"Daily limit reached ({daily}/{RATE_LIMIT_DAILY}). Try again tomorrow."

        return True, "OK"

    def get_status(self, user_id: int) -> Dict:
        """Get rate limit status for a user."""
        hourly = self.db.get_generation_count(user_id, hours=1)
        daily = self.db.get_generation_count(user_id, hours=24)
        daily_cost = self.db.get_daily_cost(user_id)

        return {
            "hourly_used": hourly,
            "hourly_limit": RATE_LIMIT_HOURLY,
            "daily_used": daily,
            "daily_limit": RATE_LIMIT_DAILY,
            "daily_cost_pollen": round(daily_cost, 6),
        }
