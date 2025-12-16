import discord
from discord.ext import commands
import aiohttp
import asyncio
import json
from collections import defaultdict
from datetime import datetime

# Configuration
DISCORD_TOKEN = "DISCORD_TOKE_HERE"
POLLINATIONS_API_KEY = "POLLINATIONS_SK"
API_BASE = "https://gen.pollinations.ai"

# Bot setup - DMs and Servers
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Memory storage: {channel_id: [messages]}
conversation_memory = defaultdict(list)

# Model information for the AI to choose from
MODEL_INFO = """
Available models and their use cases:
- openai: Default model, balanced performance for general tasks
- openai-large: Complex reasoning, detailed analysis, multi-step problems
- gemini-search: Simple web searches, current events, quick facts
- perplexity-fast: Medium complexity web searches, research tasks
- perplexity-reasoning: Complex research, deep analysis with web data
- claude: Code generation, programming tasks, technical explanations
- claude-large: Complex code generation, system design, advanced programming
"""


async def make_api_request(messages, model="openai", stream=False):
    """Make request to Pollinations API"""
    url = f"{API_BASE}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": 1
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status == 200:
                if stream:
                    return response
                data = await response.json()
                return data["choices"][0]["message"]["content"]
            else:
                error_text = await response.text()
                raise Exception(f"API Error {response.status}: {error_text}")


def ensure_message_alternation(messages):
    """
    Ensure messages properly alternate between user and assistant roles.
    System messages should be at the start, followed by alternating user/assistant.
    """
    if not messages:
        return []
    
    # Separate system messages from conversation messages
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    conversation_messages = [msg for msg in messages if msg["role"] != "system"]
    
    if not conversation_messages:
        return system_messages
    
    # Ensure alternating pattern
    cleaned_messages = []
    last_role = None
    
    for msg in conversation_messages:
        current_role = msg["role"]
        
        # Skip consecutive messages with the same role
        if current_role == last_role:
            # Merge content if same role appears consecutively
            if cleaned_messages:
                cleaned_messages[-1]["content"] += "\n" + msg["content"]
            continue
        
        cleaned_messages.append(msg)
        last_role = current_role
    
    # Ensure we start with a user message (after system)
    if cleaned_messages and cleaned_messages[0]["role"] != "user":
        cleaned_messages = cleaned_messages[1:]
    
    # Ensure we end with a user message
    if cleaned_messages and cleaned_messages[-1]["role"] != "user":
        cleaned_messages = cleaned_messages[:-1]
    
    return system_messages + cleaned_messages


async def choose_model(user_message, context):
    """Use AI to intelligently choose the best model for the task"""
    selection_prompt = f"""You are a model selection expert. Analyze the user's message and choose the BEST model.

{MODEL_INFO}

Context of conversation: {context[:200] if context else "No prior context"}

User message: "{user_message}"

Analyze:
1. Does it need web search? (current events, facts, news)
2. Is it about coding? (programming, debugging, code review)
3. Is it complex reasoning? (math, logic, analysis)
4. Is it a simple question? (casual chat, basic info)

Respond with ONLY the model name, nothing else. Choose ONE:
openai, openai-large, gemini-search, perplexity-fast, perplexity-reasoning, claude, claude-large"""

    try:
        selection_messages = [
            {"role": "system", "content": "You are a model selector. Respond with ONLY the model name."},
            {"role": "user", "content": selection_prompt}
        ]
        
        # Ensure proper alternation before API call
        selection_messages = ensure_message_alternation(selection_messages)
        
        model_choice = await make_api_request(selection_messages, model="openai")
        
        model_choice = model_choice.strip().lower()
        valid_models = ["openai", "openai-large", "gemini-search", "perplexity-fast", 
                       "perplexity-reasoning", "claude", "claude-large"]
        
        if model_choice in valid_models:
            return model_choice
        return "openai"
    except Exception as e:
        print(f"Model selection error: {e}")
        return "openai"


