# NullVector — Discord Privileged Intent Review Submission

## Application Overview

**App Name:** NullVector
**App ID:** (found in Discord Developer Portal)
**Current Users:** 10,000+
**Submission Deadline:** September 9, 2026

---

## What does your app do?

NullVector is an AI assistant bot that helps users with questions, coding, research, and general conversation. It operates in both DMs and server channels (when @mentioned). The bot uses the Pollinations AI API to generate responses and intelligently routes user queries to the most appropriate AI model (e.g., search models for current events, code models for programming, reasoning models for complex analysis).

Key features:
- AI-powered chat via DM or @mention
- Smart model selection — automatically picks the best AI model for each query
- Conversation memory with short-term (last 6 messages) and long-term (summaries) context
- Web search capabilities for current events and research
- Code generation and debugging assistance
- Works in both DMs and servers

---

## Why does your app need Privileged Intents?

### Message Content Intent (`MESSAGE_CONTENT`)

NullVector requires the **Message Content** privileged intent because it is fundamentally a conversational AI assistant. The bot's core functionality depends on reading the full content of user messages to:

1. **Understand user queries** — The bot cannot generate AI responses without knowing what the user asked. It needs the full text of messages to send them to the AI API for processing.

2. **Smart model routing** — The bot analyzes message content to determine the best AI model (e.g., detecting code questions → routes to code models, detecting research queries → routes to search models). This requires reading the actual message text.

3. **Conversation memory** — The bot maintains short-term and long-term memory of conversations to provide contextual responses. This requires storing and referencing previous message content.

4. **DM conversations** — Users message the bot directly for help. The bot needs to read these DM messages to respond.

### Server Members Intent

NullVector does **not** require the Server Members intent.

### Presence Intent

NullVector does **not** require the Presence intent.

---

## How does your app handle user data?

NullVector is designed with privacy and data minimization in mind:

- **In-memory storage only** — Conversation history is stored in a Python dictionary (RAM) and is not persisted to any database. All memory is cleared when the bot restarts.
- **No persistent logging** — User messages are not logged to disk or any external service.
- **No data sharing** — User data is never shared with third parties beyond the AI API provider (Pollinations) which processes messages to generate responses.
- **Opt-in interaction** — In servers, the bot only reads messages where it is directly @mentioned. It does not read or process any other messages in server channels.
- **User control** — Users can clear their conversation memory at any time using the `!clear` command.
- **No message scanning** — The bot does not scan, monitor, or analyze messages it was not directly mentioned in.

---

## Mitigation Measures

1. **Minimal intent usage** — Only `message_content` is requested. The bot does not use Server Members or Presence intents.
2. **Mention-only activation** — In servers, the bot only processes messages where it is @mentioned. It ignores all other messages.
3. **No persistent storage** — All conversation data exists only in RAM and is lost on restart.
4. **User-initiated only** — The bot never initiates conversations or sends unsolicited messages.
5. **No moderation** — The bot does not perform any moderation, logging, or surveillance functions.
6. **Clear privacy controls** — Users can clear their memory at any time.

---

## Summary

NullVector is a straightforward AI assistant that needs `message_content` to function — it cannot respond to users without reading their messages. The bot only processes messages where it is directly mentioned or in DMs, stores no persistent data, and provides users with full control over their conversation history.

---

## Notes for Reviewer

- The bot has been offline for several months and is being updated before being brought back online.
- We are updating the bot to use slash commands in addition to prefix commands, further reducing the need for message content scanning.
- The codebase is open source: https://github.com/cloudcompile/nullvector
