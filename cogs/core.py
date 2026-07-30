#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v3.0 — Core Cog

Essential commands: help, status, memory, models, ping.
"""

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from database import Database
from model_router import ModelRouter
from rate_limiter import RateLimiter
from config import ADMIN_IDS, RATE_LIMIT_HOURLY, RATE_LIMIT_DAILY


class CoreCog(commands.Cog, name="Core"):
    """Essential bot commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show NullVector's commands")
    async def help_slash(self, ctx: commands.Context):
        """Show all available commands."""
        embed = discord.Embed(
            title="NullVector v3.0 — Command Guide",
            description="Smart AI assistant that automatically picks the best model for your query. Works in DMs and servers!",
            color=discord.Color.purple(),
        )

        embed.add_field(
            name="💬 AI Chat",
            value=(
                "`/ask <question>` — Ask anything\n"
                "`/chat <message>` — Have a conversation\n"
                "`/imagine <prompt>` — Creative text generation\n"
                "`/research <topic>` — Web search research\n"
                "`/code <prompt>` — Coding help"
            ),
            inline=False,
        )

        embed.add_field(
            name="🖼️ Image Generation",
            value="`/image <prompt>` — Generate an image (Sana Sprint!)",
            inline=False,
        )

        embed.add_field(
            name="📋 Memory & Info",
            value=(
                "`/memory` — View memory stats\n"
                "`/clear` — Clear conversation memory\n"
                "`/models [category]` — List AI models\n"
                "`/model_info <model>` — Get model details\n"
                "`/quota` — Check your rate limits\n"
                "`/ping` — Check response time"
            ),
            inline=False,
        )

        embed.set_footer(text="NullVector v3.0 | Smart Model Routing | Cost-Conscious AI")
        if ctx.interaction:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="ping", description="Check response time")
    async def ping(self, ctx: commands.Context):
        """Simple ping/pong."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! {latency}ms")

    @commands.hybrid_command(name="memory", description="View conversation memory stats")
    async def memory(self, ctx: commands.Context):
        """View memory stats for this channel."""
        db: Database = self.bot.db  # type: ignore
        channel_id = ctx.channel.id

        count = db.get_conversation_count(channel_id)
        ltm = db.get_latest_ltm_summary(channel_id)

        embed = discord.Embed(title="Memory Stats", color=discord.Color.purple())
        embed.add_field(name="Total Messages", value=str(count), inline=True)
        embed.add_field(name="LTM Summary", value="Yes" if ltm else "No", inline=True)
        embed.add_field(name="STM (Recent)", value=str(min(8, count)), inline=True)

        if ltm:
            embed.add_field(name="Summary Preview", value=ltm[:200] + "...", inline=False)

        if ctx.interaction:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="clear", description="Clear conversation memory for this channel")
    async def clear(self, ctx: commands.Context):
        """Clear conversation memory."""
        db: Database = self.bot.db  # type: ignore
        channel_id = ctx.channel.id
        db.clear_conversations(channel_id)
        await ctx.send("Conversation memory cleared!")

    @commands.hybrid_command(name="models", description="List available AI models")
    @app_commands.describe(
        category="Model category: text or image",
        tier="Cost tier: budget, standard, premium",
    )
    async def models(
        self,
        ctx: commands.Context,
        category: str = "text",
        tier: str = None,
    ):
        """List available AI models."""
        router: ModelRouter = self.bot.model_router  # type: ignore

        models = router.list_models(category=category, cost_tier=tier)

        if not models:
            if ctx.interaction:
                await ctx.send(
                    f"No models found for category `{category}`" + (f" tier `{tier}`" if tier else ""),
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    f"No models found for category `{category}`" + (f" tier `{tier}`" if tier else "")
                )
            return

        embed = discord.Embed(
            title=f"{category.title()} Models" + (f" — {tier.title()} Tier" if tier else ""),
            color=discord.Color.purple(),
        )

        for m in models[:20]:
            vision = " 👁️" if m.has_vision else ""
            reasoning = " 🧠" if m.has_reasoning else ""
            search = " 🔍" if m.has_search else ""
            cost = f"{m.completion_price:.8f}"
            embed.add_field(
                name=f"`{m.name}`{vision}{reasoning}{search}",
                value=f"{m.title} — {m.description}\nCost: {cost} pollen/token",
                inline=False,
            )

        if ctx.interaction:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="model_info", description="Get details about a specific model")
    @app_commands.describe(model="Model name to look up")
    async def model_info(self, ctx: commands.Context, model: str):
        """Get detailed info about a model."""
        router: ModelRouter = self.bot.model_router  # type: ignore
        info = router.get_model_info(model)

        if not info:
            if ctx.interaction:
                await ctx.send(
                    f"Model `{model}` not found. Use `/models` to see available models.",
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    f"Model `{model}` not found. Use `/models` to see available models."
                )
            return

        embed = discord.Embed(
            title=info.title,
            description=info.description,
            color=discord.Color.purple(),
        )
        embed.add_field(name="ID", value=f"`{info.name}`", inline=True)
        embed.add_field(name="Cost Tier", value=info.cost_tier.title(), inline=True)
        embed.add_field(name="Prompt Cost", value=f"{info.prompt_price:.8f}", inline=True)
        embed.add_field(name="Completion Cost", value=f"{info.completion_price:.8f}", inline=True)
        embed.add_field(name="Vision", value="✅" if info.has_vision else "❌", inline=True)
        embed.add_field(name="Reasoning", value="✅" if info.has_reasoning else "❌", inline=True)

        if ctx.interaction:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="quota", description="Check your rate limits")
    async def quota(self, ctx: commands.Context):
        """Check your generation rate limits."""
        limiter: RateLimiter = self.bot.rate_limiter  # type: ignore
        status = limiter.get_status(ctx.author.id)

        embed = discord.Embed(title="Your Rate Limits", color=discord.Color.purple())
        embed.add_field(
            name="Hourly",
            value=f"{status['hourly_used']}/{status['hourly_limit']}",
            inline=True,
        )
        embed.add_field(
            name="Daily",
            value=f"{status['daily_used']}/{status['daily_limit']}",
            inline=True,
        )
        embed.add_field(
            name="Daily Cost",
            value=f"{status['daily_cost_pollen']:.6f} pollen",
            inline=True,
        )
        embed.set_footer(text="Rate limits reset automatically")
        if ctx.interaction:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCog(bot))
