import asyncio
from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from openai import OpenAI
import os
import random
import requests
import sqlite3
import time

from glados_db import ConfigCache, get_db_connection
from glados_help import *

from media_downloader import handle_media_links

# Config from all the different servers
config = ConfigCache(get_db_connection())

# Load env
load_dotenv()

# Set up dictionaries
channel_histories           = {}          # channel_id -> list[{"role","content"}]
guest_has_vc_access         = {}
guest_access_timer          = {}

call_begin_time     = None
call_start_message  = None
unique_member_roles = None

class GLaDOSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.token = os.getenv("DISCORD_API_TOKEN")
        self.last_command_time = time.time()

client = GLaDOSBot()

@client.event
async def on_ready() -> None:
    config.load_all()
    print("Config cache loaded")
    print(f"{client.user} is now running")

@client.command(name="sync")
async def sync_commands(ctx) -> None:
    # Manual sync command to fix "command not found" issues
    # Checks if user has administrator permissions or is the host
    is_admin = ctx.author.guild_permissions.administrator
    host_id = ctx.guild.owner_id
    is_host = host_id and str(ctx.author.id) == str(host_id)

    if is_admin or is_host:
        msg = await ctx.send("Syncing commands...")
        try:
            if ctx.guild:
                client.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
                await msg.edit(content=f"Synced {len(synced)} commands to the current guild.")
            else:
                await msg.edit(content="This command must be used in a guild.")
        except Exception as e:
            await msg.edit(content=f"Sync failed: {e}")
    else:
        await ctx.send("You are not authorized to sync commands.")

###################################################################################################
#                                   EVENT HANDLING BELOW                                          #
#                                                                                                 #
###################################################################################################

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    global call_begin_time, call_start_message
    guild = member.guild

    logchannel   = client.get_channel(config.get_channel(guild.id, 'log-chat'))
    genchat      = client.get_channel(config.get_channel(guild.id, 'general-chat'))
    voicechannel = client.get_channel(config.get_channel(guild.id, 'main-vc'))
    callchat     = client.get_channel(config.get_channel(guild.id, 'ringing-chat'))
    guestchannel = client.get_channel(config.get_channel(guild.id, 'guest-vc'))

    guestrole   = guild.get_role(config.get_role(guild.id, 'guest'))
    member_role = guild.get_role(config.get_role(guild.id, 'member'))

    # Log movement
    if before.channel != after.channel and logchannel:
        await logchannel.send(f"VOICE: {member} Went from {before.channel} to {after.channel}")
        print(f"{member} Went from {before.channel} to {after.channel}  {datetime.now()} EST")

    # Bisector doing bisector things
    if member.name == "bisector" and before.channel == None and after.channel == voicechannel and len(voicechannel.members) == 1 and genchat:
        await genchat.send(f"{member.name} is a dingus")

    # Naughty member
    if after.channel == guestchannel and guestrole not in member.roles:
        if logchannel:
            await logchannel.send(f"VOICE: {member} tried joining guestchannel")
        await member.move_to(None)

    # Call started
    elif ((member_role in member.roles) and before.channel == None and after.channel == voicechannel \
            and len(voicechannel.members) == 1 and ((time.time() - client.last_command_time) > 30)):
        # Set cooldown
        client.last_command_time = time.time()
        call_begin_time = client.last_command_time
        if callchat and member_role:
            await callchat.set_permissions(member_role, read_messages=True)
        if genchat:
            print(f"{member} started a call")
            call_start_message = await genchat.send(f"{member.name} has started a call")
        if callchat:
            await callchat.send(f"{member.name} has started a call @everyone ")
            await asyncio.sleep(30)
            await callchat.set_permissions(member_role, read_messages=False)

    # Temp access for guests
    elif (guestrole in member.roles):
        if (before.channel != voicechannel and after.channel == voicechannel):
            # Joins voicechannel, timer stopped and guest is granted access if they dont already have
            print(guest_has_vc_access.get(member.name, False))
            if (guest_has_vc_access.get(member.name, False) == False):
                # Member was just dragged, give them permissions
                if logchannel:
                    await logchannel.send(f"VOICE: guest {member} has gained vc access ")
                await voicechannel.set_permissions(member, view_channel=True, connect=True)
                guest_has_vc_access[member.name] = True
            guest_access_timer[member.name] = False

        elif (guest_access_timer.get(member.name, False) == False and before.channel == voicechannel and after.channel != voicechannel):
            # Guest left, and does not currently have a countdown running, start their timer
            guest_access_timer[member.name] = True
            timeout_seconds = 60 # Guests have a minute after leaving to keep access
            for i in range(0, timeout_seconds):
                await asyncio.sleep(1)
                # User rejoins in time
                if guest_access_timer.get(member.name, False) == False:
                    break
            else:
                # Timer runs out, user loses perms
                await voicechannel.set_permissions(member, connect=None, view_channel=None)
                guest_access_timer[member.name] = False
                guest_has_vc_access[member.name] = False
                if logchannel:
                    await logchannel.send(f"VOICE: guest {member} has lost vc access ")

    # Call ended
    elif (before.channel == voicechannel and len(voicechannel.members) == 0 and call_begin_time != None and call_start_message):
        duration = time.time() - call_begin_time
        msg = duration_msg(duration)
        await call_start_message.edit(content=f"{call_start_message.content[:-19]} started a call that lasted {msg}")
        call_begin_time = None

