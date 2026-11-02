import json
import logging
import os
import plistlib
import re
import tempfile
import urllib.parse
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
USER_CHAT_ID = 2140565223

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
# IOS SHORTCUT BINARY BUILDER (.shortcut)
# -------------------------------------------------------------------
def generate_shortcut_bytes() -> bytes:
    shortcut_dict = {
        "WFWorkflowClientVersion": "2600.0.0",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": [
            "WFURLContentItem",
            "WFStringContentItem",
            "WFSafariWebPageContentItem"
        ],
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59781,
            "WFWorkflowIconStartColor": 4282601983
        },
        "WFWorkflowActions": [
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
                "WFWorkflowActionParameters": {
                    "WFURL": "https://botdownloaderbymk.vercel.app/api/share",
                    "WFHTTPMethod": "POST",
                    "WFHTTPBodyType": "JSON",
                    "WFJSONValues": {
                        "Value": {
                            "WFDictionaryFieldValueItems": [
                                {
                                    "WFItemType": 0,
                                    "WFKey": {
                                        "Value": {"string": "url", "attachmentsByRange": {}},
                                        "WFSerializationType": "WFTextTokenString"
                                    },
                                    "WFValue": {
                                        "Value": {
                                            "string": "\ufffc",
                                            "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}}
                                        },
                                        "WFSerializationType": "WFTextTokenString"
                                    }
                                },
                                {
                                    "WFItemType": 0,
                                    "WFKey": {
                                        "Value": {"string": "chat_id", "attachmentsByRange": {}},
                                        "WFSerializationType": "WFTextTokenString"
                                    },
                                    "WFValue": {
                                        "Value": {"string": str(USER_CHAT_ID), "attachmentsByRange": {}},
                                        "WFSerializationType": "WFTextTokenString"
                                    }
                                }
                            ]
                        },
                        "WFSerializationType": "WFDictionaryFieldValue"
                    }
                }
            },
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
                "WFWorkflowActionParameters": {
                    "WFNotificationActionTitle": "Downloader Mk ⚡",
                    "WFNotificationActionBody": "Video sent to your Telegram!"
                }
            }
        ]
    }
    return plistlib.dumps(shortcut_dict, fmt=plistlib.FMT_BINARY)


