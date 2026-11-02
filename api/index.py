import json
import logging
import os
import re
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler
import requests
import yt_dlp

# -------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("VercelBot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
URL_REGEX = re.compile(r"https?://(?:www\.)?\S+", re.IGNORECASE)

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
        return {"name": "X (Twitter)", "emoji": "🐦", "desc": "X / Twitter Media"}
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
# TELEGRAM API HELPERS
# -------------------------------------------------------------------
def send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> int:
    try:
        res = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10
        )
        data = res.json()
        if data.get("ok"):
            return data["result"]["message_id"]
    except Exception as e:
        logger.error(f"sendMessage error: {e}")
    return 0


def edit_telegram_message(chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown"):
    if not message_id:
        return
    try:
        requests.post(
            f"{TELEGRAM_API}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode},
            timeout=10
        )
    except Exception as e:
        logger.error(f"editMessageText error: {e}")


def delete_telegram_message(chat_id: int, message_id: int):
    if not message_id:
        return
    try:
        requests.post(
            f"{TELEGRAM_API}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=10
        )
    except Exception as e:
        logger.error(f"deleteMessage error: {e}")


# -------------------------------------------------------------------
# EXTRACTION & UPLOAD PIPELINE
# -------------------------------------------------------------------
def process_url_and_reply(chat_id: int, url: str, platform: dict, status_msg_id: int):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info and info["entries"]:
                info = info["entries"][0]

        title = info.get("title", f"{platform['name']} Video")
        duration = int(info.get("duration", 0)) if info.get("duration") else None
        caption = f"🎬 **{platform['emoji']} {platform['name']}**\n\n📌 {title[:80]}"

        # Attempt 1: Direct streaming URL if available
        direct_url = info.get("url")
        if not direct_url and "formats" in info:
            mp4_candidates = [
                f for f in info["formats"]
                if f.get("ext") == "mp4" and f.get("url") and f.get("vcodec") != "none"
            ]
            if mp4_candidates:
                direct_url = mp4_candidates[-1]["url"]

        if direct_url:
            logger.info("Attempting direct URL dispatch via Telegram Bot API...")
            send_res = requests.post(
                f"{TELEGRAM_API}/sendVideo",
                json={
                    "chat_id": chat_id,
                    "video": direct_url,
                    "caption": caption,
                    "parse_mode": "Markdown",
                    "supports_streaming": True,
                    "duration": duration
                },
                timeout=25
            )
            result = send_res.json()
            if result.get("ok"):
                delete_telegram_message(chat_id, status_msg_id)
                return

        # Attempt 2: Download stream chunk to /tmp and upload multipart
        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"📥 **Downloading {platform['emoji']} {platform['name']} stream...**"
        )

        tmp_dir = tempfile.gettempdir()
        tmp_file = os.path.join(tmp_dir, f"video_{uuid.uuid4().hex[:6]}.mp4")

        ydl_download_opts = {
            "outtmpl": tmp_file,
            "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "max_filesize": 48 * 1024 * 1024,
        }

        with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
            ydl.download([url])

        target_file = tmp_file
        if not os.path.exists(target_file):
            for candidate in os.listdir(tmp_dir):
                if candidate.startswith("video_") and candidate.endswith(".mp4"):
                    target_file = os.path.join(tmp_dir, candidate)
                    break

        if os.path.exists(target_file):
            edit_telegram_message(chat_id, status_msg_id, "🚀 **Uploading video to Telegram...**")
            with open(target_file, "rb") as vf:
                requests.post(
                    f"{TELEGRAM_API}/sendVideo",
                    data={
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "Markdown",
                        "supports_streaming": "true"
                    },
                    files={"video": (os.path.basename(target_file), vf, "video/mp4")},
                    timeout=50
                )
            try:
                os.remove(target_file)
            except Exception:
                pass
            delete_telegram_message(chat_id, status_msg_id)
            return

        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"❌ Could not download video from {platform['name']}. File might be private or geo-blocked."
        )

    except yt_dlp.utils.DownloadError as de:
        clean_err = str(de).split(";")[0].replace("ERROR:", "").strip()
        edit_telegram_message(chat_id, status_msg_id, f"❌ Extraction error: {clean_err[:120]}")
    except Exception as e:
        logger.error(f"Error handling video: {e}")
        edit_telegram_message(
            chat_id,
            status_msg_id,
            "❌ An unexpected error occurred while processing the video."
        )


