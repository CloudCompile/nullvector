# NullVector v2.0 — Smart AI Discord Bot

Intelligent AI assistant that automatically picks the best model for your query. Works in DMs and servers.

## What's New in v2.0

- **Persistent memory** — SQLite database instead of in-memory dict (survives restarts!)
- **Slash commands** — `/ask`, `/chat`, `/research`, `/code`, `/image`, etc.
- **Smart model routing** — Auto-picks the cheapest model that fits the task
- **Image generation** — Sana Sprint (dirt cheap at 0.0001 pollen/gen!)
- **Rate limiting** — 30/hr, 100/day per user (cost-conscious)
- **Web search** — Gemini Search for current events and research
- **Code help** — Claude Fast for programming questions
- **Cost tracking** — Know exactly how much each generation costs

## Models Used

| Task | Model | Cost | Why |
|------|-------|------|-----|
| Casual chat | openai-fast | Ultra-cheap | Default for simple questions |
| Deep conversation | openai | Standard | When messages are long |
| Web search | gemini-search | Standard | Current events, research |
| Code help | claude-fast | Standard | Programming, debugging |
| Reasoning | deepseek | Standard | Math, logic, analysis |
| Images | sana | 0.0001/gen | Dirt cheap image gen |

## Setup

1. Clone the repo
2. Copy `.env.example` to `.env`
3. Fill in your Discord token and Pollinations key
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python bot.py`

Or use the unified setup script: `python3 setup_bots.py`

## Commands

### 💬 AI Chat
- `/ask <question>` — Ask anything
- `/chat <message>` — Have a conversation
- `/research <topic>` — Web search research
- `/code <prompt>` — Coding help

### 🖼️ Image Generation
- `/image <prompt>` — Generate an image

### 📋 Memory & Info
- `/memory` — View memory stats
- `/clear` — Clear conversation memory
- `/models [category]` — List AI models
- `/model_info <model>` — Get model details
- `/quota` — Check your rate limits
- `/ping` — Check response time

## Privileged Intents

NullVector requires the **Message Content** privileged intent to read user messages for AI response generation. The bot only processes messages in DMs or when @mentioned in servers.

## Tech Stack
- **discord.py** 2.4+ — Discord bot framework
- **Pollinations API** — Text & image generation
- **SQLite** — Persistent conversation memory
- **Python 3.10+**

## License
MIT
