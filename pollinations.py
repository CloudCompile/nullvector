#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v2.0 — Pollinations API Client

Handles text and image generation via the Pollinations API.
v2.0: Proper error handling, cost tracking, rate limiting awareness.
"""

from __future__ import annotations
import aiohttp
import json
from typing import Optional, List, Dict, Any

from config import POLLINATIONS_KEY, POLLINATIONS_BASE_URL, POLLINATIONS_MEDIA_URL


class PollinationsAPI:
    """Async client for the Pollinations AI API."""

    def __init__(self):
        self.base_url = POLLINATIONS_BASE_URL
        self.media_url = POLLINATIONS_MEDIA_URL
        self.api_key = POLLINATIONS_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self) -> Dict[str, str]:
        """Build request headers with auth."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ── Text Generation ──────────────────────────────────

    async def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: str = "openai-fast",
        temperature: float = 1.0,
        max_tokens: int = 500,
        safe: str = "privacy,secrets",
    ) -> str:
        """Send a chat completion request and return the response text."""
        session = await self._get_session()
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                error_text = await resp.text()
                raise Exception(f"API Error {resp.status}: {error_text[:300]}")

    async def text_simple(
        self,
        prompt: str,
        model: str = "openai-fast",
        system: str = None,
        temperature: float = 0.7,
        safe: str = "privacy,secrets",
    ) -> str:
        """Simple text generation with a single prompt."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat_completions(messages, model=model, temperature=temperature)

    # ── Image Generation ─────────────────────────────────

    async def image_generate(
        self,
        prompt: str,
        model: str = "sana",
        width: int = 1024,
        height: int = 1024,
        seed: int = 0,
        safe: str = "privacy,secrets",
        quality: str = "medium",
        enhance: bool = False,
    ) -> bytes:
        """Generate an image and return the raw bytes."""
        session = await self._get_session()
        url = f"{self.base_url}/v1/images/generations"

        payload = {
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "seed": seed,
            "quality": quality,
            "enhance": enhance,
        }

        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                if "data" in data and data["data"]:
                    item = data["data"][0]
                    # If we got a URL, download the image
                    if "url" in item:
                        img_url = item["url"]
                        async with session.get(img_url) as img_resp:
                            if img_resp.status == 200:
                                return await img_resp.read()
                            raise Exception(f"Failed to download image: {img_resp.status}")
                    # If we got b64_json, decode it
                    if "b64_json" in item:
                        import base64
                        return base64.b64decode(item["b64_json"])
                raise Exception("No image data in response")
            else:
                error_text = await resp.text()
                raise Exception(f"Image API Error {resp.status}: {error_text[:300]}")

    # ── Balance ──────────────────────────────────────────

    async def get_balance(self) -> Dict[str, Any]:
        """Check the API balance."""
        session = await self._get_session()
        url = f"{self.base_url}/v1/balance"

        async with session.get(url, headers=self._headers()) as resp:
            if resp.status == 200:
                return await resp.json()
            raise Exception(f"Balance API Error {resp.status}")

    # ── Cleanup ──────────────────────────────────────────

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
