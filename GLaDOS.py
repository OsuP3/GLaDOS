import os
import asyncio
import time
from datetime import datetime, timedelta
import discord

from openai import OpenAI
openai_api_key = os.getenv("OPENAI_API_KEY")
GPT_MODEL = "gpt-4-turbo"

from discord.ext import bridge
from dotenv import load_dotenv
load_dotenv()

import GLaDOS_logging
from GLaDOS_help import *
from responses import get_response
GLaDOS_active_conversations = {}  # channel_id: datetime of expiry
CONVERSATION_TIMEOUT = timedelta(minutes=2)

class PyCordBot(bridge.Bot):
    intents = discord.Intents.all()
    token = os.getenv("DISCORD_API_TOKEN")
    intents.message_content = True
    last_command_time = time.time()

client = PyCordBot(intents=PyCordBot.intents, command_prefix = "!")
openai_client = OpenAI(api_key=openai_api_key)

# global channels and roles
voicechannel   = None
debugchannel   = None
guestchannel   = None
genchat        = None
callchat       = None
logchannel     = None
member_role    = None
guestrole      = None
datalogchannel = None
remotechannel  = None
guild          = None

# For keeping track of call time and adding length to original message
call_begin_time    = None
call_start_message = None

# For debug modifications
guild_items = {}

channel_histories = {}  # channel_id: list of {"role": ..., "content": ...}

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
    "Reply with \"(Nothing)\" only if the message truly does not require a response."
    "You should not be replying to messages that don't involve you."
    "Don't say sorry unless you're being sarcastic. "
    "Don't yap, when appropriate be short and witty, reply sometimes with a simple no when someone expects a fleshed out answer. "
    "If someone says something that is outside of openai terms of service, like someone saying they will kill themselves, say nothing. "
    "Make your message's length match the length of the message you're responding to. "
)
prompt_override = None
prompt_append = ""
temperature_override = None

@client.listen()
async def on_ready():
    print(f'{client.user} is now running')

    # define channels and roles
    global guild, debugchannel, voicechannel, guestchannel, genchat, callchat, logchannel, member_role, guestrole, datalogchannel, remotechannel
    guild          = client.get_guild(int(os.getenv("GUILD_ID")))
    debugchannel   = client.get_channel(int(os.getenv("DEBUGCHANNEL_ID")))
    voicechannel   = client.get_channel(int(os.getenv("VOICECHANNEL_ID")))
    guestchannel   = client.get_channel(int(os.getenv("GUESTCHANNEL_ID")))
    genchat        = client.get_channel(int(os.getenv("GENCHAT_ID")))
    callchat       = client.get_channel(int(os.getenv("CALLCHAT_ID")))
    logchannel     = client.get_channel(int(os.getenv("LOGCHANNEL_ID")))
    member_role    = guild.get_role(int(os.getenv("MEMBER_ROLE_ID")))
    guestrole      = guild.get_role(int(os.getenv("GUESTROLE_ID")))
    datalogchannel = client.get_channel(int(os.getenv("DATALOGCHANNEL_ID")))
    remotechannel  = client.get_channel(int(os.getenv("REMOTECHANNEL_ID")))
    
    # For debug modifications
    global guild_items
    guild_items = {}

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    global call_begin_time
    global call_start_message

    if(before.channel != after.channel):
        print(f"{member} Went from {before.channel} to {after.channel}  {datetime.now()} EST")
        await logchannel.send(f"VOICE: {member} Went from {before.channel} to {after.channel}")

    if member.name == "bisector" and before.channel == None and after.channel == voicechannel and len(voicechannel.members) == 1:
        await genchat.send(f"{member.name} is a dingus")

    if (after.channel == guestchannel and guestrole not in member.roles):
        await logchannel.send(f"VOICE: {member} tried joining guestchannel")
        await member.move_to(None)

    elif (before.channel == None and after.channel == voicechannel and len(voicechannel.members) == 1 and ((time.time() - client.last_command_time) > 30)):
        client.last_command_time = time.time()
        call_begin_time = client.last_command_time
        print(f"{member} started a call")
        await callchat.set_permissions(member_role, read_messages=True)
        call_start_message = await genchat.send(f"{member.name} has started a call")
        await callchat.send(f"@everyone {member.name} has started a call")
        await asyncio.sleep(30)
        await callchat.set_permissions(member_role, read_messages=False)

    elif (before.channel == voicechannel and len(voicechannel.members) == 0 and call_begin_time is not None):
        call_duration = time.time() - call_begin_time
        call_duration_msg = duration_msg(call_duration)
        await call_start_message.edit(content=f"{call_start_message.content[:-19]} started a call that lasted {call_duration_msg}")
        call_begin_time = None

