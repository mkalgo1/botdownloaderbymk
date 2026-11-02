import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Dict, Optional, Tuple

import aiohttp
from aiohttp import web
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message

# -------------------------------------------------------------------
# LOGGING SETUP
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MediaDownloaderBot")

# -------------------------------------------------------------------
# ENVIRONMENT & THRESHOLDS
# -------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s")
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN environment variable is missing! Halting execution.")
    sys.exit(1)

MAX_TELEGRAM_BYTES = 48 * 1024 * 1024       # 48 MB safety margin for 50 MB Telegram API limit
TARGET_COMPRESSED_BYTES = 44 * 1024 * 1024  # 44 MB target for large video compression
MAX_VIDEO_DURATION_SECONDS = 3600           # 60 minutes limit
MAX_CONCURRENT_TASKS = 2                    # Prevents memory and CPU oversubscription
PORT = int(os.getenv("PORT", "8080"))

URL_REGEX = re.compile(r"https?://(?:www\.)?\S+", re.IGNORECASE)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


# -------------------------------------------------------------------
# PLATFORM DETECTOR
# -------------------------------------------------------------------
def detect_platform(url: str) -> dict:
    url_l = url.lower()
    if "instagram.com" in url_l:
        return {"name": "Instagram", "emoji": "📸", "desc": "Instagram Reel / Post"}
    elif "tiktok.com" in url_l:
        return {"name": "TikTok", "emoji": "🎵", "desc": "TikTok Video"}
    elif "youtube.com" in url_l or "youtu.be" in url_l:
        return {"name": "YouTube", "emoji": "🔴", "desc": "YouTube Video / Shorts"}
    elif "twitter.com" in url_l or "x.com" in url_l:
        return {"name": "X (Twitter)", "emoji": "🐦", "desc": "X / Twitter Video"}
    elif "reddit.com" in url_l or "redd.it" in url_l:
        return {"name": "Reddit", "emoji": "👽", "desc": "Reddit Video"}
    elif "facebook.com" in url_l or "fb.watch" in url_l:
        return {"name": "Facebook", "emoji": "📘", "desc": "Facebook Video"}
    elif "twitch.tv" in url_l:
        return {"name": "Twitch", "emoji": "🟣", "desc": "Twitch Clip"}
    elif "pinterest.com" in url_l or "pin.it" in url_l:
        return {"name": "Pinterest", "emoji": "📌", "desc": "Pinterest Video"}
    elif "vimeo.com" in url_l:
        return {"name": "Vimeo", "emoji": "🎬", "desc": "Vimeo Video"}
    elif "dailymotion.com" in url_l or "dai.ly" in url_l:
        return {"name": "Dailymotion", "emoji": "📹", "desc": "Dailymotion Video"}
    else:
        return {"name": "Web", "emoji": "🌐", "desc": "Universal Web Video"}


# -------------------------------------------------------------------
# KEEP-ALIVE HTTP SERVER (PREVENTS BOT SLEEP ON RENDER/KOYEB/ETC)
# -------------------------------------------------------------------
async def ping_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "pong",
        "message": "Bot is awake and running 24/7",
        "service": "Universal Media Downloader Bot",
        "bot": "@vidsmkdownloaderbot",
        "ping_url": "https://botdownloaderbymk.vercel.app/ping"
    })

async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "healthy",
        "active_downloads": MAX_CONCURRENT_TASKS - DOWNLOAD_SEMAPHORE._value
    })

async def root_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "alive",
        "service": "Universal Media Downloader Bot",
        "endpoints": {
            "ping": "/ping",
            "health": "/health"
        }
    })

def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", root_handler)
    app.router.add_get("/ping", ping_handler)
    app.router.add_get("/health", health_handler)
    return app

async def start_web_server() -> web.AppRunner:
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Keep-alive HTTP server listening on http://0.0.0.0:{PORT}")
    return runner

async def self_ping_worker():
    """Optional auto-ping background loop if PING_URL or RENDER_EXTERNAL_URL is set."""
    target_url = os.getenv("PING_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if not target_url:
        target_url = "https://botdownloaderbymk.vercel.app/ping"

    if not target_url.endswith("/ping"):
        target_url = target_url.rstrip("/") + "/ping"

    logger.info(f"Self-ping worker initialized for target: {target_url}")
    await asyncio.sleep(60)  # Wait 1 min before starting ping cycle
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(target_url, timeout=15) as resp:
                    logger.info(f"Keep-alive self-ping sent -> Status: {resp.status}")
            except Exception as e:
                logger.warning(f"Self-ping failed (non-critical): {e}")
            await asyncio.sleep(10 * 60)  # Ping every 10 minutes


# -------------------------------------------------------------------
# FFPROBE & FFMPEG ENGINE
# -------------------------------------------------------------------
def get_media_duration(file_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        file_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        meta = json.loads(res.stdout)
        return float(meta["format"]["duration"])
    except Exception as e:
        logger.error(f"Duration inspection error: {e}")
        return 0.0


def run_adaptive_compression(input_path: str, output_path: str, duration: float) -> bool:
    if duration <= 0:
        return False

    target_bits = TARGET_COMPRESSED_BYTES * 8
    audio_kbit = 96
    total_audio_bits = audio_kbit * 1000 * duration
    usable_video_bits = target_bits - total_audio_bits

    if usable_video_bits <= 0:
        logger.warning("Media duration exceeds bandwidth limit for 50 MB cap.")
        return False

    calculated_video_kbit = int((usable_video_bits / duration) / 1000)
    video_kbit = max(180, min(calculated_video_kbit, 2600))

    scale_expr = "scale='min(1280,iw)':-2"
    if video_kbit < 600:
        scale_expr = "scale='min(854,iw)':-2"

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264",
        "-b:v", f"{video_kbit}k",
        "-maxrate", f"{int(video_kbit * 1.35)}k",
        "-bufsize", f"{int(video_kbit * 2.2)}k",
        "-preset", "veryfast",
        "-vf", scale_expr,
        "-c:a", "aac",
        "-b:a", f"{audio_kbit}k",
        "-movflags", "+faststart",
        output_path
    ]

    try:
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) <= MAX_TELEGRAM_BYTES
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e.stderr.decode('utf-8', errors='ignore')}")
        return False