def format_message_with_attachments(msg: discord.Message) -> str:
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
async def on_message(message: discord.Message) -> None:
    # Dont handle bot's own messages
    if message.author == client.user:
        return
    # DMs have no guild, so no config to look up
    if not message.guild:
        await client.process_commands(message)
        return

    guild_id       = message.guild.id
    genchat        = client.get_channel(config.get_channel(guild_id, 'general-chat'))
    remotechannel  = client.get_channel(config.get_channel(guild_id, 'remote-chat'))
    logchannel     = client.get_channel(config.get_channel(guild_id, 'log-chat'))
    datalogchannel = client.get_channel(config.get_channel(guild_id, 'datalog-chat'))

    # Save last 10 messages (for chatbot memory)
    hist = channel_histories.setdefault(message.channel.id, [])
    hist.append({"role": "user", "content": message.content})
    if len(hist) > 10:
        channel_histories[message.channel.id] = hist[-10:]

    # Auto-download linked media (YouTube / Twitter / TikTok)
    if genchat:
        await handle_media_links(message)

    # Bot chat remote control
    if message.channel == remotechannel and genchat:
        files = []
        for att in message.attachments:
            try:
                files.append(await att.to_file())
            except:
                pass
        await genchat.send(message.content or "", files=files)

    # Basic message log
    if logchannel and datalogchannel and message.channel not in (logchannel, datalogchannel):
        await logchannel.send(f"TEXT/ID:{message.id}/ {message.channel}/{message.author}: {format_message_with_attachments(message)}",
                                allowed_mentions=discord.AllowedMentions.none())

    # Handle chatbot conversation if applicable (disabled for now)
    # now = datetime.now()
    # active_until = GLaDOS_active_conversations.get(message.channel.id)
    # if ("glados" in message.content.lower()) or (active_until and now < active_until):
    #     await glados_response(message, channel_histories[message.channel.id], now, message.channel.id)

    # IMPORTANT: needed so hybrid/prefix commands still fire
    await client.process_commands(message)

###################################################################################################
#                                   BOT COMMANDS BELOW                                            #
#                                                                                                 #
###################################################################################################

@client.hybrid_command(name="ping", description="Ping Pong")
async def ping(ctx: commands.Context) -> None:
    ms = int(client.latency * 1000)
    print(f"Pong!")
    await ctx.reply(f"Pong {ms}ms")

@client.hybrid_command(name="ring", description="Ring a friend")
@commands.cooldown(1, 30, commands.BucketType.default)
async def ring(ctx: commands.Context, member: discord.Member) -> None:
    guild_id = ctx.guild.id
    genchat        = client.get_channel(config.get_channel(guild_id, 'general-chat'))
    remotechannel  = client.get_channel(config.get_channel(guild_id, 'remote-chat'))
    logchannel     = client.get_channel(config.get_channel(guild_id, 'log-chat'))
    datalogchannel = client.get_channel(config.get_channel(guild_id, 'datalog-chat'))
    callchat       = client.get_channel(config.get_channel(guild_id, 'ringing-chat'))

    # Channels must be set
    if genchat == None or callchat == None:
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
    if ctx.author.voice == None:
        msg = "You need to be in a voice channel to ring someone."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    # Target must not be in voice
    if member.voice != None:
        msg = f"{member.display_name} is already in a voice channel."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    try:
        # Only the caller sees this
        ack = f"Ringing {member.display_name}"
        print(ack)
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
        print("Ring error:", e)

