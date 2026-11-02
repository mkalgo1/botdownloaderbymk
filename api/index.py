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
    elif "snapchat.com" in url_l:
        return {"name": "Snapchat", "emoji": "👻", "desc": "Snapchat Spotlight / Story"}
    else:
        return {"name": "Web", "emoji": "🌐", "desc": "Universal Web Video"}


# -------------------------------------------------------------------
# SPECIALIZED FAST EXTRACTORS (TikTok & Snapchat)
# -------------------------------------------------------------------
def extract_snapchat_direct(url: str):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        # Expand shortened links (t.snapchat.com/...)
        if "t.snapchat.com" in url:
            try:
                r_exp = requests.get(url, allow_redirects=True, headers=headers, timeout=8)
                url = r_exp.url
            except Exception:
                pass

        resp = requests.get(url, headers=headers, timeout=12)
        html = resp.text

        # 1. Check for Story / Public Profile (__NEXT_DATA__) -> Completely Watermark-Free!
        m_next = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if m_next:
            try:
                data = json.loads(m_next.group(1))
                page_props = data.get("props", {}).get("pageProps", {})

                # Single story
                story = page_props.get("story")
                if story and story.get("snapList"):
                    for snap in story["snapList"]:
                        media_u = snap.get("snapUrls", {}).get("mediaUrl")
                        if media_u:
                            return media_u, "Snapchat Story", int(snap.get("duration", 0))

                # Curated highlights
                highlights = page_props.get("curatedHighlights", [])
                for h in highlights:
                    for snap in h.get("snapList", []):
                        media_u = snap.get("snapUrls", {}).get("mediaUrl")
                        if media_u and snap.get("snapMediaType") != 0:
                            return media_u, h.get("title", "Snapchat Story"), int(snap.get("duration", 0))
            except Exception as e:
                logger.warning(f"Next data parsing error: {e}")

        # 2. Check for exact video ID match in Spotlight
        id_m = re.search(r'spotlight/([A-Za-z0-9_-]+)', url)
        target_id = id_m.group(1) if id_m else None
        if target_id and target_id in html:
            pos = html.find(target_id)
            sub = html[max(0, pos - 500):min(len(html), pos + 2500)]
            m_v = re.findall(r'https://(?:bolt-gcdn|cf-st)\.sc-cdn\.net/[^\s"\'<>\\]+\.27\.[^\s"\'<>\\]+', sub)
            if m_v:
                clean_u = m_v[0].replace('\\u0026', '&').replace('\\"', '').replace('\\', '')
                title_m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                title = title_m.group(1).split(" | ")[0].strip() if title_m else "Snapchat Spotlight"
                return clean_u, title, 0

        # 3. Fallback: all matching video URLs
        m_videos = re.findall(r'https://(?:bolt-gcdn|cf-st)\.sc-cdn\.net/[^\s"\'<>]+\.27\.[^\s"\'<>]+', html)
        if not m_videos:
            m_videos = re.findall(r'videoUrl[^:]*:[^"]*"([^"]+)"', html)

        if m_videos:
            clean_u = m_videos[0].replace('\\u0026', '&').replace('\\"', '').replace('\\', '')
            title_m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            title = title_m.group(1).split(" | ")[0].strip() if title_m else "Snapchat Video"
            return clean_u, title, 0
    except Exception as e:
        logger.warning(f"Snapchat extraction error: {e}")
    return None, None, None


