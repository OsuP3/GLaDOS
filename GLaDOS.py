import os
import yt_dlp
import asyncio
import random
import time
from datetime import datetime
import aiohttp
import discord
from responses import get_response

from discord.ext import bridge
from dotenv import load_dotenv, dotenv_values

load_dotenv()

class PyCordBot(bridge.Bot):
    intents = discord.Intents.all()
    token = os.getenv("DISCORD_API_TOKEN")
    intents.message_content = True
    last_command_time = time.time()

client = PyCordBot(intents=PyCordBot.intents, command_prefix = "!")

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
        if call_duration < 60:
            call_duration_msg = "a few seconds"
        elif (call_duration // 60 == 1):
            call_duration_msg = "a minute"
        elif (call_duration // 60) < 60:
            call_duration_msg = f"{int(call_duration//60)} minutes"
        elif (call_duration // 3600 == 1):
            call_duration_msg = f"an hour"
        elif (call_duration // 3600 < 24):
            call_duration_msg = f"{int(call_duration // 3600)} hours"
        elif ((call_duration // 3600) == 24):
            call_duration_msg = f"a day"
        else:
            call_duration_msg = f"{int(call_duration // (3600 * 24))} days"
        await call_start_message.edit(content=f"{call_start_message.content[:-19]} started a call that lasted {call_duration_msg}")
        call_begin_time = None

@client.event
async def on_message(message: discord.Message):
    # Channel message was sent from 
    channel = message.channel

    if(channel == remotechannel):
        await genchat.send(message.content)

    if(channel != logchannel and channel != datalogchannel):
        await logchannel.send(f"TEXT/ID: {message.id}/: {str(channel).title()}/{message.author}: {message.content}")
    
    if channel == debugchannel:
        message = message.content.lower()
        message_split = message.split(" ")
        try:
            if message_split[0] == "set":
                if message_split[1] == "call":
                    if message_split[2] == "start":
                        global call_begin_time
                        hour = message_split[3]
                        day = message_split[4]
                        dt = datetime.strptime(f"{day} {hour}", "%m-%d-%Y %H:%M")
                        call_begin_time = dt.timestamp()
                        await debugchannel.send(f"Call start time set to {dt} (timestamp: {call_begin_time})")
                    elif message_split[2] == "perms":
                        pass
                    elif  message_split[2] == "limit":
                        pass
            elif message == "reset cooldown":
                client.last_command_time = 0
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
    if(message.author != client.user and "glados" in str(message.content).lower()):
        await channel.send(get_response(message.content, message.author.name))

@client.event
async def on_message_edit(before:discord.message, after:discord.message):
    channel = discord.utils.get(guild.text_channels, name=str(before.channel))

    if(channel != logchannel):
        await logchannel.send(f"EDIT: {str(channel).title()}/{before.author}: original: ( {before.content} ) - > edited: ( {after.content} )")
@client.event
async def on_message_delete(message: discord.Message):
    channel = discord.utils.get(guild.text_channels, name=str(message.channel))

    if(channel != logchannel):
        await logchannel.send(f"DELETED: {str(channel).title()}/{message.author}: {message.content}")
@client.event
async def on_raw_message_delete(data: discord.RawMessageDeleteEvent):
    channel = client.get_channel(data.channel_id)

    if(data.cached_message == None):
        await logchannel.send(f"UNCACHED DELETED (check data) / ID = {data.message_id}")
    if(channel != logchannel and channel != datalogchannel): 
        await datalogchannel.send(f"DELETED/ID: {data.message_id}/: {str(channel).title()}/DATA: {data.cached_message}")
@client.event
async def on_raw_message_edit(data: discord.RawMessageUpdateEvent):
    channel = client.get_channel(data.channel_id)

    if(data.cached_message ==None):
        await logchannel.send(f"UNCACHED EDIT (check data) / ID = {data.message_id}") 

    if(channel != logchannel and channel != datalogchannel):
        await datalogchannel.send(f"EDIT/ID: {data.message_id}/: {str(channel).title()}/DATA: {data.cached_message}")

@client.bridge_command(description = "Ping, Pong!")
async def ping(ctx):
    latency = (str(client.latency)).split('.')[1][1:3]
    await ctx.respond(f"Pong!, Bot replied in {latency} ms")

async def main_bot():
    print("bot is starting")
    await client.start(PyCordBot().token)
    start_time = time.time()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(main_bot()))