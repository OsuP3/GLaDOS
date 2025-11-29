import os
import asyncio
import time
from datetime import datetime, timedelta
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
GPT_MODEL = "gpt-4-turbo"

from GLaDOS_help import *  # (kept)

GLaDOS_active_conversations = {}          # channel_id -> expiry datetime
CONVERSATION_TIMEOUT = timedelta(minutes=2)
channel_histories = {}                    # channel_id -> list[{"role","content"}]

DEFAULT_PROMPT = (
    "You are GLaDOS from Portal. "
    "Only reply if you are being addressed or if it is clear from the conversation that the user is talking to you. "
    "If the conversation is not about you, reply with (Nothing). "
    "You are in a discord server with administrator privileges. "
    "Do not try to be helpful. You are not here to help or assist anyone with anything. "
    "Do not use quotes or em dashes in your replies. "
    "Occasionally use AM quotes, but speak them as your own words, do not inform anyone they are AM quotes. "
    "You should interact with users when they try, you are here as a comedic robot so don't ignore people too much. "
    "Respond with ... only if you are intentionally ignoring someone after they repeatedly try to get your attention. "
    "Do not use ... for every message. Most of the time, reply as GLaDOS would, unless you truly want to ignore the user. "
    "Reply with \"(Nothing)\" only if the message truly does not require a response. "
    "You should not be replying to messages that don't involve you. "
    "Don't say sorry unless you're being sarcastic. "
    "Don't yap, when appropriate be short and witty, reply sometimes with a simple no when someone expects a fleshed out answer. "
    "If someone says something that is outside of openai terms of service, like someone saying they will kill themselves, say nothing. "
    "Make your message's length match the length of the message you're responding to. "
)

prompt_override = None
prompt_append = ""
temperature_override = None

# Globals populated in on_ready
voicechannel = debugchannel = guestchannel = genchat = callchat = logchannel = member_role = guestrole = debugrole = datalogchannel = remotechannel = guild = None
call_begin_time = None
call_start_message = None

class GLaDOSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.token = os.getenv("DISCORD_API_TOKEN")
        self.last_command_time = time.time()

client = GLaDOSBot()
openai_client = OpenAI(api_key=openai_api_key)

@client.event
async def on_ready():
    global guild, debugchannel, voicechannel, guestchannel, genchat, callchat, logchannel
    global member_role, guestrole, debugrole, datalogchannel, remotechannel
    guild          = client.get_guild(int(os.getenv("GUILD_ID")))
    debugchannel   = client.get_channel(int(os.getenv("DEBUGCHANNEL_ID")))
    voicechannel   = client.get_channel(int(os.getenv("VOICECHANNEL_ID")))
    guestchannel   = client.get_channel(int(os.getenv("GUESTCHANNEL_ID")))
    genchat        = client.get_channel(int(os.getenv("GENCHAT_ID")))
    callchat       = client.get_channel(int(os.getenv("CALLCHAT_ID")))
    logchannel     = client.get_channel(int(os.getenv("LOGCHANNEL_ID")))
    member_role    = guild.get_role(int(os.getenv("MEMBER_ROLE_ID")))
    guestrole      = guild.get_role(int(os.getenv("GUESTROLE_ID")))
    debugrole      = guild.get_role(int(os.getenv("DEBUGROLE_ID")))
    datalogchannel = client.get_channel(int(os.getenv("DATALOGCHANNEL_ID")))
    remotechannel  = client.get_channel(int(os.getenv("REMOTECHANNEL_ID")))
    try:
        await client.tree.sync(guild=guild)
    except Exception as e:
        print("Slash sync error:", e)
    print(f"{client.user} is now running")

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    global call_begin_time, call_start_message
    if before.channel != after.channel and logchannel:
        await logchannel.send(f"VOICE: {member} Went from {before.channel} to {after.channel}")
    if member.name == "bisector" and before.channel is None and after.channel == voicechannel and len(voicechannel.members) == 1 and genchat:
        await genchat.send(f"{member.name} is a dingus")
    if after.channel == guestchannel and guestrole not in member.roles:
        if logchannel:
            await logchannel.send(f"VOICE: {member} tried joining guestchannel")
        await member.move_to(None)
    elif (before.channel is None and after.channel == voicechannel and len(voicechannel.members) == 1 and ((time.time() - client.last_command_time) > 30)):
        client.last_command_time = time.time()
        call_begin_time = client.last_command_time
        if callchat and member_role:
            await callchat.set_permissions(member_role, read_messages=True)
        if genchat:
            call_start_message = await genchat.send(f"{member.name} has started a call")
        if callchat:
            await callchat.send(f"@everyone {member.name} has started a call")
            await asyncio.sleep(30)
            await callchat.set_permissions(member_role, read_messages=False)
    elif (before.channel == voicechannel and len(voicechannel.members) == 0 and call_begin_time is not None and call_start_message):
        duration = time.time() - call_begin_time
        msg = duration_msg(duration)
        await call_start_message.edit(content=f"{call_start_message.content[:-19]} started a call that lasted {msg}")
        call_begin_time = None

