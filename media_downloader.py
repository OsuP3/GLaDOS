"""
media_downloader.py
====================
Drop this file next to glados_bot.py. It watches Discord messages for
YouTube / Twitter (X) / TikTok links, downloads them with yt-dlp, and
posts them back into the channel:

    - If the file fits under MAX_UPLOAD_MB, it's sent as a native Discord
      attachment (best experience -- built-in player, download button).
    - If it's bigger, it's uploaded to Catbox.moe (free, no API key) and the
      raw link is posted instead. Discord auto-embeds direct video links as
      an inline player regardless of size, since it's just fetching from an
      external URL rather than accepting an upload -- so this sidesteps
      Discord's cap almost entirely (only bounded by Catbox's own ~200MB
      per-file limit).

Install:
    pip install yt-dlp requests

Usage in glados_bot.py:
    from media_downloader import handle_media_links

    # inside on_message, after your history/logging logic:
    await handle_media_links(message)

Config (optional, via environment variables):
    MAX_UPLOAD_MB           - size cap in MB for native Discord upload (default 25)
    MEDIA_DL_MAX_LINKS      - max links processed per message (default 3)
    MEDIA_DL_COOKIES_FILE   - path to a cookies.txt for gated Twitter/TikTok
                              content (optional, unset by default)
    MEDIA_DL_FALLBACK_HOST  - "catbox" (default) or "none" to disable the
                              external-host fallback and just skip oversized
                              files instead

Note on Catbox: it's a free, community-run anonymous file host. Uploaded
files are public (anyone with the link can view them) and persist
indefinitely. Fine for a casual/friends server; if you outgrow it, swap
_upload_to_catbox() for your own S3/Cloudflare R2 bucket -- the rest of
this file doesn't need to change.
"""

import asyncio
import glob
import os
import re
import tempfile

import discord
import requests
import yt_dlp

# ── Config ───────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_LINKS_PER_MESSAGE = int(os.getenv("MEDIA_DL_MAX_LINKS", "3"))
COOKIES_FILE = os.getenv("MEDIA_DL_COOKIES_FILE")  # None if not set
FALLBACK_HOST = os.getenv("MEDIA_DL_FALLBACK_HOST", "catbox").lower()

CATBOX_API_URL = "https://catbox.moe/user/api.php"
# Catbox's own hard limit per file; nothing we can do about files bigger
# than this short of self-hosting.
CATBOX_MAX_BYTES = 200 * 1024 * 1024

URL_PATTERN = re.compile(
    r"""(https?://
        (?:www\.|vt\.|m\.)?
        (?:
            youtube\.com/(?:watch\?v=|shorts/)[\w\-]+ |
            youtu\.be/[\w\-]+ |
            twitter\.com/\w+/status/\d+ |
            x\.com/\w+/status/\d+ |
            tiktok\.com/@[\w.\-]+/(?:video|photo)/\d+ |
            tiktok\.com/t/[\w]+ |
            vt\.tiktok\.com/[\w]+
        )
        [^\s>]*
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _download_media(url: str, dest_dir: str) -> str | None:
    """
    Blocking call -- must be run in an executor, never awaited directly.
    Downloads the best quality reasonably close to the size cap and returns
    the path to the largest file produced.
    """
    # The real ceiling on what's worth downloading at all: if the fallback
    # host is enabled, that's the true backstop (Discord's cap no longer
    # matters since oversized files just get routed there instead). If the
    # fallback is disabled, there's no point downloading past the Discord
    # cap since the file could never be posted anyway.
    download_ceiling = CATBOX_MAX_BYTES if FALLBACK_HOST != "none" else MAX_UPLOAD_BYTES

    outtmpl = os.path.join(dest_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": f"mp4[filesize<{download_ceiling}]/best[filesize<{download_ceiling}]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "max_filesize": download_ceiling,
        # YouTube has been aggressively 403'ing certain player clients as
        # part of its anti-bot measures. Trying several in order gives
        # yt-dlp a much better shot at finding one that still works.
        # Keep yt-dlp itself updated (pip install -U yt-dlp) -- this list
        # is a workaround, not a substitute for staying current.
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb", "web_safari"],
            }
        },
    }
    if COOKIES_FILE:
        ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"yt-dlp download error for {url}: {e}")
        return None

    files = glob.glob(os.path.join(dest_dir, "*"))
    # yt-dlp leaves .part (and sometimes .ytdl) files behind when a
    # download is interrupted or aborted (e.g. it hit max_filesize
    # mid-stream). Those are incomplete and must never be treated as the
    # finished file -- filter them out before picking the "largest" one.
    finished_files = [
        f for f in files
        if not f.endswith(".part") and not f.endswith(".ytdl")
    ]
    if not finished_files:
        print(f"No completed file found for this download (only partial/temp "
              f"files present) -- likely hit max_filesize or was interrupted")
        return None
    return max(finished_files, key=os.path.getsize)


def _upload_to_catbox(path: str) -> str | None:
    """
    Blocking call -- must be run in an executor. Uploads a file to Catbox.moe
    and returns the resulting direct link, or None on failure.
    """
    try:
        with open(path, "rb") as f:
            resp = requests.post(
                CATBOX_API_URL,
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=120,
            )
        resp.raise_for_status()
        url = resp.text.strip()
        if url.startswith("http"):
            return url
        print(f"Catbox upload returned unexpected response: {url}")
        return None
    except Exception as e:
        print(f"Catbox upload error: {e}")
        return None


async def handle_media_links(message: discord.Message) -> None:
    """
    Scans a message for supported links and posts back downloaded media.
    Small files go up as native Discord attachments; large ones fall back
    to an external host link (so Discord still renders an inline player
    with no real size limit). Call this from on_message.
    """
    urls = URL_PATTERN.findall(message.content)
    if not urls:
        return

    loop = asyncio.get_running_loop()

    for url in urls[:MAX_LINKS_PER_MESSAGE]:
        if url[-1] == "^":
            url = url[:-1]
        else:
            continue
        with tempfile.TemporaryDirectory() as tmpdir:
            path = await loop.run_in_executor(None, _download_media, url, tmpdir)
            if not path:
                continue

            size = os.path.getsize(path)

            # Case 1: small enough for a native Discord upload (best UX).
            if size <= MAX_UPLOAD_BYTES:
                try:
                    async with message.channel.typing():
                        await message.channel.send(
                            file=discord.File(path),
                            reference=message,
                            mention_author=False,
                        )
                except discord.HTTPException as e:
                    print(f"Native upload failed for {url}: {e}")
                continue

            # Case 2: too big for Discord -- fall back to an external host
            # and post the link, which Discord will still embed as a
            # playable/downloadable video.
            if FALLBACK_HOST == "none":
                print(f"Skipping {url}: {size / 1_048_576:.1f}MB exceeds "
                      f"{MAX_UPLOAD_BYTES / 1_048_576:.0f}MB cap "
                      f"(fallback host disabled)")
                continue

            if size > CATBOX_MAX_BYTES:
                print(f"Skipping {url}: {size / 1_048_576:.1f}MB exceeds "
                      f"Catbox's {CATBOX_MAX_BYTES / 1_048_576:.0f}MB limit too")
                continue

            async with message.channel.typing():
                hosted_url = await loop.run_in_executor(None, _upload_to_catbox, path)
            if not hosted_url:
                print(f"Fallback upload failed for {url}, giving up on this link")
                continue

            try:
                await message.channel.send(
                    hosted_url,
                    reference=message,
                    mention_author=False,
                )
            except discord.HTTPException as e:
                print(f"Failed to post fallback link for {url}: {e}")