# -------------------------------------------------------------------
# VERCEL SERVERLESS HTTP HANDLER
# -------------------------------------------------------------------
class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        if path in ("/ping", "/api/ping"):
            self._send_json(200, {
                "status": "pong",
                "message": "Bot is awake and running 24/7 on Vercel",
                "service": "Universal Media Downloader Bot",
                "bot": "@vidsmkdownloaderbot",
                "ping_url": "https://botdownloaderbymk.vercel.app/ping"
            })
            return

        if path in ("/health", "/api/health"):
            self._send_json(200, {"status": "healthy"})
            return

        if path in ("/setup", "/api/setup", "/set_webhook"):
            webhook_url = "https://botdownloaderbymk.vercel.app/api/webhook"
            res = requests.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url}, timeout=10)
            self._send_json(200, {
                "action": "setWebhook",
                "target_url": webhook_url,
                "telegram_response": res.json()
            })
            return

        # Default info endpoint
        self._send_json(200, {
            "status": "online",
            "service": "Downloader Mk - Telegram Universal Media Bot",
            "bot_username": "@vidsmkdownloaderbot",
            "endpoints": {
                "ping": "https://botdownloaderbymk.vercel.app/ping",
                "health": "https://botdownloaderbymk.vercel.app/health",
                "webhook": "https://botdownloaderbymk.vercel.app/api/webhook",
                "setup_webhook": "https://botdownloaderbymk.vercel.app/setup"
            }
        })

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            update = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse webhook JSON: {e}")
            self._send_json(400, {"error": "Invalid JSON"})
            return

        message = update.get("message") or update.get("channel_post")
        if not message:
            self._send_json(200, {"status": "ignored_no_message"})
            return

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if not chat_id or not text:
            self._send_json(200, {"status": "ignored_no_text"})
            return

        # 1. Handle /start command
        if text.strip().startswith("/start"):
            send_telegram_message(
                chat_id,
                "⚡ **Universal Video Downloader**\n\n"
                "Send or paste any public link from:\n"
                "• 📸 **Instagram** (Reels, Posts, Stories)\n"
                "• 🎵 **TikTok** (No watermark)\n"
                "• 🔴 **YouTube** (Shorts & Standard Videos)\n"
                "• 🐦 **X / Twitter** Media\n"
                "• 👽 **Reddit** Clips\n"
                "• 📘 **Facebook** Videos\n"
                "• 🟣 **Twitch, Pinterest, Vimeo**, etc.\n\n"
                "I will automatically detect the platform and deliver the video directly to you!"
            )
            self._send_json(200, {"status": "start_command_handled"})
            return

        # 2. Check for URL
        match = URL_REGEX.search(text)
        if not match:
            send_telegram_message(
                chat_id,
                "ℹ️ Please send a valid video link (e.g., from Instagram, TikTok, YouTube, X, Reddit)."
            )
            self._send_json(200, {"status": "no_url_found"})
            return

        url = match.group(0)
        platform = detect_platform(url)

        # Notify user of detected platform
        status_msg_id = send_telegram_message(
            chat_id,
            f"🔎 **Platform Detected:** {platform['emoji']} *{platform['desc']}*\n"
            f"⏳ *Extracting media stream...*"
        )

        # Process download & delivery
        process_url_and_reply(chat_id, url, platform, status_msg_id)

        self._send_json(200, {"status": "processed", "platform": platform["name"]})