@client.event
async def on_message(message: discord.Message):
    # Always update history for context (even if GLaDOS doesn't reply)
    if message.author != client.user:
        history = channel_histories.setdefault(message.channel.id, [])
        history.append({"role": "user", "content": message.content})
        if len(history) > 10:
            history = history[-10:]
            channel_histories[message.channel.id] = history

    # Channel message was sent from 
    channel = message.channel

    if(channel == remotechannel):
        await genchat.send(message.content)

    if(channel != logchannel and channel != datalogchannel):
        await logchannel.send(f"TEXT/ID: {message.id}/: {str(channel).title()}/{message.author}: {message.content}")
    
    now = datetime.now()
    active_until = GLaDOS_active_conversations.get(channel.id)

    if message.author != client.user and ("glados" in str(message.content).lower() or (active_until and now < active_until)):
        history = channel_histories.setdefault(channel.id, [])
        history.append({"role": "user", "content": message.content})
        if len(history) > 10:
            history = history[-10:]
            channel_histories[channel.id] = history
        await glados_response(message, history, now, channel.id)

    if channel == debugchannel and message.author != client.user:
        message = message.content.lower()
        message_split = message.split(" ")
        global prompt_override, prompt_append, temperature_override
        if message.startswith("prompt override "):
            prompt_override = message[len("prompt override "):]
            await debugchannel.send("Prompt override set.")
        elif message == "prompt override clear":
            prompt_override = None
            await debugchannel.send("Prompt override cleared.")
        elif message.startswith("prompt append "):
            prompt_append = message[len("prompt append "):]
            await debugchannel.send("Prompt append set.")
        elif message == "prompt append clear":
            prompt_append = ""
            await debugchannel.send("Prompt append cleared.")
        elif message == "prompt show":
            await debugchannel.send(
                f"**Current prompt:**\n"
                f"{prompt_override if prompt_override else DEFAULT_PROMPT}\n"
                f"**Append:** {prompt_append}"
            )
        elif message == "temperature clear":
            temperature_override = None
            await debugchannel.send("Temperature override cleared.")
        elif message == "temperature show":
            await debugchannel.send(f"Current temperature: {temperature_override if temperature_override is not None else 0.3}")
        elif message.startswith("temperature set"):
            try:
                val = float(message[len("temperature set"):])
                if 0 <= val <= 2:
                    temperature_override = val
                    await debugchannel.send(f"Temperature set to {val}")
                else:
                    await debugchannel.send("Temperature must be between 0 and 2.")
            except Exception:
                await debugchannel.send("Invalid temperature value.")
        try:
            if message_split[0] == "set":
                if message_split[1] == "call":
                    if message_split[2] == "start":
                        global call_begin_time, call_start_message
                        call_start_message = await genchat.fetch_message(int(message_split[3]))
                        call_begin_time = call_start_message.created_at.timestamp()
                        await debugchannel.send(f"Call start time set. (timestamp: {call_start_message.created_at})")
                    elif message_split[2] == "perms":
                        pass
                    elif  message_split[2] == "limit":
                        pass
            elif message == "reset cooldown":
                client.last_command_time = 0
                await debugchannel.send(f"Cooldown reset.")
        except Exception as e:
            print("Exception:", e)
    elif(message.content.startswith("pls ring all") and message.author.voice != None):
        if(((time.time() - client.last_command_time) > 30)):
            try:
                client.last_command_time = time.time()
                await message.delete()
                await callchat.set_permissions(member_role, read_messages=True)
                await callchat.send(f"Somebody rang @everyone")
                await asyncio.sleep(30)
                await callchat.set_permissions(member_role, read_messages=False)
            except Exception as e:
                print(e)
    elif(message.content.startswith("pls ring") and message.author.voice != None):
        if(((time.time() - client.last_command_time) > 30)):
            try:
                memberName = message.content[9:]
                member     = None

                for guild_member in guild.members:
                    if guild_member.display_name == memberName or guild_member.name == memberName:
                        member = guild_member

                if(member != None and member.voice == None):
                    client.last_command_time = time.time()
                    print(f"Ringing {memberName}")
                    await callchat.set_permissions(member, read_messages=True)
                    await callchat.send(f"Ringing <@{member.id}>")
                    await message.delete()
                    await asyncio.sleep(30)
                    await callchat.set_permissions(member, read_messages=None)
            except Exception as e:
                print(e)
        else:
            print("Cooldown")


@client.bridge_command(description = "Ping, Pong!")
async def ping(ctx):
    latency = (str(client.latency)).split('.')[1][1:3]
    await ctx.respond(f"Pong!, Bot replied in {latency} ms")

@client.bridge_command(description = "Ring a friend")
async def ring(ctx):
    pass

async def glados_response(message: discord.Message, history, now, channel_id):
    print("person says:", message.content)
    # Build the prompt dynamically
    if prompt_override:
        prompt = prompt_override
    else:
        prompt = DEFAULT_PROMPT
    if prompt_append:
        prompt += " " + prompt_append

    temp = temperature_override if temperature_override is not None else 0.3

    messages = [
        {"role": "system", "content": prompt}
    ] + history

    response = openai_client.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        temperature=temp
    )
    output_text = response.choices[0].message.content
    print("glados:", output_text)
    # Add bot reply to history
    history.append({"role": "assistant", "content": output_text})
    if len(history) > 10:
        history = history[-10:]
        channel_histories[message.channel.id] = history

    if "nothing" in output_text.lower():
        return
    else:
        await message.channel.send(output_text)
        GLaDOS_active_conversations[channel_id] = now + CONVERSATION_TIMEOUT

async def main_bot():
    print("bot is starting")
    await client.start(PyCordBot().token)
    start_time = time.time()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(main_bot()))