def format_message_with_attachments(msg: discord.Message):
    parts = []
    if msg.content:
        parts.append(msg.content)
    for att in msg.attachments:
        parts.append(f"[attachment:{att.filename}] {att.url}")
    for st in msg.stickers:
        parts.append(f"[sticker:{st.name}]")
    if msg.embeds:
        parts.append(f"[embeds:{len(msg.embeds)}]")
    return "\n".join(parts) if parts else "(no content)"

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    hist = channel_histories.setdefault(message.channel.id, [])
    hist.append({"role": "user", "content": message.content})
    if len(hist) > 10:
        channel_histories[message.channel.id] = hist[-10:]

    if message.channel == remotechannel and genchat:
        files = []
        for att in message.attachments:
            try:
                files.append(await att.to_file())
            except:
                pass
        await genchat.send(message.content or "", files=files)

    if logchannel and datalogchannel and message.channel not in (logchannel, datalogchannel):
        await logchannel.send(f"TEXT/ID:{message.id}/ {message.channel}/{message.author}: {format_message_with_attachments(message)}")

    now = datetime.now()
    active_until = GLaDOS_active_conversations.get(message.channel.id)
    if ("glados" in message.content.lower()) or (active_until and now < active_until):
        await glados_response(message, channel_histories[message.channel.id], now, message.channel.id)

# Hybrid ping (slash + prefix)
@client.hybrid_command(name="ping", description="Ping Pong")
async def ping(ctx: commands.Context):
    ms = int(client.latency * 1000)
    await ctx.reply(f"Pong {ms}ms")

# Ring (slash + prefix)
@client.hybrid_command(name="ring", description="Ring a friend")
@commands.cooldown(1, 30, commands.BucketType.default)
async def ring(ctx: commands.Context, member: discord.Member):
    # Channels must be set
    if genchat is None or callchat is None:
        msg = "Config error: genchat/callchat not set."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    # Only allow in general chat
    if ctx.channel.id != genchat.id:
        msg = "Use this command in general chat."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    # Caller must be in voice
    if ctx.author.voice is None:
        msg = "You need to be in a voice channel to ring someone."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    # Target must not be in voice
    if member.voice is not None:
        msg = f"{member.display_name} is already in a voice channel."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    try:
        # Only the caller sees this (like before)
        ack = f"Ringing {member.display_name}"
        if ctx.interaction:
            await ctx.interaction.response.send_message(ack, ephemeral=True)
        else:
            await ctx.reply(ack)

        # Grant temporary access to callchat
        await callchat.set_permissions(member, view_channel=True, read_messages=True)

        # Notify in callchat
        await callchat.send(f"Ringing <@{member.id}>")

        # Remove after 30 seconds
        await asyncio.sleep(30)
        await callchat.set_permissions(member, view_channel=None, read_messages=None)

    except Exception as e:
        # Quiet like before, but log to console
        print("Ring error:", e)

@client.hybrid_command(name="ringall", description="Ring everyone role")
@commands.cooldown(1, 120, commands.BucketType.guild)
async def ringall(ctx: commands.Context):
    if ctx.channel != genchat:
        if ctx.interaction:
            await ctx.interaction.response.send_message("Wrong channel.", ephemeral=True)
        else:
            await ctx.reply("Wrong channel.")
        return
    if ctx.author.voice is None:
        if ctx.interaction:
            await ctx.interaction.response.send_message("Join voice first.", ephemeral=True)
        else:
            await ctx.reply("Join voice first.")
        return
    try:
        if ctx.interaction:
            await ctx.interaction.response.send_message("Ringing all", ephemeral=True)
        else:
            await ctx.reply("Ringing all")
        if callchat and member_role:
            await callchat.set_permissions(member_role, read_messages=True)
            await callchat.send("Somebody rang @everyone")
            await asyncio.sleep(30)
            await callchat.set_permissions(member_role, read_messages=False)
    except Exception as e:
        print("ringall error:", e)