@client.hybrid_command(name="ringall", description="Ring everyone role")
@commands.cooldown(1, 120, commands.BucketType.guild)
async def ringall(ctx: commands.Context) -> None:
    guild_id = ctx.guild.id
    genchat        = client.get_channel(config.get_channel(guild_id, 'general-chat'))
    remotechannel  = client.get_channel(config.get_channel(guild_id, 'remote-chat'))
    logchannel     = client.get_channel(config.get_channel(guild_id, 'log-chat'))
    datalogchannel = client.get_channel(config.get_channel(guild_id, 'datalog-chat'))
    callchat       = client.get_channel(config.get_channel(guild_id, 'ringing-chat'))

    guestrole   = ctx.guild.get_role(config.get_role(guild_id, 'guest'))
    member_role = ctx.guild.get_role(config.get_role(guild_id, 'member'))

    # Wrong channel
    if ctx.channel != genchat:
        if ctx.interaction:
            await ctx.interaction.response.send_message("Wrong channel.", ephemeral=True)
        else:
            await ctx.reply("Wrong channel.")
        return
    # Caller not in voice
    if ctx.author.voice == None:
        if ctx.interaction:
            await ctx.interaction.response.send_message("Join voice first.", ephemeral=True)
        else:
            await ctx.reply("Join voice first.")
        return
    try:
        print("Ringing All")
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
async def ring_errors(ctx: commands.Context, error) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        retry = f"{error.retry_after:.0f}"
        if ctx.interaction:
            await ctx.interaction.response.send_message(f"Cooldown {retry}s", ephemeral=True)
        else:
            await ctx.reply(f"Cooldown {retry}s")
    else:
        print("ring command error:", error)


# default order and color assignments
# saga(71368a), skira(ce0e24), bop(f0ed52), tori(e9cadc), ari(000001), gab(9b59b6), yeyo(3061e3), osu(33cc99), glados(401901), bisector(95a7ff), milk(dcdcdc)

async def safe_edit_role(role, color = None, nick = None):
    for _ in range(3):  # try up to 3 times
        try:
            if color:
                await role.edit(color=color)
            if nick:
                for member in role.members:
                    await member.edit(nick=nick)
            return
        except discord.HTTPException as e:
            print(f"Edit failed ({e}), retrying in 5s...")
            await asyncio.sleep(5)


@client.hybrid_command(name="scramble", description="Scramble!")
@commands.cooldown(1, 30, commands.BucketType.guild)
async def scramble(ctx: commands.Context):
    await ctx.interaction.response.send_message("Scrambling Currently Disabled", ephemeral=True)
    return
    # NOTE: unique_member_roles is never populated anywhere in this file.
    # This command will currently do nothing (loop over None/empty).
    # It needs to be sourced per-guild, e.g. a new 'scramble_roles' entry
    # in server_roles (comma-separated ids) or its own table, then loaded
    # here via config before this loop runs.
    global unique_member_roles
    colorlist  = [0x71368a, 0xce0e24, 0xf0ed52, 0xe9cadc, 0x000001, 0x9b59b6, 0x3061e3, 0x33cc99, 0x401901, 0x95a7ff, 0xdcdcdc] # default configuration
    colornames = ["Cyan", "Black", "Green", "Pink", "Brown", "Orange", "Periwinkle Purple", "Purple", "Red", "White", "Yellow"]

    await ctx.interaction.response.send_message("Scrambling!", ephemeral=True)
    for member_role in (unique_member_roles or []):
        await safe_edit_role(member_role, color=discord.Color(colorlist.pop(random.randint(0, len(colorlist)-1))))

        # Server owner cannot have their nick changes by bot
        if member_role.name != "osu":
            await safe_edit_role(member_role, nick=colornames.pop(random.randint(0, len(colornames)-1)))
    await ctx.interaction.edit_original_response(content="Scrambled!")

@scramble.error
async def scramble_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        retry = f"{error.retry_after:.1f}"
        msg = f"Cooldown {retry}s"
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
    else:
        print("Scramble error:", error)


@client.hybrid_command(name="togglepausevid", description="Pause/Unpause Osu's Video")
@commands.cooldown(1, 5, commands.BucketType.user)
async def togglepausevid(ctx: commands.Context) -> None:
    print(f"Pause prompted")
    await ctx.interaction.response.send_message("Togglepausevid Currently Disabled", ephemeral=True)
    return
    guild_id = ctx.guild.id
    voicechannel = client.get_channel(config.get_channel(guild_id, 'main-vc'))
    pause_role   = ctx.guild.get_role(config.get_role(guild_id, 'pause'))
    logchannel   = client.get_channel(config.get_channel(guild_id, 'log-chat'))

    # Check permissions
    if pause_role and pause_role not in ctx.author.roles:
        msg = "You don't have permission to use this command."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    # Check voice state
    if not ctx.author.voice or ctx.author.voice.channel != voicechannel:
        msg = "You must be in the voice channel to use this command."
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
        return

    # Check host state
    host_id = os.getenv("HOST_ID")
    if host_id:
        host_member = ctx.guild.get_member(int(host_id))
        if not host_member or not host_member.voice or host_member.voice.channel != voicechannel:
            msg = "Command only works when the host is in the voice channel."
            if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
            else: await ctx.reply(msg)
            return
        if not host_member.voice.self_stream:
            msg = "Command only works when the host is sharing their screen."
            if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
            else: await ctx.reply(msg)
            return

    try:
        # Create the flag file for SSH bridge
        # Use absolute path to ensure it matches what pc_connector looks for
        flag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media_toggle_request.flag")
        with open(flag_path, "w") as f:
            f.write(str(time.time()))

        print(f"Flag created at: {flag_path}") # Debug print

        msg = " **Media toggle triggered!**"
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)

        if logchannel:
            await logchannel.send(f"PAUSE: {ctx.author} used togglepausevid command")

    except Exception as e:
        err_msg = f"**Error triggering toggle:** {str(e)}"
        if ctx.interaction: await ctx.interaction.response.send_message(err_msg, ephemeral=True)
        else: await ctx.reply(err_msg)