def extract_tiktok_direct(url: str):
    try:
        api_url = f"https://tikwm.com/api/?url={urllib.parse.quote(url, safe=':/?=&')}"
        req = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=10)
        if req.status_code == 200:
            data = req.json()
            if data.get("code") == 0 and data.get("data"):
                d = data["data"]
                play_url = d.get("play") or d.get("wmplay")
                hd_url = d.get("hdplay")
                title = d.get("title") or "TikTok Video"
                duration = d.get("duration", 0)
                return play_url, hd_url, title, duration
    except Exception as e:
        logger.warning(f"TikWM extraction failed: {e}")
    return None, None, None, None


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
    .icon {{ font-size: 54px; margin-bottom: 14px; display: inline-block; }}
    h1 {{ font-size: 24px; font-weight: 700; color: #fff; margin-bottom: 8px; }}
    p.subtitle {{ font-size: 14px; color: #94a3b8; margin-bottom: 20px; line-height: 1.5; }}
    .copy-box {{ background: #0b1120; border: 1px dashed #3b82f6; border-radius: 14px; padding: 14px; margin-bottom: 20px; text-align: left; }}
    .copy-label {{ font-size: 11px; text-transform: uppercase; color: #60a5fa; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 6px; }}
    .copy-url {{ font-family: ui-monospace, monospace; font-size: 12px; color: #38bdf8; word-break: break-all; margin-bottom: 10px; display: block; }}
    .btn {{ display: block; width: 100%; background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #fff; text-decoration: none; font-size: 16px; font-weight: 600; padding: 14px; border-radius: 14px; border: none; cursor: pointer; transition: transform 0.15s, opacity 0.15s; box-shadow: 0 8px 20px rgba(37, 99, 235, 0.35); }}
    .btn:active {{ transform: scale(0.98); opacity: 0.9; }}
    .steps {{ background: #0f1626; border-radius: 16px; padding: 18px 16px; text-align: left; margin-top: 20px; border: 1px solid #1a253b; }}
    .step {{ display: flex; align-items: flex-start; gap: 12px; margin-bottom: 14px; font-size: 13.5px; color: #cbd5e1; line-height: 1.45; }}
    .step:last-child {{ margin-bottom: 0; }}
    .badge {{ background: #3b82f6; color: #fff; font-weight: 700; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; flex-shrink: 0; }}
    code {{ background: #1e293b; padding: 2px 6px; border-radius: 6px; font-size: 12px; color: #38bdf8; font-family: ui-monospace, monospace; word-break: break-all; }}
    .toast {{ display: none; margin-top: 8px; font-size: 12px; color: #4ade80; font-weight: 600; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">⚡</div>
    <h1>Downloader Mk Shortcut</h1>
    <p class="subtitle">iOS requires shortcuts to be added inside the Shortcuts app. Here is your 1-click webhook link ready to paste!</p>

    <div class="copy-box">
      <div class="copy-label">Your Bot Webhook URL</div>
      <span class="copy-url" id="webhookUrl">https://botdownloaderbymk.vercel.app/api/share?url=</span>
      <button class="btn" onclick="copyUrl()">📋 Copy URL for Shortcut</button>
      <div class="toast" id="toast">✅ Copied to clipboard!</div>
    </div>
    
    <div class="steps">
      <div class="step">
        <span class="badge">1</span>
        <div>In Apple <b>Shortcuts</b>, tap <b><code>Get Contents of URL 1</code></b> (or tap <b>+</b> to create new).</div>
      </div>
      <div class="step">
        <span class="badge">2</span>
        <div>Tap the <b>( ⓘ )</b> icon at bottom &rarr; turn <b>ON &quot;Show in Share Sheet&quot;</b>.</div>
      </div>
      <div class="step">
        <span class="badge">3</span>
        <div>In the URL box, paste the copied link, and tap after <code>?url=</code> to add <b>Shortcut Input</b>. Tap Done!</div>
      </div>
    </div>
  </div>

  <script>
    function copyUrl() {{
      const text = document.getElementById('webhookUrl').innerText;
      navigator.clipboard.writeText(text).then(() => {{
        const t = document.getElementById('toast');
        t.style.display = 'block';
        setTimeout(() => {{ t.style.display = 'none'; }}, 2500);
      }});
    }}
  </script>
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

    direct_url = None
    title = f"{platform['name']} Video"
    duration = None
    stream_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        # 1. Specialized fast extractors for TikTok & Snapchat
        if platform.get("name") == "TikTok":
            tk_play, tk_hd, tk_title, tk_dur = extract_tiktok_direct(url)
            if tk_play:
                direct_url = tk_hd or tk_play
                if tk_title:
                    title = tk_title
                if tk_dur:
                    duration = int(tk_dur)
                logger.info(f"TikWM extraction succeeded for TikTok: {direct_url[:80]}")
        elif platform.get("name") == "Snapchat":
            snap_u, snap_t, snap_d = extract_snapchat_direct(url)
            if snap_u:
                direct_url = snap_u
                if snap_t:
                    title = snap_t
                logger.info(f"Snapchat direct extraction succeeded: {direct_url[:80]}")

        # 2. Universal yt-dlp extractor fallback
        if not direct_url:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "format": "best[ext=mp4][acodec!=none]/best[ext=mp4]/best",
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-us,en;q=0.5",
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if "entries" in info and info["entries"]:
                    info = info["entries"][0]

            if info.get("title"):
                title = str(info["title"]).strip()
            if info.get("duration"):
                duration = int(info["duration"])

            chosen_format = None
            if "formats" in info:
                for f in reversed(info["formats"]):
                    if f.get("url") and f.get("ext") == "mp4" and f.get("vcodec") != "none" and f.get("acodec") != "none":
                        chosen_format = f
                        direct_url = f["url"]
                        break
                if not direct_url:
                    for f in reversed(info["formats"]):
                        if f.get("url") and f.get("ext") == "mp4":
                            chosen_format = f
                            direct_url = f["url"]
                            break

            if not direct_url:
                direct_url = info.get("url")

            if chosen_format and chosen_format.get("http_headers"):
                stream_headers.update(chosen_format["http_headers"])
            elif info.get("http_headers"):
                stream_headers.update(info["http_headers"])
            elif "instagram.com" in url.lower():
                stream_headers["Referer"] = "https://www.instagram.com/"
            elif "tiktok.com" in url.lower():
                stream_headers["Referer"] = "https://www.tiktok.com/"

        if not direct_url:
            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"❌ Could not extract video stream from {platform['name']}. Media may be private or protected."
            )
            return

        # 3. Download direct stream into temporary file
        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"📥 **Downloading {platform['emoji']} {platform['name']} media...**"
        )

        tmp_file = os.path.join(tempfile.gettempdir(), f"vid_{uuid.uuid4().hex[:6]}.mp4")
        download_resp = requests.get(direct_url, headers=stream_headers, stream=True, timeout=30)
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

        # 4. Upload video file to Telegram
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
        try:
            self._handle_get()
        except Exception as e:
            logger.error(f"Unhandled GET exception: {e}", exc_info=True)
            self._send_json(500, {"error": "Server internal error", "detail": str(e)})

    def _handle_get(self):
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

        # Direct Video Stream for iOS Shortcut (Saves straight to iPhone Camera Roll without Telegram)
        if action == "stream" or "stream" in full_path or action == "download" or "download" in full_path:
            raw_url = query.get("url", [""])[0]
            quality_raw = query.get("quality", ["best"])[0].lower()
            m_q = re.search(r"\d+", quality_raw)
            q_height = int(m_q.group(0)) if m_q else None

            m = URL_REGEX.search(raw_url)
            target_url = m.group(0) if m else raw_url.strip()

            if not target_url:
                self._send_json(400, {"error": "Missing 'url' query parameter"})
                return

            platform = detect_platform(target_url)
            direct_url = None
            stream_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }

            if platform.get("name") == "TikTok":
                tk_play, tk_hd, _, _ = extract_tiktok_direct(target_url)
                if q_height and q_height >= 1080 and tk_hd:
                    direct_url = tk_hd
                elif tk_play:
                    direct_url = tk_play
            elif platform.get("name") == "Snapchat":
                snap_u, _, _ = extract_snapchat_direct(target_url)
                if snap_u:
                    direct_url = snap_u

            if not direct_url:
                try:
                    fmt_str = (
                        f"best[height<={q_height}][ext=mp4][acodec!=none]/best[height<={q_height}][ext=mp4]/best[height<={q_height}]/best"
                        if q_height
                        else "best[ext=mp4][acodec!=none]/best[ext=mp4]/best"
                    )
                    ydl_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "noplaylist": True,
                        "format": fmt_str,
                        "http_headers": {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        }
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(target_url, download=False)
                        if "entries" in info and info["entries"]:
                            info = info["entries"][0]

                    chosen_format = None
                    if "formats" in info:
                        if q_height:
                            for f in reversed(info["formats"]):
                                if f.get("url") and f.get("ext") == "mp4" and f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("height") and f.get("height") <= q_height:
                                    chosen_format = f
                                    direct_url = f["url"]
                                    break
                        if not direct_url:
                            for f in reversed(info["formats"]):
                                if f.get("url") and f.get("ext") == "mp4" and f.get("vcodec") != "none" and f.get("acodec") != "none":
                                    chosen_format = f
                                    direct_url = f["url"]
                                    break
                        if not direct_url:
                            for f in reversed(info["formats"]):
                                if f.get("url") and f.get("ext") == "mp4":
                                    chosen_format = f
                                    direct_url = f["url"]
                                    break
                    if not direct_url:
                        direct_url = info.get("url")

                    if chosen_format and chosen_format.get("http_headers"):
                        stream_headers.update(chosen_format["http_headers"])
                    elif info.get("http_headers"):
                        stream_headers.update(info["http_headers"])
                    elif "instagram.com" in target_url.lower():
                        stream_headers["Referer"] = "https://www.instagram.com/"
                    elif "tiktok.com" in target_url.lower():
                        stream_headers["Referer"] = "https://www.tiktok.com/"
                except Exception as ydl_err:
                    logger.warning(f"yt-dlp extraction failed: {ydl_err}")

            if not direct_url:
                self._send_json(404, {"error": "Could not extract video stream from URL"})
                return

            # If client requested JSON format
            if query.get("format", [""])[0].lower() == "json":
                self._send_json(200, {
                    "status": "success",
                    "url": direct_url,
                    "platform": platform["name"]
                })
                return

            # Direct 302 Redirect to high-speed CDN URL
            # Completely avoids Vercel's 4.5MB serverless response payload limit and 10s lambda timeout.
            # Apple Shortcuts 'Get Contents of URL' follows 302 redirects automatically and saves directly to Photos!
            self.send_response(302)
            self.send_header("Location", direct_url)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            return

        # Direct iOS Shortcut Share Trigger (GET method: /api/share?url=...&chat_id=...)
        if action == "share" or "share" in full_path:
            raw_url = query.get("url", [""])[0]
            chat_id = int(query.get("chat_id", [str(USER_CHAT_ID)])[0])

            m = URL_REGEX.search(raw_url)
            target_url = m.group(0) if m else raw_url.strip()

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
        try:
            self._handle_post()
        except Exception as e:
            logger.error(f"Unhandled POST exception: {e}", exc_info=True)
            self._send_json(500, {"error": "Server internal error", "detail": str(e)})

    def _handle_post(self):
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
            raw_url = payload.get("url", "")
            chat_id = int(payload.get("chat_id", USER_CHAT_ID))

            m = URL_REGEX.search(raw_url)
            target_url = m.group(0) if m else raw_url.strip()

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