# -------------------------------------------------------------------
# SYNC DOWNLOAD & EXTRACTION PIPELINE
# -------------------------------------------------------------------
def download_and_process_sync(url: str, working_dir: str) -> Tuple[Optional[str], Dict]:
    out_template = os.path.join(working_dir, "raw_stream.%(ext)s")

    ydl_opts = {
        "outtmpl": out_template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
        },
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info and info["entries"]:
            info = info["entries"][0]

    downloaded = [
        os.path.join(working_dir, f)
        for f in os.listdir(working_dir)
        if not f.endswith(".temp") and not f.endswith(".part") and os.path.isfile(os.path.join(working_dir, f))
    ]

    if not downloaded:
        return None, info

    mp4_files = [f for f in downloaded if f.lower().endswith(".mp4")]
    raw_path = mp4_files[0] if mp4_files else downloaded[0]
    raw_size = os.path.getsize(raw_path)

    if raw_size <= MAX_TELEGRAM_BYTES:
        return raw_path, info

    dur = float(info.get("duration") or get_media_duration(raw_path))
    if dur > MAX_VIDEO_DURATION_SECONDS:
        raise ValueError(f"Video duration ({int(dur // 60)}m) exceeds max allowed limit (60m).")

    comp_path = os.path.join(working_dir, f"compressed_{uuid.uuid4().hex[:6]}.mp4")
    ok = run_adaptive_compression(raw_path, comp_path, dur)

    if ok and os.path.exists(comp_path):
        return comp_path, info

    return raw_path, info


# -------------------------------------------------------------------
# ROUTERS & HANDLERS
# -------------------------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.reply(
        "⚡ **Universal Video Downloader**\n\n"
        "Send or paste any public video link from:\n"
        "• 📸 **Instagram** (Reels, Posts, Stories)\n"
        "• 🎵 **TikTok** (No watermark)\n"
        "• 🔴 **YouTube** (Shorts & Standard Videos)\n"
        "• 🐦 **X / Twitter** Media\n"
        "• 👽 **Reddit** Clips\n"
        "• 📘 **Facebook** Videos\n"
        "• 🟣 **Twitch, Pinterest, Vimeo**, etc.\n\n"
        "I will detect the platform automatically and optimize the video for instant playback!"
    )


@dp.message(F.text)
async def process_link(msg: Message):
    match = URL_REGEX.search(msg.text)
    if not match:
        return

    url = match.group(0)
    platform = detect_platform(url)

    status_msg = await msg.reply(
        f"🔎 **Platform Detected:** {platform['emoji']} *{platform['desc']}*\n"
        f"⏳ Analyzing media stream..."
    )

    async with DOWNLOAD_SEMAPHORE:
        temp_dir = tempfile.mkdtemp(prefix="worker_media_")

        try:
            await status_msg.edit_text(f"📥 Downloading {platform['emoji']} {platform['name']} stream & checking size...")
            final_path, info = await asyncio.to_thread(download_and_process_sync, url, temp_dir)

            if not final_path or not os.path.exists(final_path):
                await status_msg.edit_text(f"❌ Could not download video from {platform['name']}. The link may be private or invalid.")
                return

            size = os.path.getsize(final_path)
            if size > (50 * 1024 * 1024):
                await status_msg.edit_text(
                    f"⚠️ Video size ({size // (1024 * 1024)} MB) exceeds Telegram's 50 MB upload limit."
                )
                return

            await status_msg.edit_text(f"🚀 Uploading {platform['name']} media to Telegram...")

            title = info.get("title", f"{platform['name']} Video")
            duration = int(info.get("duration", 0)) if info.get("duration") else None
            width = info.get("width")
            height = info.get("height")

            payload = FSInputFile(final_path, filename=f"video_{uuid.uuid4().hex[:6]}.mp4")

            await msg.reply_video(
                video=payload,
                caption=f"🎬 **{platform['emoji']} {platform['name']}**\n\n📌 {title[:80]}",
                duration=duration,
                width=width,
                height=height,
                supports_streaming=True
            )

            await status_msg.delete()

        except yt_dlp.utils.DownloadError as de:
            clean_err = str(de).split(";")[0].replace("ERROR:", "").strip()
            await status_msg.edit_text(f"❌ Extraction error: {clean_err}")
        except ValueError as ve:
            await status_msg.edit_text(f"⚠️ {str(ve)}")
        except Exception as e:
            logger.error(f"Handler processing error: {e}")
            await status_msg.edit_text("❌ An unexpected error occurred while processing the video.")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# -------------------------------------------------------------------
# APPLICATION ENTRYPOINT
# -------------------------------------------------------------------
async def main():
    logger.info("Initializing bot worker and ping server...")
    web_runner = await start_web_server()
    asyncio.create_task(self_ping_worker())
    
    logger.info("Starting Telegram long polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await web_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
