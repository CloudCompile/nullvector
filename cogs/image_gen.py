#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v3.0 — Image Generation Cog

Image generation with cost-conscious model routing.
Sana Sprint by default (dirt cheap!).
"""

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
import io

from database import Database
from pollinations import PollinationsAPI
from model_router import ModelRouter
from rate_limiter import RateLimiter
from config import DEFAULT_IMAGE_MODEL


class ImageGenCog(commands.Cog, name="Image Generation"):
    """Image generation commands using Pollinations API."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="image", description="Generate an image from a prompt")
    @app_commands.describe(
        prompt="Description of the image",
        model="Image model (sana=cheap, flux=quality, gptimage=pro)",
        width="Width in pixels (default: 1024)",
        height="Height in pixels (default: 1024)",
    )
    async def image(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: str = None,
        width: int = 1024,
        height: int = 1024,
    ):
        """Generate an image from a text prompt."""
        await interaction.response.defer(thinking=True)

        db: Database = self.bot.db  # type: ignore
        api: PollinationsAPI = self.bot.api  # type: ignore
        router: ModelRouter = self.bot.model_router  # type: ignore
        limiter: RateLimiter = self.bot.rate_limiter  # type: ignore

        user_id = interaction.user.id
        channel_id = interaction.channel_id

        can_gen, reason = limiter.can_generate(user_id)
        if not can_gen:
            await interaction.followup.send(f"Slow down! {reason}", ephemeral=True)
            return

        use_model = model or DEFAULT_IMAGE_MODEL

        try:
            image_bytes = await api.image_generate(
                prompt, model=use_model, width=width, height=height
            )

            file = discord.File(io.BytesIO(image_bytes), filename="nullvector_image.png")
            embed = discord.Embed(
                title="Generated Image",
                description=prompt[:500],
                color=discord.Color.purple(),
            )
            embed.set_image(url="attachment://nullvector_image.png")

            actual_cost = router.estimate_image_cost(use_model)
            embed.set_footer(text=f"Model: {use_model} | {width}x{height} | Cost: {actual_cost:.4f} pollen")

            await interaction.followup.send(embed=embed, file=file)

            db.log_generation(channel_id, user_id, "image", use_model, prompt[:50], cost_pollen=actual_cost)

        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)[:200]}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImageGenCog(bot))
