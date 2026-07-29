#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v2.0 — Admin Cog

Admin commands for bot management.
"""

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from database import Database
from config import ADMIN_IDS


class AdminCog(commands.Cog, name="Admin"):
    """Admin commands for NullVector."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, user_id: int) -> bool:
        return user_id in ADMIN_IDS

    @app_commands.command(name="balance", description="Check API balance (admin only)")
    async def balance(self, interaction: discord.Interaction):
        """Check Pollinations API balance."""
        if not self._is_admin(interaction.user.id):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        api = self.bot.api  # type: ignore
        try:
            result = await api.get_balance()
            embed = discord.Embed(title="API Balance", color=discord.Color.green())
            embed.add_field(name="Balance", value=str(result.get("balance", result.get("total", "N/A"))), inline=True)
            embed.add_field(name="Currency", value=result.get("currency", "pollen"), inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="stats", description="Bot statistics (admin only)")
    async def stats(self, interaction: discord.Interaction):
        """View bot statistics."""
        if not self._is_admin(interaction.user.id):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        embed = discord.Embed(title="NullVector v2.0 Stats", color=discord.Color.purple())
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
