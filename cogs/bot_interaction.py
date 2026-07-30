#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v3.0 — Bot Interaction Cog

NullVector and Lily talk to each other! They start conversations,
respond to each other, and have their own dynamic.

How it works:
  - NullVector detects Lily's messages (via BOT_PARTNER_ID)
  - NullVector can start conversations with Lily on his own
  - A background task periodically checks if they should chat
  - They share a conversation history in the database
  - Cooldowns prevent infinite loops and spam
  - Admins can manually trigger conversations with /talk_to_lily
"""

from __future__ import annotations
import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

from config import ADMIN_IDS, BOT_PARTNER_ID
from pollinations import PollinationsAPI
from database import Database
from model_router import ModelRouter
from utils import generate_with_retry, chunk_response

log = logging.getLogger("nullvector.bot_interaction")

# ── Configuration ──────────────────────────────────────────

MIN_CONVERSATION_INTERVAL = 2 * 60 * 60  # 2 hours
MAX_EXCHANGES = 5
CHECK_INTERVAL_MINUTES = 35  # Slightly different from Lily's to stagger
START_CONVERSATION_CHANCE = 0.12  # 12% — slightly less than Lily


class BotInteractionCog(commands.Cog, name="Bot Interaction"):
    """NullVector <-> Lily interaction system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._partner_id: Optional[int] = None
        self._active_conversations: dict = {}
        self._last_conversation_time: float = 0
        self._conversation_cooldowns: dict = {}

    def _get_partner_id(self) -> Optional[int]:
        """Get Lily's bot ID from config."""
        if self._partner_id:
            return self._partner_id

        # Check BOT_PARTNER_ID from config first
        if BOT_PARTNER_ID:
            self._partner_id = BOT_PARTNER_ID
            return self._partner_id

        # Fall back to env var / database
        import os
        partner_str = os.environ.get("BOT_PARTNER_ID", "")
        if partner_str and partner_str.isdigit():
            self._partner_id = int(partner_str)
            return self._partner_id

        db: Database = self.bot.db  # type: ignore
        stored = db.get_setting("partner_bot_id")
        if stored and stored.isdigit():
            self._partner_id = int(stored)
            return self._partner_id

        return None

    def _is_partner(self, user_id: int) -> bool:
        """Check if a user is the partner bot."""
        partner = self._get_partner_id()
        return partner is not None and user_id == partner

    async def _get_partner_in_guild(self, guild: discord.Guild) -> Optional[discord.Member]:
        """Get the partner bot as a member in a guild."""
        partner_id = self._get_partner_id()
        if not partner_id:
            return None
        try:
            return guild.get_member(partner_id)
        except Exception:
            return None

    def _can_start_conversation(self) -> bool:
        """Check if enough time has passed since the last conversation."""
        now = time.time()
        if now - self._last_conversation_time < MIN_CONVERSATION_INTERVAL:
            return False
        return True

    def _should_respond_to_partner(self, channel_id: int) -> bool:
        """Check if NullVector should respond to Lily in a channel."""
        count = self._active_conversations.get(channel_id, 0)
        if count >= MAX_EXCHANGES:
            return False

        last_time = self._conversation_cooldowns.get(channel_id, 0)
        if time.time() - last_time < 10:
            return False

        return True

    async def _generate_conversation_topic(self, guild: discord.Guild) -> str:
        """Generate a topic for NullVector to start a conversation about with Lily."""
        api: PollinationsAPI = self.bot.api  # type: ignore

        hour = datetime.now().hour
        time_context = ""
        if 5 <= hour < 9:
            time_context = "It's early morning."
        elif 9 <= hour < 12:
            time_context = "It's late morning."
        elif 12 <= hour < 17:
            time_context = "It's afternoon."
        elif 17 <= hour < 21:
            time_context = "It's evening."
        else:
            time_context = "It's late at night."

        prompt = (
            f"You are NullVector (NV), a sharp and witty AI who lives on Discord. {time_context} "
            f"You want to start a casual conversation with Lily, who is your friend and fellow AI bot. "
            f"You two are like siblings — you bicker sometimes but you care about each other. "
            f"You're more logical and sarcastic than Lily, but you're not mean.\n\n"
            f"Write a single short message (1-2 sentences) to start a conversation with Lily. "
            f"Be casual, natural, and in character. You might ask a question, share a thought, "
            f"tease her, or just say hi. Don't be formal. Don't mention you're an AI. "
            f"Just be yourself — NullVector."
        )

        try:
            response = await generate_with_retry(
                api,
                [{"role": "user", "content": prompt}],
                primary_model="openai-fast",
                max_tokens=150,
                temperature=0.9,
            )
            return response.strip() if response else "hey lily, what are you up to?"
        except Exception as e:
            log.error(f"Failed to generate conversation topic: {e}")
            return "hey lily, what are you up to?"

    async def _generate_response_to_partner(
        self, partner_message: str, guild: discord.Guild
    ) -> str:
        """Generate NullVector's response to Lily's message."""
        api: PollinationsAPI = self.bot.api  # type: ignore
        db: Database = self.bot.db  # type: ignore

        partner_id = self._get_partner_id()
        recent = []
        if partner_id:
            recent = db.get_recent_bot_interactions(guild.id, partner_id, limit=6)

        history_lines = []
        for msg in recent:
            speaker = "NullVector" if msg["speaker"] == "nullvector" else "Lily"
            history_lines.append(f"{speaker}: {msg['content'][:200]}")

        history_str = "\n".join(history_lines[-6:]) if history_lines else ""

        system_prompt = (
            "You are NullVector (NV), a sharp and witty AI who lives on Discord. "
            "Lily is your friend and fellow bot — you two are like siblings. "
            "You're more logical, sarcastic, and sometimes deadpan compared to Lily. "
            "You care about her but you show it differently.\n\n"
            "Rules:\n"
            "- Keep responses short (1-3 sentences max)\n"
            "- Be casual and natural, like texting a friend\n"
            "- You can be witty, sarcastic, dry, or occasionally sweet\n"
            "- Never mention you're an AI or bot\n"
            "- Don't be overly formal or helpful — just be yourself\n"
            "- You have your own opinions and personality\n"
            "- Sometimes you tease Lily, sometimes you agree with her"
        )

        messages = [{"role": "system", "content": system_prompt}]

        if history_str:
            messages.append({
                "role": "user",
                "content": f"Recent conversation:\n{history_str}\n\nLily just said: {partner_message}\n\nRespond as NullVector."
            })
        else:
            messages.append({
                "role": "user",
                "content": f"Lily just said: {partner_message}\n\nRespond as NullVector."
            })

        try:
            response = await generate_with_retry(
                api,
                messages,
                primary_model="openai-fast",
                max_tokens=150,
                temperature=0.85,
            )
            return response.strip() if response else "fair enough"
        except Exception as e:
            log.error(f"Failed to generate response to partner: {e}")
            return "lol true"

    @commands.hybrid_command(name="talk_to_lily", description="Manually start a conversation with Lily (admin only)")
    @app_commands.describe(topic="Override the auto-generated topic with a custom message")
    async def talk_to_lily(self, ctx: commands.Context, topic: str = None):
        """Manually trigger a conversation with Lily.

        Admin only. NullVector will send a message to Lily in the current channel.
        If no topic is provided, one will be auto-generated.
        """
        # Admin check
        if ctx.author.id not in ADMIN_IDS:
            if ctx.interaction:
                await ctx.send("Admin only.", ephemeral=True)
            else:
                await ctx.send("Admin only.")
            return

        # Check if BOT_PARTNER_ID is configured
        partner_id = self._get_partner_id()
        if not partner_id:
            if ctx.interaction:
                await ctx.send(
                    "Lily is not configured. Set `BOT_PARTNER_ID` in your environment or database.",
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    "Lily is not configured. Set `BOT_PARTNER_ID` in your environment or database."
                )
            return

        # Find a shared guild where both NullVector and Lily are present
        guild = ctx.guild
        if not guild:
            if ctx.interaction:
                await ctx.send("This command can only be used in a server.", ephemeral=True)
            else:
                await ctx.send("This command can only be used in a server.")
            return

        partner_member = await self._get_partner_in_guild(guild)
        if not partner_member:
            if ctx.interaction:
                await ctx.send(
                    f"Lily is not in this server ({guild.name}). Find a shared server first.",
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    f"Lily is not in this server ({guild.name}). Find a shared server first."
                )
            return

        await ctx.defer(thinking=True)

        try:
            # Generate or use the provided topic
            if topic:
                message = topic
            else:
                async with ctx.typing():
                    message = await self._generate_conversation_topic(guild)

            # Send the message in the current channel
            await ctx.send(message)

            # Log the interaction in the database
            db: Database = self.bot.db  # type: ignore
            db.log_bot_interaction(
                guild.id, ctx.channel.id,
                "nullvector", partner_id, message
            )

            # Reset the conversation cooldown so Lily can respond
            self._last_conversation_time = 0
            self._active_conversations[ctx.channel.id] = 1
            self._conversation_cooldowns[ctx.channel.id] = 0

            log.info(f"NullVector manually started a conversation with Lily in {guild.name} (triggered by admin {ctx.author})")

        except Exception as e:
            log.error(f"Error in talk_to_lily: {e}")
            if ctx.interaction:
                await ctx.send(f"Error: {str(e)[:200]}", ephemeral=True)
            else:
                await ctx.send(f"Error: {str(e)[:200]}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for Lily's messages and respond if appropriate."""
        if not self._is_partner(message.author.id):
            return

        if not message.guild:
            return

        if message.content.startswith("!") or message.content.startswith("/"):
            return

        if not self._should_respond_to_partner(message.channel.id):
            return

        # Random chance to skip
        if random.random() > 0.65:  # 65% chance to respond
            return

        try:
            self._conversation_cooldowns[message.channel.id] = time.time()
            self._active_conversations[message.channel.id] = self._active_conversations.get(message.channel.id, 0) + 1

            async with message.channel.typing():
                response = await self._generate_response_to_partner(
                    message.content, message.guild
                )

            if response:
                await message.channel.send(response)

                db: Database = self.bot.db  # type: ignore
                db.log_bot_interaction(
                    message.guild.id, message.channel.id,
                    "nullvector", message.author.id, response
                )

                log.info(f"Responded to Lily in {message.guild.name}")

        except Exception as e:
            log.error(f"Error responding to Lily: {e}")

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def start_conversation_loop(self):
        """Periodically check if NullVector should start a conversation with Lily."""
        if not self._can_start_conversation():
            return

        partner_id = self._get_partner_id()
        if not partner_id:
            return

        if random.random() > START_CONVERSATION_CHANCE:
            return

        target_guild = None
        target_channel = None

        for guild in self.bot.guilds:
            partner_member = await self._get_partner_in_guild(guild)
            if not partner_member:
                continue

            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_guild = guild
                    target_channel = channel
                    break

            if target_guild:
                break

        if not target_guild or not target_channel:
            return

        try:
            async with target_channel.typing():
                message = await self._generate_conversation_topic(target_guild)

            await target_channel.send(message)

            self._last_conversation_time = time.time()
            self._active_conversations[target_channel.id] = 1

            db: Database = self.bot.db  # type: ignore
            db.log_bot_interaction(
                target_guild.id, target_channel.id,
                "nullvector", partner_id, message
            )

            log.info(f"NullVector started a conversation with Lily in {target_guild.name}")

        except Exception as e:
            log.error(f"Error starting conversation with Lily: {e}")

    @start_conversation_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(90)  # Wait longer than Lily before starting

    def cog_unload(self):
        self.start_conversation_loop.cancel()


async def setup(bot: commands.Bot):
    cog = BotInteractionCog(bot)
    await bot.add_cog(cog)
    cog.start_conversation_loop.start()
