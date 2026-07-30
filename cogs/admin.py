#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v3.0 — Admin Cog

Admin commands for bot management, health dashboard.
"""

from __future__ import annotations
import time
import discord
from discord.ext import commands
from discord import app_commands

from database import Database
from config import ADMIN_IDS


class AdminCog(commands.Cog, name="Admin"):
    """Admin commands for NullVector."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._start_time = time.time()

    def _is_admin(self, user_id: int) -> bool:
        return user_id in ADMIN_IDS

    @commands.hybrid_command(name="stats", description="NullVector health dashboard (admin only)")
    async def stats(self, ctx: commands.Context):
        """Comprehensive bot health dashboard."""
        if not self._is_admin(ctx.author.id):
            if ctx.interaction:
                await ctx.send("Admin only.", ephemeral=True)
            else:
                await ctx.send("Admin only.")
            return

        db: Database = self.bot.db  # type: ignore
        db_stats = db.get_stats()

        # Calculate uptime
        uptime_seconds = int(time.time() - self._start_time)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"

        # Memory usage
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / 1024 / 1024
            mem_str = f"{mem_mb:.1f} MB"
        except ImportError:
            mem_str = "N/A (psutil not installed)"

        # Count active conversations
        active_convs = db_stats.get("total_conversations", 0)
        unique_users = db_stats.get("total_users", 0)

        # API status
        api = self.bot.api  # type: ignore
        api_status = "connected" if api._session and not api._session.closed else "not initialized"

        # Partner status
        partner_cog = self.bot.get_cog("Bot Interaction")
        partner_status = "configured" if partner_cog else "not set"

        embed = discord.Embed(
            title="⚡ NullVector v3.0 — Health Dashboard",
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="System",
            value=(
                f"Uptime: {uptime_str}\n"
                f"Servers: {len(self.bot.guilds)}\n"
                f"Latency: {round(self.bot.latency * 1000)}ms\n"
                f"Memory: {mem_str}\n"
                f"API: {api_status}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Memory",
            value=(
                f"Conversations: {active_convs}\n"
                f"Users: {unique_users}\n"
                f"Partner Bot: {partner_status}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Generations",
            value=(
                f"Total: {db_stats.get('total_generations', 0)}\n"
                f"Today: {db_stats.get('today_generations', 0)}\n"
                f"Bot Chats: {db_stats.get('bot_interactions', 0)}\n"
                f"Pollen Spent: {db_stats.get('total_pollen_spent', 0):.4f}"
            ),
            inline=True,
        )
        embed.set_footer(text="NullVector v3.0 | Smart Model Routing | Retry Logic ✅")
        if ctx.interaction:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="balance", description="Check API balance (admin only)")
    async def balance(self, ctx: commands.Context):
        """Check Pollinations API balance."""
        if not self._is_admin(ctx.author.id):
            if ctx.interaction:
                await ctx.send("Admin only.", ephemeral=True)
            else:
                await ctx.send("Admin only.")
            return

        api = self.bot.api  # type: ignore
        try:
            result = await api.get_balance()
            embed = discord.Embed(title="API Balance", color=discord.Color.green())
            embed.add_field(name="Balance", value=str(result.get("balance", result.get("total", "N/A"))), inline=True)
            embed.add_field(name="Currency", value=result.get("currency", "pollen"), inline=True)
            if ctx.interaction:
                await ctx.send(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed)
        except Exception as e:
            if ctx.interaction:
                await ctx.send(f"Error: {str(e)[:200]}", ephemeral=True)
            else:
                await ctx.send(f"Error: {str(e)[:200]}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