def create_summary(messages):
    """Create a summary of older messages for LTM"""
    if len(messages) <= 6:
        return ""
    
    old_messages = messages[:-6]
    summary_text = "Previous conversation summary:\n"
    for msg in old_messages[-10:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"][:100]
        summary_text += f"{role}: {content}...\n"
    
    return summary_text


def add_to_memory(channel_id, role, content):
    """Add message to conversation memory"""
    conversation_memory[channel_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    
    # Keep only last 50 messages to prevent memory bloat
    if len(conversation_memory[channel_id]) > 50:
        conversation_memory[channel_id] = conversation_memory[channel_id][-50:]


def get_context_messages(channel_id):
    """Get STM (last 6) and LTM (summary) for context"""
    messages = conversation_memory[channel_id]
    
    if len(messages) == 0:
        return []
    
    # Get STM (last 6 messages)
    stm_messages = messages[-6:]
    
    # Build context with proper user/assistant alternation
    context_messages = []
    
    for msg in stm_messages:
        context_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    return context_messages


@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")
    print(f"📊 Connected to {len(bot.guilds)} servers")
    print(f"💬 Works in DMs and servers (mention me in servers)")
    await bot.change_presence(activity=discord.Game(name="DM or @mention me | AI Assistant"))


@bot.event
async def on_message(message):
    # Ignore own messages
    if message.author == bot.user:
        return
    
    # Process commands first
    await bot.process_commands(message)
    
    # Check if bot should respond
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    
    # Only respond in DMs or when mentioned in servers
    if not (is_dm or is_mentioned):
        return
    
    # Remove bot mention from message in servers
    content = message.content
    if is_mentioned:
        content = content.replace(f'<@{bot.user.id}>', '').strip()
    
    if not content:
        return
    
    channel_id = message.channel.id
    
    try:
        # Show typing indicator
        async with message.channel.typing():
            # Add user message to memory
            add_to_memory(channel_id, "user", content)
            
            # Get conversation context
            context_messages = get_context_messages(channel_id)
            context_text = "\n".join([f"{m['role']}: {m['content'][:100]}" for m in context_messages[-3:]])
            
            # Choose best model
            selected_model = await choose_model(content, context_text)
            
            # Prepare messages for API
            system_message = {
                "role": "system",
                "content": """You are a helpful, friendly AI assistant. You can:
- Answer questions on any topic
- Help with coding and technical problems
- Search the web for current information (when using search models)
- Have natural conversations
- Provide detailed explanations

Be concise but thorough. Use markdown for formatting when appropriate."""
            }
            
            # Add LTM summary to system message if we have old messages
            if len(conversation_memory[channel_id]) > 6:
                ltm_summary = create_summary(conversation_memory[channel_id])
                system_message["content"] += f"\n\n{ltm_summary}"
            
            # Build initial message list
            api_messages = [system_message] + context_messages
            
            # CRITICAL FIX: Ensure proper message alternation before sending to API
            api_messages = ensure_message_alternation(api_messages)
            
            # Get response from chosen model
            response = await make_api_request(api_messages, model=selected_model)
            
            # Add assistant response to memory
            add_to_memory(channel_id, "assistant", response)
            
            # Check for <think></think> tags and extract reasoning
            reasoning = None
            display_response = response
            
            if "<think>" in response and "</think>" in response:
                start_idx = response.find("<think>")
                end_idx = response.find("</think>") + len("</think>")
                reasoning = response[start_idx + 7:end_idx - 8]  # Extract content between tags
                display_response = response[:start_idx] + response[end_idx:]
                display_response = display_response.strip()
            
            # Limit response to 2000 characters
            if len(display_response) > 1950:
                display_response = display_response[:1950] + "..."
            
            # Add model info
            display_response += f"\n\n*Model: {selected_model}*"
            
            # Create view with button if reasoning exists (no timeout)
            if reasoning:
                view = discord.ui.View(timeout=None)
                
                class ReasoningButton(discord.ui.Button):
                    def __init__(self, reasoning_text):
                        super().__init__(style=discord.ButtonStyle.primary, label="Show Reasoning")
                        self.reasoning_text = reasoning_text
                    
                    async def callback(self, interaction: discord.Interaction):
                        # Limit reasoning to 2000 chars
                        reasoning_display = self.reasoning_text
                        if len(reasoning_display) > 1950:
                            reasoning_display = reasoning_display[:1950] + "..."
                        
                        await interaction.response.send_message(
                            f"**🧠 Reasoning Process:**\n{reasoning_display}",
                            ephemeral=True
                        )
                
                view.add_item(ReasoningButton(reasoning))
                await message.channel.send(display_response, view=view)
            else:
                await message.channel.send(display_response)
    
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        await message.channel.send(error_msg)
        print(f"Error processing message: {e}")


@bot.command(name="clear")
async def clear_memory(ctx):
    """Clear conversation memory for this channel/DM"""
    channel_id = ctx.channel.id
    conversation_memory[channel_id] = []
    await ctx.send("🧹 Conversation memory cleared!")


@bot.command(name="memory")
async def show_memory(ctx):
    """Show current conversation memory stats"""
    channel_id = ctx.channel.id
    messages = conversation_memory[channel_id]
    
    embed = discord.Embed(title="💾 Memory Stats", color=discord.Color.blue())
    embed.add_field(name="Total Messages", value=len(messages), inline=True)
    embed.add_field(name="STM (Recent)", value=min(6, len(messages)), inline=True)
    embed.add_field(name="LTM (Summary)", value="Yes" if len(messages) > 6 else "No", inline=True)
    
    await ctx.send(embed=embed)


@bot.command(name="models")
async def list_models(ctx):
    """List available AI models and their purposes"""
    embed = discord.Embed(
        title="🤖 Available AI Models",
        description="I automatically choose the best model for your query!",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="General Purpose",
        value="**openai**: Default balanced model\n**openai-large**: Complex reasoning",
        inline=False
    )
    
    embed.add_field(
        name="Web Search",
        value="**gemini-search**: Simple searches\n**perplexity-fast**: Medium searches\n**perplexity-reasoning**: Deep research",
        inline=False
    )
    
    embed.add_field(
        name="Code Generation",
        value="**claude**: Standard coding\n**claude-large**: Complex programming",
        inline=False
    )
    
    await ctx.send(embed=embed)


@bot.command(name="help")
async def help_command(ctx):
    """Show help information"""
    embed = discord.Embed(
        title="🤖 AI Assistant Help",
        description="I'm an intelligent AI assistant that automatically chooses the best model for your needs!",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="How to Use",
        value="• **DMs**: Just message me directly\n• **Servers**: Mention me with @BotName",
        inline=False
    )
    
    embed.add_field(
        name="Commands",
        value="`!clear` - Clear conversation memory\n`!memory` - Show memory stats\n`!models` - List available models\n`!help` - Show this message",
        inline=False
    )
    
    embed.add_field(
        name="Features",
        value="✅ Smart model selection\n✅ Conversation memory (LTM + STM)\n✅ Web search capabilities\n✅ Code generation\n✅ Works in DMs and servers",
        inline=False
    )
    
    await ctx.send(embed=embed)


# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `!help` to see available commands.")
    else:
        await ctx.send(f"❌ An error occurred: {str(error)}")
        print(f"Command error: {error}")


# Run the bot
if __name__ == "__main__":
    print("🚀 Starting Discord AI Bot...")
    print("📝 Features:")
    print("   - Smart model selection")
    print("   - LTM (summaries) + STM (last 6 messages)")
    print("   - Works in DMs and servers")
    print("   - Web search and code generation")
    print("\n⏳ Connecting to Discord...")
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        print("\n⚠️  Make sure you've set your DISCORD_TOKEN and POLLINATIONS_API_KEY!")
