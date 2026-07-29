#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v2.0 — AI Chat Cog

The core chat functionality. Smart model routing, persistent memory,
slash commands. Works in DMs and servers.
"""

from __future__ import annotations
import asyncio
import discord
from discord.ext import commands
from discord import app_commands

from database import Database
from pollinations import PollinationsAPI
from model_router import ModelRouter
from rate_limiter import RateLimiter
from config import DEFAULT_TEXT_MODEL, STM_MESSAGES, LTM_SUMMARY_THRESHOLD


class AIChatCog(commands.Cog, name="AI Chat"):
    """AI chat commands — the core of NullVector."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _ensure_alternation(self, messages: list) -> list:
        """Ensure messages properly alternate between user and assistant."""
        if not messages:
            return []

        system = [m for m in messages if m["role"] == "system"]
        conv = [m for m in messages if m["role"] != "system"]

        cleaned = []
        last_role = None
        for msg in conv:
            if msg["role"] == last_role:
                if cleaned:
                    cleaned[-1]["content"] += "\n" + msg["content"]
                continue
            cleaned.append(msg)
            last_role = msg["role"]

        # Ensure starts with user
        if cleaned and cleaned[0]["role"] != "user":
            cleaned = cleaned[1:]
        # Ensure ends with user
        if cleaned and cleaned[-1]["role"] != "user":
            cleaned = cleaned[:-1]

        return system + cleaned

    @app_commands.command(name="ask", description="Ask NullVector anything")
    @app_commands.describe(
        question="Your question",
        model="AI model (leave empty for smart routing)",
    )
    async def ask(self, interaction: discord.Interaction, question: str, model: str = None):
        """Ask NullVector a question using AI."""
        await interaction.response.defer(thinking=True)

        api: PollinationsAPI = self.bot.api  # type: ignore
        db: Database = self.bot.db  # type: ignore
        router: ModelRouter = self.bot.model_router  # type: ignore
        limiter: RateLimiter = self.bot.rate_limiter  # type: ignore

        user_id = interaction.user.id
        channel_id = interaction.channel_id

        # Check rate limit
        can_gen, reason = limiter.can_generate(user_id)
        if not can_gen:
            await interaction.followup.send(f"Slow down! {reason}", ephemeral=True)
            return

        # Smart model routing
        use_model = model or router.route_text(question)

        # Build context from database
        history = db.get_conversations(channel_id, limit=STM_MESSAGES)
        ltm_summary = db.get_latest_ltm_summary(channel_id)

        # Build system prompt
        system_content = "You are NullVector, a helpful AI assistant. You can answer questions, help with coding, research topics, and have natural conversations. Be concise but thorough. Use markdown formatting when appropriate."
        if ltm_summary:
            system_content += f"\n\nPrevious conversation summary:\n{ltm_summary}"

        # Build messages
        api_messages = [{"role": "system", "content": system_content}]
        for msg in history:
            api_messages.append({"role": msg["role"], "content": msg["content"]})
        api_messages.append({"role": "user", "content": question})

        # Ensure proper alternation
        api_messages = self._ensure_alternation(api_messages)

        try:
            response = await api.chat_completions(api_messages, model=use_model)

            # Save to DB
            db.add_conversation(channel_id, user_id, "user", question)
            db.add_conversation(channel_id, user_id, "assistant", response, model_used=use_model)

            # Track cost
            cost = router.estimate_cost(use_model, len(question.split()) * 2, len(response.split()) * 2)
            db.log_generation(channel_id, user_id, "text", use_model, question[:50], cost_pollen=cost)

            # Truncate if needed
            if len(response) > 1950:
                response = response[:1950] + "..."

            # Add model info
            response += f"\n\n*Model: {use_model}*"

            await interaction.followup.send(response)

        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="chat", description="Have a conversation with NullVector")
    @app_commands.describe(
        message="Your message",
        model="AI model to use",
    )
    async def chat(self, interaction: discord.Interaction, message: str, model: str = None):
        """Have a conversation with NullVector using full context."""
        await interaction.response.defer(thinking=True)

        api: PollinationsAPI = self.bot.api  # type: ignore
        db: Database = self.bot.db  # type: ignore
        router: ModelRouter = self.bot.model_router  # type: ignore
        limiter: RateLimiter = self.bot.rate_limiter  # type: ignore

        user_id = interaction.user.id
        channel_id = interaction.channel_id

        can_gen, reason = limiter.can_generate(user_id)
        if not can_gen:
            await interaction.followup.send(f"Slow down! {reason}", ephemeral=True)
            return

        # Route: longer messages get better models
        task = "deep_conversation" if len(message) > 300 else "casual_chat"
        use_model = model or router.route_text(message)

        history = db.get_conversations(channel_id, limit=STM_MESSAGES)
        ltm_summary = db.get_latest_ltm_summary(channel_id)

        system_content = "You are NullVector, a helpful AI assistant. You can answer questions, help with coding, research topics, and have natural conversations. Be concise but thorough. Use markdown formatting when appropriate."
        if ltm_summary:
            system_content += f"\n\nPrevious conversation summary:\n{ltm_summary}"

        api_messages = [{"role": "system", "content": system_content}]
        for msg in history:
            api_messages.append({"role": msg["role"], "content": msg["content"]})
        api_messages.append({"role": "user", "content": message})

        api_messages = self._ensure_alternation(api_messages)

        try:
            response = await api.chat_completions(api_messages, model=use_model, max_tokens=800)

            db.add_conversation(channel_id, user_id, "user", message)
            db.add_conversation(channel_id, user_id, "assistant", response, model_used=use_model)

            cost = router.estimate_cost(use_model, len(message.split()) * 2, len(response.split()) * 2)
            db.log_generation(channel_id, user_id, "text", use_model, message[:50], cost_pollen=cost)

            if len(response) > 1950:
                response = response[:1950] + "..."

            response += f"\n\n*Model: {use_model}*"

            await interaction.followup.send(response)

        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="research", description="Research a topic using web search")
    @app_commands.describe(query="What to research")
    async def research(self, interaction: discord.Interaction, query: str):
        """Research a topic using web-search-capable models."""
        await interaction.response.defer(thinking=True)

        api: PollinationsAPI = self.bot.api  # type: ignore
        db: Database = self.bot.db  # type: ignore
        limiter: RateLimiter = self.bot.rate_limiter  # type: ignore

        user_id = interaction.user.id
        channel_id = interaction.channel_id

        can_gen, reason = limiter.can_generate(user_id)
        if not can_gen:
            await interaction.followup.send(f"Slow down! {reason}", ephemeral=True)
            return

        try:
            response = await api.chat_completions(
                [
                    {"role": "system", "content": "You are a research assistant. Search the web for current, accurate information about the user's query. Provide detailed, well-sourced answers."},
                    {"role": "user", "content": query},
                ],
                model="gemini-search",
                max_tokens=1000,
            )

            db.add_conversation(channel_id, user_id, "user", query)
            db.add_conversation(channel_id, user_id, "assistant", response, model_used="gemini-search")

            cost = router.estimate_cost("gemini-search", len(query.split()) * 2, len(response.split()) * 2)
            db.log_generation(channel_id, user_id, "research", "gemini-search", query[:50], cost_pollen=cost)

            if len(response) > 1950:
                response = response[:1950] + "..."

            embed = discord.Embed(
                title="Research Results",
                description=response,
                color=discord.Color.blue(),
            )
            embed.set_footer(text="Model: gemini-search | Powered by Pollinations")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="code", description="Get help with coding")
    @app_commands.describe(
        prompt="What you need help with",
        language="Programming language (optional)",
    )
    async def code(self, interaction: discord.Interaction, prompt: str, language: str = None):
        """Get coding help from a code-specialized model."""
        await interaction.response.defer(thinking=True)

        api: PollinationsAPI = self.bot.api  # type: ignore
        db: Database = self.bot.db  # type: ignore
        limiter: RateLimiter = self.bot.rate_limiter  # type: ignore

        user_id = interaction.user.id
        channel_id = interaction.channel_id

        can_gen, reason = limiter.can_generate(user_id)
        if not can_gen:
            await interaction.followup.send(f"Slow down! {reason}", ephemeral=True)
            return

        system_msg = "You are a coding expert. Provide clear, well-commented code with explanations. Use markdown code blocks."
        if language:
            system_msg += f" The user prefers {language}."

        try:
            response = await api.chat_completions(
                [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                model="claude-fast",
                max_tokens=1000,
            )

            db.add_conversation(channel_id, user_id, "user", prompt)
            db.add_conversation(channel_id, user_id, "assistant", response, model_used="claude-fast")

            cost = router.estimate_cost("claude-fast", len(prompt.split()) * 2, len(response.split()) * 2)
            db.log_generation(channel_id, user_id, "code", "claude-fast", prompt[:50], cost_pollen=cost)

            if len(response) > 1950:
                response = response[:1950] + "..."

            response += "\n\n*Model: claude-fast*"

            await interaction.followup.send(response)

        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)[:200]}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChatCog(bot))