@togglepausevid.error
async def togglepausevid_error(ctx: commands.Context, error) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        retry = f"{error.retry_after:.1f}"
        msg = f"Cooldown {retry}s"
        if ctx.interaction: await ctx.interaction.response.send_message(msg, ephemeral=True)
        else: await ctx.reply(msg)
    else:
        print("togglepausevid error:", error)

###################################################################################################
#                                  DEBUG COMMANDS BELOW                                           #
#                                                                                                 #
###################################################################################################

@client.tree.command(name="debug", description="Debug control")
async def debug_command(interaction: discord.Interaction,
                        section: str,
                        action: str = None,
                        value: str = None) -> None:
    guild_id = interaction.guild.id
    debug_channel_id = config.get_channel(guild_id, 'debug-chat')

    if interaction.channel.id != debug_channel_id and not (section == "chatbot" and action == "stop"):
        await interaction.response.send_message("Wrong channel.", ephemeral=True)
        return
    global call_begin_time, call_start_message, prompt_override, prompt_append, temperature_override
    await interaction.response.defer(ephemeral=True)
    try:
        if section == "scramble":
            if action == "off":
                pass
        elif section == "resetcooldown":
            client.last_command_time = 0
            await interaction.followup.send("Cooldown reset.")
        elif section == "call_start":
            if action == "set" and value:
                try:
                    genchat = client.get_channel(config.get_channel(guild_id, 'general-chat'))
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
                    prompt_append += value
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
                await interaction.followup.send(f"Temperature: {temperature_override if temperature_override != None else 0.3}")
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

# async def glados_response(message: discord.Message, history, now, channel_id) -> None:
#     print("person says:", message.content)
#     prompt = prompt_override if prompt_override else DEFAULT_PROMPT
#     if prompt_append:
#         prompt += " " + prompt_append
#     temp = temperature_override if temperature_override != None else 0.3
#     messages = [{"role": "system", "content": prompt}] + history
#     try:
#         resp = openai_client.chat.completions.create(
#             model=GPT_MODEL,
#             messages=messages,
#             temperature=temp
#         )
#         output = resp.choices[0].message.content
#     except Exception as e:
#         print("OpenAI error:", e)
#         return
#     history.append({"role": "assistant", "content": output})
#     if len(history) > 10:
#         channel_histories[message.channel.id] = history[-10:]
#     if "(Nothing)" in output:
#         return
#     await message.channel.send(output)
#     print("glados:", output)
#     GLaDOS_active_conversations[channel_id] = now + CONVERSATION_TIMEOUT


###################################################################################################
#                                   MESSAGE EVENT HANDLING BELOW                                  #
#                                                                                                 #
###################################################################################################
# Logging events
@client.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    if not before.guild:
        return
    logchannel = client.get_channel(config.get_channel(before.guild.id, 'log-chat'))

    if not logchannel or before.channel == logchannel:
        return
    b = format_message_with_attachments(before)
    a = format_message_with_attachments(after)
    await logchannel.send(f"EDIT {before.channel}/{before.author}\nFROM: {b}\nTO: {a}")

@client.event
async def on_message_delete(message: discord.Message) -> None:
    if not message.guild:
        return
    logchannel = client.get_channel(config.get_channel(message.guild.id, 'log-chat'))

    if not logchannel or message.channel == logchannel:
        return
    await logchannel.send(f"DELETE {message.channel}/{message.author}: {format_message_with_attachments(message)}")

@client.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent) -> None:
    if not payload.guild_id:
        return
    logchannel     = client.get_channel(config.get_channel(payload.guild_id, 'log-chat'))
    datalogchannel = client.get_channel(config.get_channel(payload.guild_id, 'datalog-chat'))

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
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent) -> None:
    if not payload.guild_id:
        return
    logchannel     = client.get_channel(config.get_channel(payload.guild_id, 'log-chat'))
    datalogchannel = client.get_channel(config.get_channel(payload.guild_id, 'datalog-chat'))

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

###################################################################################################
#                                           MAIN                                                  #
#                                                                                                 #
###################################################################################################

async def main() -> None:
    print("bot starting")
    await client.start(client.token)

if __name__ == "__main__":
    asyncio.run(main())