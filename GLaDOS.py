#needs ffmpeg
import os
import yt_dlp
import asyncio
import ffmpeg
import random
import time
import datetime
import aiohttp
import discord
from responses import get_response
#from Music import CheckMusicCommands

from discord.ext import bridge
from dotenv import load_dotenv, dotenv_values

load_dotenv()

class PyCordBot(bridge.Bot):
    intents = discord.Intents.all()
    token = os.getenv("DISCORD_API_TOKEN")
    intents.message_content = True

voice_clients = {}
yt_dl_options = {'format': 'bestaudio/best'}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)
ffmpeg_options = {'options': '-vn'}


client = PyCordBot(intents=PyCordBot.intents, command_prefix = "!")

@client.listen()
async def on_ready():
    print(f'{client.user} is now running')

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
     voicechannel = client.get_channel(1286141863622873134)
     genchat = client.get_channel(1286141863622873133)
     callchat = client.get_channel(1286333897109409883)
     logchannel = client.get_channel(1286349969271558204)
     role = client.get_guild(1286141863622873130).get_role(1286149445750100098)
     if(before.channel == None or after.channel == None):
        print(f"{member} Went from {before.channel} to {after.channel}  {datetime.datetime.now()} EST")
        await logchannel.send(f"VOICE: {member} Went from {before.channel} to {after.channel}")

     if before.channel == None and after.channel == voicechannel and len(voicechannel.members) == 1:
        print(f"{member} started a call")
        await callchat.set_permissions(role, read_messages=True)
        await genchat.send(f"{member.name} has started a call")
        await callchat.send(f"@everyone {member.name} has started a call")
        await asyncio.sleep(30)
        await callchat.set_permissions(role, read_messages=False)


@client.event
async def on_message(message: discord.Message):
    channel = discord.utils.get(client.get_guild(1286141863622873130).text_channels, name=str(message.channel))
    logchannel = client.get_channel(1286349969271558204)
    datalogchannel = client.get_channel(1286381605148950600)

    if(message.content.startswith("pls play")):
        try:
            voice_client = await message.author.voice.channel.connect()
            voice_clients[voice_client.guild.id] = voice_client
            
        except Exception as e:
            print(e)
        try:
            url = message.content.split()[2]

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))

            song = data['url']
            player = discord.FFmpegPCMAudio(song, **ffmpeg_options)

            await channel.send(f"ok")
            voice_clients[message.guild.id].play(player)
        except Exception as e:
            print(e)
    if(message.content.startswith("pls pause")):
        try:
            voice_clients[message.guild.id].pause()
            await channel.send(f"ok")
        except Exception as e:
            print(e)
    if(message.content.startswith("?pls resume")):
        try:
            voice_clients[message.guild.id].resume()
            await channel.send(f"ok")
        except Exception as e:
            print(e)
    if(message.content.startswith("pls stop")):
        try:
            voice_clients[message.guild.id].disconnect()
            await channel.send(f"ok")
        except Exception as e:
            print(e)

    if(channel != logchannel and channel != datalogchannel):
        await logchannel.send(f"TEXT/ID: {message.id}/: {str(channel).title()}/{message.author}: {message.content}")

    if(message.author != client.user and "glados" in str(message.content).lower()):
        await channel.send(get_response(message.content, message.author.name))

@client.event
async def on_message_edit(before:discord.message, after:discord.message):
    channel = discord.utils.get(client.get_guild(1286141863622873130).text_channels, name=str(before.channel))
    logchannel = client.get_channel(1286349969271558204)
    if(channel != logchannel):
        await logchannel.send(f"EDIT: {str(channel).title()}/{before.author}: original: ( {before.content} ) - > edited: ( {after.content} )")

@client.event
async def on_message_delete(message: discord.Message):
    channel = discord.utils.get(client.get_guild(1286141863622873130).text_channels, name=str(message.channel))
    logchannel = client.get_channel(1286349969271558204)
    if(channel != logchannel):
        await logchannel.send(f"DELETED: {str(channel).title()}/{message.author}: {message.content}")

@client.event
async def on_raw_message_delete(data: discord.RawMessageDeleteEvent):
    channel = client.get_channel(data.channel_id)
    logchannel = client.get_channel(1286349969271558204)
    datalogchannel = client.get_channel(1286381605148950600)
    if(data.cached_message == None):
        await logchannel.send(f"UNCACHED DELETED (check data) / ID = {data.message_id}")
    if(channel != logchannel and channel != datalogchannel): 
        await datalogchannel.send(f"DELETED/ID: {data.message_id}/: {str(channel).title()}/DATA: {data.cached_message}")
@client.event
async def on_raw_message_edit(data: discord.RawMessageUpdateEvent):
    channel = client.get_channel(data.channel_id)
    logchannel = client.get_channel(1286349969271558204)
    datalogchannel = client.get_channel(1286381605148950600)
    if(data.cached_message ==None):
        await logchannel.send(f"UNCACHED EDIT (check data) / ID = {data.message_id}") 

    if(channel != logchannel and channel != datalogchannel):
        await datalogchannel.send(f"EDIT/ID: {data.message_id}/: {str(channel).title()}/DATA: {data.cached_message}")

@client.bridge_command(description = "Ping, Pong!")
async def ping(ctx):
    latency = (str(client.latency)).split('.')[1][1:3]
    await ctx.respond(f"Pong!, Bot replied in {latency} ms")

for filename in os.listdir("./cogs"):
    if filename.endswith(".py"):
        client.load_extension(f"cogs.{filename[:-3]}")
        print(f"loaded {filename}")

async def main_bot():
    print("bot is starting")
    
    await client.start(PyCordBot().token)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(main_bot()))




