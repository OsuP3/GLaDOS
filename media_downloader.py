"""
media_downloader.py
====================
Drop this file next to glados_bot.py. It watches Discord messages for
YouTube / Twitter (X) / TikTok links, downloads them with yt-dlp, and
re-posts them as native attachments if they fit under your size cap.

Install:
    pip install yt-dlp

Usage in glados_bot.py:
    from media_downloader import handle_media_links

    # inside on_message, after your history/logging logic:
    await handle_media_links(message)

Config (optional, via environment variables):
    MAX_UPLOAD_MB           - size cap in MB for re-uploaded files (default 25)
    MEDIA_DL_MAX_LINKS      - max links processed per message (default 3)
    MEDIA_DL_COOKIES_FILE   - path to a cookies.txt for gated Twitter/TikTok
                              content (optional, unset by default)
"""

import asyncio
import glob
import os
import re
import tempfile

import discord
import yt_dlp

# ── Config ───────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_LINKS_PER_MESSAGE = int(os.getenv("MEDIA_DL_MAX_LINKS", "3"))
COOKIES_FILE = os.getenv("MEDIA_DL_COOKIES_FILE")  # None if not set

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
    outtmpl = os.path.join(dest_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": f"mp4[filesize<{MAX_UPLOAD_BYTES * 2}]/best[filesize<{MAX_UPLOAD_BYTES * 2}]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "max_filesize": MAX_UPLOAD_BYTES * 2,
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
    if not files:
        return None
    return max(files, key=os.path.getsize)


async def handle_media_links(message: discord.Message) -> None:
    """
    Scans a message for supported links and posts back downloaded media
    for any that fit under the size cap. Call this from on_message.
    """
    urls = URL_PATTERN.findall(message.content)
    if not urls:
        return

    loop = asyncio.get_running_loop()

    for url in urls[:MAX_LINKS_PER_MESSAGE]:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = await loop.run_in_executor(None, _download_media, url, tmpdir)
            if not path:
                continue

            size = os.path.getsize(path)
            if size > MAX_UPLOAD_BYTES:
                print(f"Skipping {url}: {size / 1_048_576:.1f}MB exceeds "
                      f"{MAX_UPLOAD_BYTES / 1_048_576:.0f}MB cap")
                continue

            try:
                async with message.channel.typing():
                    await message.channel.send(
                        file=discord.File(path),
                        reference=message,
                        mention_author=False,
                    )
            except discord.HTTPException as e:
                print(f"Upload failed for {url}: {e}")