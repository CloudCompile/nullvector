#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NullVector v3.0 — Pollinations API Client

Handles text and image generation via the Pollinations API.
v3.0: Retry logic, unified model set, chat_completions_simple helper.
"""

from __future__ import annotations
import asyncio
import aiohttp
import json
import logging
from typing import Optional, List, Dict, Any

from config import POLLINATIONS_KEY, POLLINATIONS_BASE_URL, POLLINATIONS_MEDIA_URL

log = logging.getLogger("nullvector.pollinations")

# ── Retry Configuration ────────────────────────────────────
MAX_RETRIES = 2          # Number of retries on failure
RETRY_DELAY = 1.0        # Seconds to wait between retries
RETRY_BACKOFF = 2.0      # Multiplier for each retry (1s, 2s, 4s...)


class PollinationsAPI:
    """Async client for the Pollinations AI API with retry logic."""

    def __init__(self):
        self.base_url = POLLINATIONS_BASE_URL
        self.media_url = POLLINATIONS_MEDIA_URL
        self.api_key = POLLINATIONS_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300),
            )
        return self._session

    def _headers(self) -> Dict[str, str]:
        """Build request headers with auth."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _retry_request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Make an HTTP request with automatic retry on failure.

        Retries on:
          - Server errors (5xx)
          - Timeouts
          - Connection errors
        Does NOT retry on:
          - Client errors (4xx) — those are the caller's fault
          - Successful responses
        """
        session = await self._get_session()
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                if method.upper() == "POST":
                    resp = await session.post(url, **kwargs)
                else:
                    resp = await session.get(url, **kwargs)

                # Retry on 5xx server errors
                if resp.status >= 500:
                    body = await resp.text()
                    last_error = f"Server error {resp.status}: {body[:300]}"
                    log.warning(f"Retry {attempt + 1}/{MAX_RETRIES}: {last_error}")
                    if attempt < MAX_RETRIES:
                        delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                        await asyncio.sleep(delay)
                    continue

                # Don't retry on 4xx errors
                return resp

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = str(e)
                log.warning(f"Retry {attempt + 1}/{MAX_RETRIES}: Connection error: {last_error}")
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                    await asyncio.sleep(delay)
                continue

        # All retries exhausted
        raise Exception(f"API request failed after {MAX_RETRIES + 1} attempts. Last error: {last_error}")

    # ── Text Generation ──────────────────────────────────

    async def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: str = "openai-fast",
        temperature: float = 1.0,
        max_tokens: int = 500,
        safe: str = "privacy,secrets",
    ) -> str:
        """Send a chat completion request and return the response text.

        Automatically retries on failure (up to MAX_RETRIES times).
        """
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                session = await self._get_session()
                async with session.post(url, headers=self._headers(), json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            content = data["choices"][0]["message"]["content"]
                            if not content:
                                # Try reasoning_content fallback
                                content = data["choices"][0]["message"].get("reasoning_content", "") or ""
                            if not content:
                                log.warning(f"Empty response from {model}, attempt {attempt + 1}")
                                last_error = "empty_response"
                                if attempt < MAX_RETRIES:
                                    await asyncio.sleep(RETRY_DELAY * (RETRY_BACKOFF ** attempt))
                                    continue
                                return ""
                            return content
                        except (KeyError, IndexError) as e:
                            log.error(f"Unexpected API response format: {json.dumps(data)[:500]}")
                            return ""
                    elif resp.status >= 500:
                        error_text = await resp.text()
                        last_error = f"Server error {resp.status}: {error_text[:300]}"
                        log.warning(f"Retry {attempt + 1}/{MAX_RETRIES}: {last_error}")
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY * (RETRY_BACKOFF ** attempt))
                            continue
                        raise Exception(last_error)
                    else:
                        error_text = await resp.text()
                        raise Exception(f"API Error {resp.status}: {error_text[:300]}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = str(e)
                log.warning(f"Retry {attempt + 1}/{MAX_RETRIES}: Connection error: {last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (RETRY_BACKOFF ** attempt))
                    continue

        # All retries exhausted
        log.error(f"All retries failed for model={model}. Last error: {last_error}")
        return ""

    async def chat_completions_simple(
        self,
        messages: List[Dict[str, Any]],
        model: str = "openai-fast",
        **kwargs,
    ) -> str:
        """Simplified chat completions — returns just the assistant text.

        Same as chat_completions but with a cleaner interface.
        """
        return await self.chat_completions(messages, model=model, **kwargs)

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
        """Generate an image and return the raw bytes.

        Uses POST /v1/images/generations with retry logic.
        """
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

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                session = await self._get_session()
                async with session.post(url, headers=self._headers(), json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "data" in data and data["data"]:
                            item = data["data"][0]
                            if "url" in item:
                                img_url = item["url"]
                                async with session.get(img_url) as img_resp:
                                    if img_resp.status == 200:
                                        return await img_resp.read()
                                    raise Exception(f"Failed to download image: {img_resp.status}")
                            if "b64_json" in item:
                                import base64
                                return base64.b64decode(item["b64_json"])
                        raise Exception("No image data in response")
                    elif resp.status >= 500:
                        error_text = await resp.text()
                        last_error = f"Image API Server error {resp.status}: {error_text[:300]}"
                        log.warning(f"Image retry {attempt + 1}/{MAX_RETRIES}: {last_error}")
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY * (RETRY_BACKOFF ** attempt))
                            continue
                        raise Exception(last_error)
                    else:
                        error_text = await resp.text()
                        raise Exception(f"Image API Error {resp.status}: {error_text[:300]}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = str(e)
                log.warning(f"Image retry {attempt + 1}/{MAX_RETRIES}: Connection error: {last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (RETRY_BACKOFF ** attempt))
                    continue

        raise Exception(f"Image generation failed after {MAX_RETRIES + 1} attempts. Last error: {last_error}")

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
