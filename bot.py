#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v2.0 — Smart AI Discord Bot

Powered by Pollinations API — Text & Image Generation.
Intelligent model routing, persistent memory, rate limiting.

Features:
  - Smart model routing (auto-picks the best model for each query)
  - Persistent conversation memory (STM + LTM with SQLite)
  - Slash commands (works in DMs and servers)
  - Image generation (Sana Sprint = dirt cheap!)
  - Rate limiting (cost-conscious, not unlimited)
  - Web search via Gemini Search
  - Code help via Claude Fast

Run: python bot.py
"""

from __future__ import annotations
import asyncio
import logging
import sys
import os

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import (
    DISCORD_TOKEN, ADMIN_IDS, BOT_PREFIX,
    POLLINATIONS_KEY, POLLINATIONS_BASE_URL,
)
from database import Database
from pollinations import PollinationsAPI
from model_router import ModelRouter
from rate_limiter import RateLimiter

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("NullVector")

# ── Bot setup ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True   # Privileged — required for reading messages
intents.messages = True
intents.guilds = True
intents.dm_messages = True


class NullVectorBot(commands.Bot):
    """NullVector v2.0 Discord Bot."""

    def __init__(self):
        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None,
        )
        self.db = Database()
        self.api = PollinationsAPI()
        self.model_router = ModelRouter()
        self.rate_limiter = RateLimiter(self.db)

    async def setup_hook(self):
        """Load all cogs."""
        cogs = [
            "cogs.core",
            "cogs.ai_chat",
            "cogs.image_gen",
            "cogs.admin",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded cog: {cog}")
            except Exception as e:
                log.error(f"Failed to load cog {cog}: {e}")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            log.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            log.error(f"Failed to sync commands: {e}")

    async def on_ready(self):
        """Called when the bot is connected and ready."""
        log.info(f"✅ {self.user} is online!")
        log.info(f"📊 Connected to {len(self.guilds)} servers")
        await self.change_presence(
            activity=discord.Game(name="DM or @mention me | /help | v2.0")
        )

    async def on_message(self, message: discord.Message):
        """Handle messages — DMs and @mentions in servers."""
        # Ignore own messages
        if message.author == self.user:
            return

        # Process prefix commands first
        await self.process_commands(message)

        # Check if bot should respond
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user in message.mentions

        if not (is_dm or is_mentioned):
            return

        # Remove bot mention from message in servers
        content = message.content
        if is_mentioned:
            content = content.replace(f'<@{self.user.id}>', '').strip()

        if not content:
            return

        # Check rate limit
        can_gen, reason = self.rate_limiter.can_generate(message.author.id)
        if not can_gen:
            await message.channel.send(f"Slow down! {reason}")
            return

        # Route to the best model
        use_model = self.model_router.route_text(content)
        channel_id = message.channel.id
        user_id = message.author.id

        # Build context from database
        history = self.db.get_conversations(channel_id, limit=8)
        ltm_summary = self.db.get_latest_ltm_summary(channel_id)

        # Build system prompt
        system_content = "You are NullVector, a helpful AI assistant. You can answer questions, help with coding, research topics, and have natural conversations. Be concise but thorough. Use markdown formatting when appropriate."
        if ltm_summary:
            system_content += f"\n\nPrevious conversation summary:\n{ltm_summary}"

        # Build messages
        api_messages = [{"role": "system", "content": system_content}]
        for msg in history:
            api_messages.append({"role": msg["role"], "content": msg["content"]})
        api_messages.append({"role": "user", "content": content})

        # Ensure proper alternation
        cleaned = []
        system = [m for m in api_messages if m["role"] == "system"]
        conv = [m for m in api_messages if m["role"] != "system"]
        last_role = None
        for msg in conv:
            if msg["role"] == last_role:
                if cleaned:
                    cleaned[-1]["content"] += "\n" + msg["content"]
                continue
            cleaned.append(msg)
            last_role = msg["role"]
        if cleaned and cleaned[0]["role"] != "user":
            cleaned = cleaned[1:]
        if cleaned and cleaned[-1]["role"] != "user":
            cleaned = cleaned[:-1]
        api_messages = system + cleaned

        try:
            async with message.channel.typing():
                response = await self.api.chat_completions(api_messages, model=use_model)

                # Handle empty response
                if not response or not response.strip():
                    log.warning(f"Empty response from model {use_model}, retrying with openai-fast...")
                    response = await self.api.chat_completions(api_messages, model="openai")
                    if not response or not response.strip():
                        await message.channel.send("Hmm, I got an empty response. Try again?")
                        return

                # Save to DB
                self.db.add_conversation(channel_id, user_id, "user", content)
                self.db.add_conversation(channel_id, user_id, "assistant", response, model_used=use_model)

                # Track cost
                cost = self.model_router.estimate_cost(use_model, len(content.split()) * 2, len(response.split()) * 2)
                self.db.log_generation(channel_id, user_id, "text", use_model, content[:50], cost_pollen=cost)

                # Truncate if needed
                display_response = response
                if len(display_response) > 1950:
                    display_response = display_response[:1950] + "..."

                # Add model info
                display_response += f"\n\n*Model: {use_model}*"

                await message.channel.send(display_response)

        except Exception as e:
            await message.channel.send(f"Error: {str(e)[:200]}")
            log.error(f"Error processing message: {e}")

    async def close(self):
        """Clean up on shutdown."""
        await self.api.close()
        await super().close()


# ── Run ───────────────────────────────────────────────────
def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: DISCORD_TOKEN is not set!")
        print("Create a .env file from .env.example and add your bot token.")
        sys.exit(1)

    print("NullVector v2.0 — Starting...")
    print(f"  API: Pollinations ({POLLINATIONS_BASE_URL})")
    print(f"  Key: {'set' if POLLINATIONS_KEY else 'not set (using free tier)'}")
    print(f"  Admins: {ADMIN_IDS or 'none'}")
    print(f"  Default text model: openai-fast")
    print()

    bot = NullVectorBot()

    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
