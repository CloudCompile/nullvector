#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v2.0 — Smart Model Router

Analyzes user messages and routes them to the best AI model.
v2.0: Cost-aware routing — uses cheap models by default, expensive only when needed.
"""

from __future__ import annotations
import re
from typing import Optional, List, Dict
from dataclasses import dataclass

from config import DEFAULT_TEXT_MODEL, DEFAULT_IMAGE_MODEL


@dataclass
class ModelInfo:
    """Information about an AI model."""
    name: str
    title: str
    description: str
    category: str          # "text" or "image"
    cost_tier: str         # "budget", "standard", "premium"
    has_vision: bool = False
    has_reasoning: bool = False
    has_search: bool = False
    has_tools: bool = False
    prompt_price: float = 0.0
    completion_price: float = 0.0


# ── Model definitions with pricing (from Pollinations API) ──

TEXT_MODELS = {
    # Budget tier (ultra-cheap or free)
    "openai-fast": ModelInfo(
        name="openai-fast", title="GPT-5 Nano", description="Ultra-fast and ultra-cheap for simple tasks",
        category="text", cost_tier="budget", has_vision=True, has_tools=True,
        prompt_price=0.0000000375, completion_price=0.0000003,
    ),
    "gpt-oss": ModelInfo(
        name="gpt-oss", title="GPT-OSS 20B", description="Open-weight reasoner, budget",
        category="text", cost_tier="budget", has_reasoning=True, has_tools=True,
        prompt_price=0.00000005, completion_price=0.00000018,
    ),
    # Standard tier
    "openai": ModelInfo(
        name="openai", title="GPT-5.4 Nano", description="Balanced all-rounder",
        category="text", cost_tier="standard", has_vision=True, has_tools=True,
        prompt_price=0.00000015, completion_price=0.0000009375,
    ),
    "deepseek": ModelInfo(
        name="deepseek", title="DeepSeek", description="Strong reasoning and analysis",
        category="text", cost_tier="standard", has_reasoning=True,
        prompt_price=0.00000015, completion_price=0.00000055,
    ),
    "claude-fast": ModelInfo(
        name="claude-fast", title="Claude Fast", description="Fast Claude model",
        category="text", cost_tier="standard",
        prompt_price=0.00000008, completion_price=0.0000004,
    ),
    # Search models
    "gemini-search": ModelInfo(
        name="gemini-search", title="Gemini Search", description="Web search for current events",
        category="text", cost_tier="standard", has_search=True,
        prompt_price=0.0000001, completion_price=0.0000005,
    ),
    "perplexity-fast": ModelInfo(
        name="perplexity-fast", title="Perplexity Fast", description="Quick web research",
        category="text", cost_tier="standard", has_search=True,
        prompt_price=0.0000001, completion_price=0.0000005,
    ),
    # Premium tier
    "openai-large": ModelInfo(
        name="openai-large", title="GPT-5.4", description="Complex reasoning and analysis",
        category="text", cost_tier="premium", has_reasoning=True, has_tools=True,
        prompt_price=0.0000005, completion_price=0.000003,
    ),
    "claude": ModelInfo(
        name="claude", title="Claude", description="High-quality Claude model",
        category="text", cost_tier="premium",
        prompt_price=0.0000003, completion_price=0.0000015,
    ),
    "claude-large": ModelInfo(
        name="claude-large", title="Claude Large", description="Most capable Claude model",
        category="text", cost_tier="premium",
        prompt_price=0.00000075, completion_price=0.00000375,
    ),
    "deepseek-pro": ModelInfo(
        name="deepseek-pro", title="DeepSeek Pro", description="Advanced reasoning",
        category="text", cost_tier="premium", has_reasoning=True,
        prompt_price=0.0000004, completion_price=0.0000016,
    ),
}

IMAGE_MODELS = {
    "sana": ModelInfo(
        name="sana", title="Sana Sprint", description="Ultra-fast image gen, dirt cheap",
        category="image", cost_tier="budget",
        prompt_price=0.0, completion_price=0.0001,
    ),
    "flux": ModelInfo(
        name="flux", title="Flux", description="Quality image generation",
        category="image", cost_tier="standard",
        prompt_price=0.0, completion_price=0.003,
    ),
    "gptimage": ModelInfo(
        name="gptimage", title="GPT Image", description="Professional image generation",
        category="image", cost_tier="premium",
        prompt_price=0.0, completion_price=0.01,
    ),
}

ALL_MODELS = {**TEXT_MODELS, **IMAGE_MODELS}


class ModelRouter:
    """Smart model router — picks the best model for the task."""

    def __init__(self):
        self.models = ALL_MODELS

    def route_text(self, message: str, context: str = "") -> str:
        """Analyze a message and return the best model name for it."""
        msg_lower = message.lower()

        # ── Search signals ───────────────────────────────
        search_patterns = [
            r'\b(who is|what is|when did|where is|how does|latest|recent|news|current|today|this week|this month)\b',
            r'\b(weather|stock|price|score|result|update|happening)\b',
            r'\b(look up|search|find|google|check online)\b',
        ]
        for pattern in search_patterns:
            if re.search(pattern, msg_lower):
                return "gemini-search"

        # ── Code signals ─────────────────────────────────
        code_patterns = [
            r'\b(code|program|function|debug|error|compile|python|javascript|java|c\+\+|rust|html|css|sql)\b',
            r'\b(api|algorithm|script|module|class|method|variable|syntax)\b',
            r'```',
        ]
        for pattern in code_patterns:
            if re.search(pattern, msg_lower):
                return "claude-fast"

        # ── Reasoning signals ────────────────────────────
        reasoning_patterns = [
            r'\b(explain|analyze|compare|why|how|reason|logic|prove|calculate|math)\b',
            r'\b(philosophy|debate|argue|opinion|perspective|think about)\b',
        ]
        for pattern in reasoning_patterns:
            if re.search(pattern, msg_lower):
                return "deepseek"

        # ── Complex/long messages ────────────────────────
        if len(message) > 500:
            return "openai"

        # ── Default: ultra-cheap ─────────────────────────
        return DEFAULT_TEXT_MODEL

    def route_image(self, prompt: str) -> str:
        """Pick the best image model for a prompt."""
        # Default to cheapest (Sana Sprint)
        return DEFAULT_IMAGE_MODEL

    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate pollen cost for a generation."""
        info = self.models.get(model)
        if not info:
            return 0.0
        return (prompt_tokens * info.prompt_price) + (completion_tokens * info.completion_price)

    def estimate_image_cost(self, model: str) -> float:
        """Estimate pollen cost for an image generation."""
        info = self.models.get(model)
        if not info:
            return 0.0
        return info.completion_price

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get info about a specific model."""
        return self.models.get(model_name)

    def list_models(self, category: str = None, cost_tier: str = None) -> List[ModelInfo]:
        """List models, optionally filtered by category and/or cost tier."""
        results = list(self.models.values())
        if category:
            results = [m for m in results if m.category == category]
        if cost_tier:
            results = [m for m in results if m.cost_tier == cost_tier]
        return results