def render_shortcut_page() -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Downloader Mk — iOS Shortcut</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro", "Segoe UI", Roboto, sans-serif; }}
    body {{ background: #0b0f19; color: #f3f4f6; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px 16px; }}
    .card {{ background: #131b2e; border: 1px solid #1f2d47; border-radius: 24px; padding: 32px 24px; max-width: 480px; width: 100%; box-shadow: 0 20px 40px rgba(0,0,0,0.5); text-align: center; }}
    .icon {{ font-size: 54px; margin-bottom: 16px; display: inline-block; }}
    h1 {{ font-size: 24px; font-weight: 700; color: #fff; margin-bottom: 8px; }}
    p.subtitle {{ font-size: 14px; color: #94a3b8; margin-bottom: 24px; line-height: 1.5; }}
    .btn {{ display: block; width: 100%; background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; text-decoration: none; font-size: 17px; font-weight: 600; padding: 16px; border-radius: 16px; border: none; cursor: pointer; transition: transform 0.15s, opacity 0.15s; box-shadow: 0 8px 24px rgba(245, 158, 11, 0.35); margin-bottom: 16px; }}
    .btn:active {{ transform: scale(0.98); opacity: 0.9; }}
    .steps {{ background: #0f1626; border-radius: 16px; padding: 18px 16px; text-align: left; margin-top: 16px; border: 1px solid #1a253b; }}
    .step {{ display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px; font-size: 13.5px; color: #cbd5e1; line-height: 1.4; }}
    .step:last-child {{ margin-bottom: 0; }}
    .badge {{ background: #f59e0b; color: #000; font-weight: 700; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; flex-shrink: 0; }}
    code {{ background: #1e293b; padding: 2px 6px; border-radius: 6px; font-size: 12px; color: #38bdf8; font-family: ui-monospace, monospace; word-break: break-all; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">⚡</div>
    <h1>Downloader Mk Shortcut</h1>
    <p class="subtitle">Share any Instagram, TikTok, YouTube, or Facebook link directly from your iOS Share Sheet to download it instantly!</p>
    
    <a href="/downloader_mk.shortcut" class="btn">📲 Download iOS Shortcut File</a>
    
    <div class="steps">
      <div class="step">
        <span class="badge">1</span>
        <div>Tap <b>Download iOS Shortcut</b> above to open and save it in your <b>Shortcuts</b> app.</div>
      </div>
      <div class="step">
        <span class="badge">2</span>
        <div>Whenever you view a Reel or Video on Instagram, TikTok, or YouTube, tap <b>Share (⬆️)</b>.</div>
      </div>
      <div class="step">
        <span class="badge">3</span>
        <div>Select <b>Downloader Mk</b>. Your video will be delivered straight into your Telegram chat!</div>
      </div>
    </div>
  </div>
</body>
</html>"""


# -------------------------------------------------------------------
# TELEGRAM API HELPERS
# -------------------------------------------------------------------
def send_telegram_message(chat_id: int, text: str) -> int:
    try:
        res = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
        data = res.json()
        if not data.get("ok"):
            res = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10
            )
            data = res.json()
        if data.get("ok"):
            return data["result"]["message_id"]
    except Exception as e:
        logger.error(f"sendMessage error: {e}")
    return 0


def edit_telegram_message(chat_id: int, message_id: int, text: str):
    if not message_id:
        return
    try:
        res = requests.post(
            f"{TELEGRAM_API}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
        if not res.json().get("ok"):
            requests.post(
                f"{TELEGRAM_API}/editMessageText",
                json={"chat_id": chat_id, "message_id": message_id, "text": text},
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
    logger.info(f"Processing URL: {url} for {platform['name']} (chat_id: {chat_id})")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[ext=mp4][acodec!=none]/best[ext=mp4]/best",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Referer": url,
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info and info["entries"]:
                info = info["entries"][0]

        title = str(info.get("title", f"{platform['name']} Video")).strip()
        duration = int(info.get("duration", 0)) if info.get("duration") else None

        # Resolve direct video stream URL
        direct_url = info.get("url")
        if not direct_url and "formats" in info:
            for f in reversed(info["formats"]):
                if f.get("url") and f.get("ext") == "mp4":
                    direct_url = f["url"]
                    break

        if not direct_url:
            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"❌ Could not extract video stream from {platform['name']}. Media may be private or protected."
            )
            return

        # 2. Download direct stream into temporary file
        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"📥 **Downloading {platform['emoji']} {platform['name']} media...**"
        )

        tmp_file = os.path.join(tempfile.gettempdir(), f"vid_{uuid.uuid4().hex[:6]}.mp4")
        stream_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": url
        }

        download_resp = requests.get(direct_url, headers=stream_headers, stream=True, timeout=25)
        download_resp.raise_for_status()

        total_bytes = 0
        with open(tmp_file, "wb") as f:
            for chunk in download_resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > 48 * 1024 * 1024:
                        break

        if total_bytes > 48 * 1024 * 1024:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"⚠️ Video size ({total_bytes // (1024 * 1024)} MB) exceeds Telegram's 50 MB upload limit."
            )
            return

        if not os.path.exists(tmp_file) or total_bytes == 0:
            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"❌ Downloaded stream was empty or blocked by {platform['name']}."
            )
            return

        # 3. Upload video file to Telegram
        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"🚀 **Uploading {platform['name']} video to chat...**"
        )

        caption_text = f"🎬 {platform['emoji']} {platform['name']}\n\n📌 {title[:80]}"

        with open(tmp_file, "rb") as vf:
            upload_res = requests.post(
                f"{TELEGRAM_API}/sendVideo",
                data={
                    "chat_id": chat_id,
                    "caption": caption_text,
                    "supports_streaming": "true",
                    "duration": duration
                },
                files={"video": (os.path.basename(tmp_file), vf, "video/mp4")},
                timeout=50
            )

        try:
            os.remove(tmp_file)
        except Exception:
            pass

        upload_data = upload_res.json()
        logger.info(f"Telegram upload result: {upload_data.get('ok')} - desc: {upload_data.get('description')}")

        if upload_data.get("ok"):
            delete_telegram_message(chat_id, status_msg_id)
        else:
            err_desc = upload_data.get("description", "Unknown Telegram error")
            edit_telegram_message(chat_id, status_msg_id, f"❌ Telegram upload error: {err_desc}")

    except yt_dlp.utils.DownloadError as de:
        clean_err = str(de).split(";")[0].replace("ERROR:", "").strip()
        edit_telegram_message(chat_id, status_msg_id, f"❌ Extraction error: {clean_err[:120]}")
    except Exception as e:
        logger.error(f"Error handling video: {e}", exc_info=True)
        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"❌ Error downloading video: {str(e)[:100]}"
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
        parsed_url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_url.query)
        action = query.get("action", [""])[0].lower()
        full_path = self.path.lower()

        # Direct shortcut file download
        if action == "shortcut" or "downloader_mk.shortcut" in full_path or full_path.endswith(".shortcut"):
            shortcut_data = generate_shortcut_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-apple-shortcut")
            self.send_header("Content-Disposition", 'attachment; filename="Downloader_Mk.shortcut"')
            self.send_header("Content-Length", str(len(shortcut_data)))
            self.end_headers()
            self.wfile.write(shortcut_data)
            return

        # Interactive Shortcut Webpage
        if action == "page" or "shortcut" in full_path or "ios" in full_path:
            html = render_shortcut_page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        # Direct iOS Shortcut Share Trigger (GET method: /api/share?url=...&chat_id=...)
        if action == "share" or "share" in full_path:
            target_url = query.get("url", [""])[0]
            chat_id = int(query.get("chat_id", [str(USER_CHAT_ID)])[0])

            if not target_url:
                self._send_json(400, {"error": "Missing 'url' query parameter"})
                return

            platform = detect_platform(target_url)
            status_id = send_telegram_message(
                chat_id,
                f"📲 **Received via iOS Shortcut**\n\n🔎 **Platform:** {platform['emoji']} *{platform['desc']}*\n⏳ *Extracting media stream...*"
            )
            process_url_and_reply(chat_id, target_url, platform, status_id)
            self._send_json(200, {
                "status": "success",
                "message": "Video sent to your Telegram!",
                "platform": platform["name"]
            })
            return

        if action == "ping" or "ping" in full_path:
            self._send_json(200, {
                "status": "pong",
                "message": "Bot is awake and running 24/7 on Vercel",
                "service": "Universal Media Downloader Bot",
                "bot": "@vidsmkdownloaderbot",
                "ping_url": "https://botdownloaderbymk.vercel.app/ping"
            })
            return

        if action == "health" or "health" in full_path:
            self._send_json(200, {"status": "healthy"})
            return

        if action == "setup" or "setup" in full_path:
            webhook_url = "https://botdownloaderbymk.vercel.app/api/webhook"
            res = requests.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url}, timeout=10)
            self._send_json(200, {
                "action": "setWebhook",
                "target_url": webhook_url,
                "telegram_response": res.json()
            })
            return

        self._send_json(200, {
            "status": "online",
            "service": "Downloader Mk - Telegram Universal Media Bot",
            "bot_username": "@vidsmkdownloaderbot",
            "endpoints": {
                "ios_shortcut_page": "https://botdownloaderbymk.vercel.app/shortcut",
                "ios_shortcut_file": "https://botdownloaderbymk.vercel.app/downloader_mk.shortcut",
                "share_api": "https://botdownloaderbymk.vercel.app/api/share",
                "ping": "https://botdownloaderbymk.vercel.app/ping"
            }
        })

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse POST JSON: {e}")
            self._send_json(400, {"error": "Invalid JSON"})
            return

        raw_path = self.headers.get("x-matched-path") or self.path
        path = raw_path.split("?")[0].rstrip("/").lower()

        # Handle direct share from iOS Shortcut (POST method)
        if "share" in path or ("url" in payload and "message" not in payload):
            target_url = payload.get("url", "")
            chat_id = int(payload.get("chat_id", USER_CHAT_ID))

            if not target_url:
                self._send_json(400, {"error": "Missing 'url' field"})
                return

            platform = detect_platform(target_url)
            status_id = send_telegram_message(
                chat_id,
                f"📲 **Received via iOS Shortcut**\n\n🔎 **Platform:** {platform['emoji']} *{platform['desc']}*\n⏳ *Extracting media stream...*"
            )
            process_url_and_reply(chat_id, target_url, platform, status_id)
            self._send_json(200, {
                "status": "success",
                "message": "Video sent to your Telegram!",
                "platform": platform["name"]
            })
            return

        # Otherwise handle standard Telegram Webhook update
        update = payload
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
                "📲 **iOS Shortcut:** Install the shortcut at https://botdownloaderbymk.vercel.app/shortcut to share links directly from any app without copying & pasting!"
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
