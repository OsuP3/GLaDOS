from GLaDOS import client, guild, logchannel, datalogchannel
import discord

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