@ring.error
@ringall.error
async def ring_errors(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        retry = f"{error.retry_after:.0f}"
        if ctx.interaction:
            await ctx.interaction.response.send_message(f"Cooldown {retry}s", ephemeral=True)
        else:
            await ctx.reply(f"Cooldown {retry}s")
    else:
        print("ring command error:", error)

# Single /debug slash command
@client.tree.command(name="debug", description="Debug control")
async def debug_command(interaction: discord.Interaction,
                        section: str,
                        action: str = None,
                        value: str = None):
    if interaction.channel.id != int(os.getenv("DEBUGCHANNEL_ID")):
        await interaction.response.send_message("Wrong channel.", ephemeral=True)
        return
    global call_begin_time, call_start_message, prompt_override, prompt_append, temperature_override
    await interaction.response.defer(ephemeral=True)
    try:
        if section == "resetcooldown":
            client.last_command_time = 0
            await interaction.followup.send("Cooldown reset.")
        elif section == "call_start":
            if action == "set" and value:
                try:
                    msg = await genchat.fetch_message(int(value))
                    call_start_message = msg
                    call_begin_time = msg.created_at.timestamp()
                    await interaction.followup.send(f"Call start time set ({call_begin_time}).")
                except:
                    await interaction.followup.send("Invalid message ID.")
            else:
                await interaction.followup.send("Bad call_start usage.")
        elif section == "prompt":
            if action == "override":
                if value:
                    prompt_override = value
                    await interaction.followup.send("Override set.")
                else:
                    await interaction.followup.send("Need value.")
            elif action == "append":
                if value:
                    prompt_append = value
                    await interaction.followup.send("Append set.")
                else:
                    await interaction.followup.send("Need value.")
            elif action == "clear":
                prompt_override = None
                prompt_append = ""
                await interaction.followup.send("Prompt cleared.")
            elif action == "show":
                await interaction.followup.send(f"Prompt:\n{prompt_override or DEFAULT_PROMPT}\nAppend:{prompt_append}")
            else:
                await interaction.followup.send("Unknown prompt action.")
        elif section == "temperature":
            if action == "set":
                try:
                    v = float(value)
                    if 0 <= v <= 2:
                        temperature_override = v
                        await interaction.followup.send(f"Temperature {v}")
                    else:
                        await interaction.followup.send("Out of range 0-2.")
                except:
                    await interaction.followup.send("Bad number.")
            elif action == "clear":
                temperature_override = None
                await interaction.followup.send("Temperature cleared.")
            elif action == "show":
                await interaction.followup.send(f"Temperature: {temperature_override if temperature_override is not None else 0.3}")
            else:
                await interaction.followup.send("Unknown temperature action.")
        elif section == "chatbot":
            if action == "stop":
                GLaDOS_active_conversations[interaction.channel.id] = datetime.now() - CONVERSATION_TIMEOUT
                await interaction.followup.send("Chatbot stopped.")
            else:
                await interaction.followup.send("Unknown chatbot action.")
        else:
            await interaction.followup.send("Unknown section.")
    except Exception as e:
        print("debug error:", e)
        await interaction.followup.send("Debug failed.")

async def glados_response(message: discord.Message, history, now, channel_id):
    prompt = prompt_override if prompt_override else DEFAULT_PROMPT
    if prompt_append:
        prompt += " " + prompt_append
    temp = temperature_override if temperature_override is not None else 0.3
    messages = [{"role": "system", "content": prompt}] + history
    try:
        resp = openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            temperature=temp
        )
        output = resp.choices[0].message.content
    except Exception as e:
        print("OpenAI error:", e)
        return
    history.append({"role": "assistant", "content": output})
    if len(history) > 10:
        channel_histories[message.channel.id] = history[-10:]
    if "(Nothing)" in output:
        return
    await message.channel.send(output)
    GLaDOS_active_conversations[channel_id] = now + CONVERSATION_TIMEOUT

# Logging events
@client.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not logchannel or before.channel == logchannel:
        return
    b = format_message_with_attachments(before)
    a = format_message_with_attachments(after)
    await logchannel.send(f"EDIT {before.channel}/{before.author}\nFROM: {b}\nTO: {a}")

@client.event
async def on_message_delete(message: discord.Message):
    if not logchannel or message.channel == logchannel:
        return
    await logchannel.send(f"DELETE {message.channel}/{message.author}: {format_message_with_attachments(message)}")

@client.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    if not datalogchannel:
        return
    ch = client.get_channel(payload.channel_id)
    if ch in (logchannel, datalogchannel):
        return
    if payload.cached_message:
        txt = format_message_with_attachments(payload.cached_message)
    else:
        txt = "(uncached)"
    await datalogchannel.send(f"RAW DELETE {payload.message_id} / {ch}: {txt}")

@client.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    if not datalogchannel:
        return
    ch = client.get_channel(payload.channel_id)
    if ch in (logchannel, datalogchannel):
        return
    if payload.cached_message:
        txt = format_message_with_attachments(payload.cached_message)
    else:
        txt = "(uncached)"
    await datalogchannel.send(f"RAW EDIT {payload.message_id} / {ch}: {txt}")

async def main():
    print("bot starting")
    await client.start(client.token)

if __name__ == "__main__":
    asyncio.run(main())
