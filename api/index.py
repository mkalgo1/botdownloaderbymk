import json
import logging
import os
import plistlib
import re
import struct
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
        return {"name": "Pinterest", "emoji": "📌", "desc": "Pinterest Media / Pin"}
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


def extract_mp4_dimensions(file_path: str):
    """
    Extracts the exact native visual width and height of an MP4 file
    by reading track header (tkhd) boxes inside the moov atom.
    Works for all platforms (TikTok, Instagram, Snapchat, YouTube, etc.)
    in under 2 milliseconds without FFmpeg or OpenCV.
    """
    width, height = None, None
    try:
        with open(file_path, "rb") as f:
            data = f.read(4 * 1024 * 1024)
            offset = 0
            while True:
                pos = data.find(b"tkhd", offset)
                if pos == -1:
                    break
                if pos >= 4:
                    box_size = struct.unpack(">I", data[pos - 4:pos])[0]
                    if 84 <= box_size <= 256 and (pos - 4 + box_size) <= len(data):
                        w_raw, h_raw = struct.unpack(">II", data[pos - 4 + box_size - 8 : pos - 4 + box_size])
                        w = w_raw >> 16
                        h = h_raw >> 16
                        if w > 0 and h > 0:
                            width, height = w, h
                            break
                offset = pos + 4

            if not width:
                file_size = os.path.getsize(file_path)
                if file_size > 4 * 1024 * 1024:
                    f.seek(max(0, file_size - 2 * 1024 * 1024))
                    data_end = f.read()
                    offset = 0
                    while True:
                        pos = data_end.find(b"tkhd", offset)
                        if pos == -1:
                            break
                        if pos >= 4:
                            box_size = struct.unpack(">I", data_end[pos - 4:pos])[0]
                            if 84 <= box_size <= 256 and (pos - 4 + box_size) <= len(data_end):
                                w_raw, h_raw = struct.unpack(">II", data_end[pos - 4 + box_size - 8 : pos - 4 + box_size])
                                w = w_raw >> 16
                                h = h_raw >> 16
                                if w > 0 and h > 0:
                                    width, height = w, h
                                    break
                        offset = pos + 4
    except Exception as e:
        logger.warning(f"Could not parse MP4 dimensions: {e}")
    return width, height


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
                cover_url = d.get("cover") or d.get("origin_cover")
                return play_url, hd_url, title, duration, cover_url
    except Exception as e:
        logger.warning(f"TikWM extraction failed: {e}")
    return None, None, None, None, None


def extract_pinterest_direct(url: str):
    """
    Extracts direct Pinterest video (with audio/sound) or high-res photo.
    Resolves pin.it short links, retrieves direct expMp4 720p stream with full sound,
    or extracts full-resolution uncompressed photo.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "X-Pinterest-PWS-Handler": "www/[username].js"
    }

    # 1. Expand short links (pin.it/...) and get page HTML
    expanded_url = url
    page_html = ""
    try:
        r = requests.get(url, allow_redirects=True, headers=headers, timeout=8)
        expanded_url = r.url
        page_html = r.text
    except Exception as e:
        logger.warning(f"Error expanding pin.it: {e}")

    # 2. Check for direct expMp4 video with full sound directly in the web HTML
    if page_html:
        mp4_matches = re.findall(r'https://v1\.pinimg\.com/videos/iht/expMp4/[^"\'\s<>]+\.mp4', page_html)
        if mp4_matches:
            direct_mp4 = mp4_matches[0].replace('\\u0026', '&').replace('\\"', '').replace('\\', '')
            title_m = re.search(r'<title>(.*?)</title>', page_html, re.IGNORECASE)
            title = title_m.group(1).split(" | ")[0].split(" - ")[0].strip() if title_m else "Pinterest Video"
            logger.info(f"Extracted direct Pinterest MP4 with sound from HTML: {direct_mp4[:80]}")
            return direct_mp4, "video", title, 0, None, None, None

    # 3. Extract Pin ID
    pin_id_match = re.search(r"pin/(\d+)", expanded_url)
    if not pin_id_match:
        pin_id_match = re.search(r"pin/(\d+)", url)
    if not pin_id_match:
        return None, None, None, None, None, None, None

    pin_id = pin_id_match.group(1)

    # 4. Query Pinterest PinResource API
    params = {
        "source_url": f"/pin/{pin_id}/",
        "data": json.dumps({
            "options": {"field_set_key": "unauth_react_main_pin", "id": pin_id},
            "context": {}
        })
    }

    try:
        resp = requests.get("https://www.pinterest.com/resource/PinResource/get/", headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            pdata = resp.json().get("resource_response", {}).get("data", {})
            title = pdata.get("grid_title") or pdata.get("title") or pdata.get("closeup_unified_description") or "Pinterest Media"
            thumb = pdata.get("images", {}).get("orig", {}).get("url")

            # Check for direct video in 'videos'
            videos = pdata.get("videos")
            if videos and isinstance(videos, dict):
                v_list = videos.get("video_list", {})
                for q in ["V_720P", "V_EXP7", "V_480P", "V_MOBILE"]:
                    if q in v_list and v_list[q].get("url") and v_list[q]["url"].endswith(".mp4"):
                        return v_list[q]["url"], "video", title, v_list[q].get("duration", 0), v_list[q].get("width"), v_list[q].get("height"), thumb
                if "V_HLSV3_MOBILE" in v_list and v_list["V_HLSV3_MOBILE"].get("url"):
                    vhls = v_list["V_HLSV3_MOBILE"]
                    # Try deriving direct expMp4 with sound
                    cand_mp4 = vhls["url"].replace("/hls/", "/expMp4/").replace(".m3u8", "_720w.mp4")
                    try:
                        if requests.head(cand_mp4, timeout=3).status_code == 200:
                            return cand_mp4, "video", title, vhls.get("duration", 0), vhls.get("width"), vhls.get("height"), thumb
                    except Exception:
                        pass
                    return vhls["url"], "video", title, vhls.get("duration", 0), vhls.get("width"), vhls.get("height"), thumb

            # Check story_pin_data for video
            story = pdata.get("story_pin_data")
            if story and isinstance(story, dict):
                for page in story.get("pages", []):
                    for block in page.get("blocks", []):
                        if "video" in block:
                            v_list = block["video"].get("video_list", {})
                            for q in ["V_720P", "V_EXP7", "V_480P", "V_MOBILE"]:
                                if q in v_list and v_list[q].get("url") and v_list[q]["url"].endswith(".mp4"):
                                    return v_list[q]["url"], "video", title, v_list[q].get("duration", 0), v_list[q].get("width"), v_list[q].get("height"), thumb
                            if "V_HLSV3_MOBILE" in v_list and v_list["V_HLSV3_MOBILE"].get("url"):
                                vhls = v_list["V_HLSV3_MOBILE"]
                                cand_mp4 = vhls["url"].replace("/hls/", "/expMp4/").replace(".m3u8", "_720w.mp4")
                                try:
                                    if requests.head(cand_mp4, timeout=3).status_code == 200:
                                        return cand_mp4, "video", title, vhls.get("duration", 0), vhls.get("width"), vhls.get("height"), thumb
                                except Exception:
                                    pass
                                return vhls["url"], "video", title, vhls.get("duration", 0), vhls.get("width"), vhls.get("height"), thumb

            # If not a video, extract full resolution original photo
            images = pdata.get("images", {})
            if "orig" in images and images["orig"].get("url"):
                orig = images["orig"]
                return orig["url"], "image", title, 0, orig.get("width"), orig.get("height"), None

    except Exception as e:
        logger.warning(f"Pinterest API query error: {e}")

    return None, None, None, None, None, None, None


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
    .card {{ background: #131b2e; border: 1px solid #1f2d47; border-radius: 24px; padding: 32px 24px; max-width: 520px; width: 100%; box-shadow: 0 20px 40px rgba(0,0,0,0.5); text-align: center; }}
    .icon {{ font-size: 54px; margin-bottom: 14px; display: inline-block; }}
    h1 {{ font-size: 24px; font-weight: 700; color: #fff; margin-bottom: 8px; }}
    p.subtitle {{ font-size: 14px; color: #94a3b8; margin-bottom: 20px; line-height: 1.5; }}
    .copy-box {{ background: #0b1120; border: 1px dashed #3b82f6; border-radius: 14px; padding: 14px; margin-bottom: 20px; text-align: left; }}
    .copy-label {{ font-size: 11px; text-transform: uppercase; color: #60a5fa; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 6px; }}
    .copy-url {{ font-family: ui-monospace, monospace; font-size: 12px; color: #38bdf8; word-break: break-all; margin-bottom: 10px; display: block; }}
    .btn {{ display: block; width: 100%; background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #fff; text-decoration: none; font-size: 15px; font-weight: 600; padding: 13px; border-radius: 14px; border: none; cursor: pointer; transition: transform 0.15s, opacity 0.15s; box-shadow: 0 8px 20px rgba(37, 99, 235, 0.35); text-align: center; }}
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
    <p class="subtitle">Save Pinterest, TikTok, Instagram & more straight into your iPhone Photos app!</p>

    <div class="copy-box">
      <div class="copy-label">Direct Download Stream URL</div>
      <span class="copy-url" id="streamUrl">https://botdownloaderbymk.vercel.app/api/stream?url=</span>
      <button class="btn" onclick="copyUrl()">📋 Copy Stream URL</button>
      <div class="toast" id="toast">✅ Copied to clipboard!</div>
    </div>
    
    <div class="steps">
      <div class="step">
        <span class="badge">1</span>
        <div>In Apple <b>Shortcuts</b>, tap <b>+</b> to create a new shortcut. Tap the <b>( ⓘ )</b> at bottom and turn <b>ON &quot;Show in Share Sheet&quot;</b>.</div>
      </div>
      <div class="step">
        <span class="badge">2</span>
        <div>Add action: <b><code>Get URLs from Shortcut Input</code></b> (Crucial for Pinterest/TikTok so the link is cleanly extracted).</div>
      </div>
      <div class="step">
        <span class="badge">3</span>
        <div>Add action: <b><code>Get Contents of URL</code></b>. Set URL to: <code>https://botdownloaderbymk.vercel.app/api/stream?url=</code> followed by <b><code>[URLs]</code></b>.</div>
      </div>
      <div class="step">
        <span class="badge">4</span>
        <div>Add action: <b><code>Save to Photo Album</code></b> (saves <code>[Contents of URL]</code> to <b>Recents</b>). Tap Done!</div>
      </div>
    </div>
  </div>

  <script>
    function copyUrl() {{
      const text = document.getElementById('streamUrl').innerText;
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
    media_type = "video"
    title = f"{platform['name']} Media"
    duration = None
    vid_width = None
    vid_height = None
    thumbnail_url = None
    stream_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        # 1. Specialized fast extractors for TikTok, Snapchat & Pinterest
        if platform.get("name") == "TikTok":
            tk_play, tk_hd, tk_title, tk_dur, tk_cov = extract_tiktok_direct(url)
            if tk_play:
                direct_url = tk_hd or tk_play
                if tk_title:
                    title = tk_title
                if tk_dur:
                    duration = int(tk_dur)
                thumbnail_url = tk_cov
                media_type = "video"
                logger.info(f"TikWM extraction succeeded for TikTok: {direct_url[:80]}")
        elif platform.get("name") == "Snapchat":
            snap_u, snap_t, snap_d = extract_snapchat_direct(url)
            if snap_u:
                direct_url = snap_u
                if snap_t:
                    title = snap_t
                media_type = "video"
                logger.info(f"Snapchat direct extraction succeeded: {direct_url[:80]}")
        elif platform.get("name") == "Pinterest":
            pin_u, pin_mtype, pin_t, pin_d, pin_w, pin_h, pin_th = extract_pinterest_direct(url)
            if pin_u:
                direct_url = pin_u
                media_type = pin_mtype or "video"
                if pin_t:
                    title = pin_t
                if pin_d:
                    duration = int(pin_d)
                if pin_w:
                    vid_width = pin_w
                if pin_h:
                    vid_height = pin_h
                if pin_th:
                    thumbnail_url = pin_th
                logger.info(f"Pinterest direct extraction succeeded ({media_type}): {direct_url[:80]}")

        # 2. Universal yt-dlp extractor fallback (handles all videos AND photos)
        if not direct_url:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "ignore_no_formats_error": True,
                "format": "best[ext=mp4][acodec!=none]/best[ext=mp4]/best/bestvideo/bv/b",
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-us,en;q=0.5",
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and "entries" in info and info["entries"]:
                    info = info["entries"][0]

            if info:
                if info.get("title"):
                    title = str(info["title"]).strip()
                if info.get("duration"):
                    duration = int(info["duration"])
                if info.get("thumbnail"):
                    thumbnail_url = info.get("thumbnail")
                if info.get("width"):
                    vid_width = info.get("width")
                if info.get("height"):
                    vid_height = info.get("height")

                chosen_format = None
                if "formats" in info and info["formats"]:
                    for f in reversed(info["formats"]):
                        if f.get("url") and f.get("ext") == "mp4" and f.get("vcodec") != "none" and f.get("acodec") != "none":
                            chosen_format = f
                            direct_url = f["url"]
                            media_type = "video"
                            break
                    if not direct_url:
                        for f in reversed(info["formats"]):
                            if f.get("url") and (f.get("ext") == "mp4" or f.get("vcodec") != "none"):
                                chosen_format = f
                                direct_url = f["url"]
                                media_type = "video"
                                break

                # If no video format found, inspect thumbnails for photo / image posts (Instagram, Pinterest, X, Reddit)
                if not direct_url:
                    if info.get("thumbnails"):
                        direct_url = info["thumbnails"][-1].get("url")
                        media_type = "image"
                    elif info.get("url"):
                        direct_url = info.get("url")
                        if any(ext in direct_url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                            media_type = "image"

                if chosen_format and chosen_format.get("http_headers"):
                    stream_headers.update(chosen_format["http_headers"])
                elif info.get("http_headers"):
                    stream_headers.update(info["http_headers"])
                elif "instagram.com" in url.lower():
                    stream_headers["Referer"] = "https://www.instagram.com/"
                elif "tiktok.com" in url.lower():
                    stream_headers["Referer"] = "https://www.tiktok.com/"

        # Double check media_type from URL if still marked video
        if direct_url and any(ext in direct_url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            media_type = "image"

        if not direct_url:
            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"❌ Could not extract media from {platform['name']}. Post may be private or protected."
            )
            return

        # 3. Download media stream into temporary file
        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"📥 **Downloading {platform['emoji']} {platform['name']} {media_type}...**"
        )

        is_hls = ".m3u8" in direct_url
        if is_hls and media_type == "video":
            tmp_file = os.path.join(tempfile.gettempdir(), f"vid_{uuid.uuid4().hex[:6]}.mp4")
            ydl_hls_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "bestvideo/bv/best",
                "outtmpl": tmp_file.replace(".mp4", "") + ".%(ext)s"
            }
            with yt_dlp.YoutubeDL(ydl_hls_opts) as ydl_hls:
                ydl_hls.download([direct_url])
            if not os.path.exists(tmp_file):
                base = tmp_file.replace(".mp4", "")
                for ext in [".mp4", ".mkv", ".ts"]:
                    if os.path.exists(base + ext):
                        tmp_file = base + ext
                        break
        else:
            file_ext = ".jpg" if media_type == "image" else ".mp4"
            tmp_file = os.path.join(tempfile.gettempdir(), f"media_{uuid.uuid4().hex[:6]}{file_ext}")
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
                    f"⚠️ Media size ({total_bytes // (1024 * 1024)} MB) exceeds Telegram's 50 MB upload limit."
                )
                return

        if not os.path.exists(tmp_file) or os.path.getsize(tmp_file) == 0:
            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"❌ Downloaded stream was empty or blocked by {platform['name']}."
            )
            return

        # 4. Upload to Telegram (Photo vs Video)
        if media_type == "image":
            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"🚀 **Uploading {platform['name']} photo to chat...**"
            )
            caption_text = f"🖼️ {platform['emoji']} {platform['name']}\n\n📌 {title[:80]}"
            with open(tmp_file, "rb") as pf:
                upload_res = requests.post(
                    f"{TELEGRAM_API}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption_text},
                    files={"photo": (os.path.basename(tmp_file), pf, "image/jpeg")},
                    timeout=40
                )
        else:
            # Inspect exact native dimensions from MP4 file header
            extracted_w, extracted_h = extract_mp4_dimensions(tmp_file)
            if extracted_w and extracted_h:
                vid_width, vid_height = extracted_w, extracted_h
                logger.info(f"Detected native MP4 dimensions: {vid_width}x{vid_height}")

            thumb_bytes = None
            if thumbnail_url:
                try:
                    r_th = requests.get(thumbnail_url, headers=stream_headers, timeout=6)
                    if r_th.status_code == 200 and len(r_th.content) > 100:
                        thumb_bytes = r_th.content
                except Exception as e:
                    logger.warning(f"Failed to fetch thumbnail: {e}")

            edit_telegram_message(
                chat_id,
                status_msg_id,
                f"🚀 **Uploading {platform['name']} video to chat...**"
            )
            caption_text = f"🎬 {platform['emoji']} {platform['name']}\n\n📌 {title[:80]}"
            send_data = {
                "chat_id": chat_id,
                "caption": caption_text,
                "supports_streaming": "true",
            }
            if duration:
                send_data["duration"] = int(duration)
            if vid_width and vid_height:
                send_data["width"] = int(vid_width)
                send_data["height"] = int(vid_height)

            files = {"video": (os.path.basename(tmp_file), None, "video/mp4")}
            with open(tmp_file, "rb") as vf:
                files["video"] = (os.path.basename(tmp_file), vf, "video/mp4")
                if thumb_bytes:
                    files["thumbnail"] = ("thumb.jpg", thumb_bytes, "image/jpeg")

                upload_res = requests.post(
                    f"{TELEGRAM_API}/sendVideo",
                    data=send_data,
                    files=files,
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
        logger.error(f"Error handling media: {e}", exc_info=True)
        edit_telegram_message(
            chat_id,
            status_msg_id,
            f"❌ Error downloading media: {str(e)[:100]}"
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

        # Direct Video/Media Stream for iOS Shortcut (Saves straight to iPhone Camera Roll without Telegram)
        if action == "stream" or "stream" in full_path or action == "download" or "download" in full_path:
            raw_url = (
                query.get("url", [""])[0]
                or query.get("link", [""])[0]
                or query.get("u", [""])[0]
                or query.get("text", [""])[0]
                or query.get("q", [""])[0]
                or query.get("input", [""])[0]
            )

            # If parameter was missing or empty, search full decoded path and query string
            if not raw_url:
                full_decoded = urllib.parse.unquote(self.path)
                m_all = URL_REGEX.search(full_decoded)
                if m_all:
                    raw_url = m_all.group(0)

            quality_raw = query.get("quality", ["best"])[0].lower()
            m_q = re.search(r"\d+", quality_raw)
            q_height = int(m_q.group(0)) if m_q else None

            m = URL_REGEX.search(raw_url)
            target_url = m.group(0) if m else raw_url.strip()

            if not target_url:
                self._send_json(400, {
                    "error": "Missing 'url' query parameter",
                    "tip": "In your iOS Shortcut, add 'Get URLs from Shortcut Input' before 'Get Contents of URL'."
                })
                return

            platform = detect_platform(target_url)
            direct_url = None
            media_type = "video"
            stream_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }

            if platform.get("name") == "TikTok":
                tk_play, tk_hd, _, _, _ = extract_tiktok_direct(target_url)
                if q_height and q_height >= 1080 and tk_hd:
                    direct_url = tk_hd
                elif tk_play:
                    direct_url = tk_play
            elif platform.get("name") == "Snapchat":
                snap_u, _, _ = extract_snapchat_direct(target_url)
                if snap_u:
                    direct_url = snap_u
            elif platform.get("name") == "Pinterest":
                pin_u, pin_mtype, _, _, _, _, _ = extract_pinterest_direct(target_url)
                if pin_u:
                    direct_url = pin_u
                    media_type = pin_mtype or "video"

            if not direct_url:
                try:
                    fmt_str = (
                        f"best[height<={q_height}][ext=mp4][acodec!=none]/best[height<={q_height}][ext=mp4]/best[height<={q_height}]/best/bestvideo/bv/b"
                        if q_height
                        else "best[ext=mp4][acodec!=none]/best[ext=mp4]/best/bestvideo/bv/b"
                    )
                    ydl_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "noplaylist": True,
                        "ignore_no_formats_error": True,
                        "format": fmt_str,
                        "http_headers": {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        }
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(target_url, download=False)
                        if info and "entries" in info and info["entries"]:
                            info = info["entries"][0]

                    chosen_format = None
                    if info:
                        if "formats" in info and info["formats"]:
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
                                    if f.get("url") and (f.get("ext") == "mp4" or f.get("vcodec") != "none"):
                                        chosen_format = f
                                        direct_url = f["url"]
                                        break

                        # If no video stream, check for image/photo thumbnails (Instagram, Pinterest, X)
                        if not direct_url:
                            if info.get("thumbnails"):
                                direct_url = info["thumbnails"][-1].get("url")
                                media_type = "image"
                            elif info.get("url"):
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
                self._send_json(404, {"error": "Could not extract media stream from URL"})
                return

            # If client requested JSON format
            if query.get("format", [""])[0].lower() == "json":
                self._send_json(200, {
                    "status": "success",
                    "url": direct_url,
                    "platform": platform["name"],
                    "media_type": media_type
                })
                return

            # Special handling for HLS (.m3u8) streams (like Pinterest story videos):
            # Apple Shortcuts 'Get Contents of URL' downloads .m3u8 as a text file which Photos cannot save.
            # Convert fragments to a real MP4 on the fly and stream directly to iOS if <= 4.5 MB!
            if ".m3u8" in direct_url and media_type == "video":
                try:
                    tmp_hls = os.path.join(tempfile.gettempdir(), f"stream_{uuid.uuid4().hex[:6]}.mp4")
                    ydl_hls_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "format": "bestvideo/bv/best",
                        "outtmpl": tmp_hls.replace(".mp4", "") + ".%(ext)s"
                    }
                    with yt_dlp.YoutubeDL(ydl_hls_opts) as ydl_h:
                        ydl_h.download([direct_url])

                    real_mp4 = tmp_hls
                    if not os.path.exists(real_mp4):
                        base = tmp_hls.replace(".mp4", "")
                        for ext in [".mp4", ".mkv", ".ts"]:
                            if os.path.exists(base + ext):
                                real_mp4 = base + ext
                                break

                    if os.path.exists(real_mp4):
                        fsize = os.path.getsize(real_mp4)
                        if 0 < fsize <= 4400000:
                            with open(real_mp4, "rb") as vf:
                                v_data = vf.read()
                            try:
                                os.remove(real_mp4)
                            except Exception:
                                pass
                            self.send_response(200)
                            self.send_header("Content-Type", "video/mp4")
                            self.send_header("Content-Disposition", 'attachment; filename="pinterest_video.mp4"')
                            self.send_header("Content-Length", str(len(v_data)))
                            self.send_header("Access-Control-Allow-Origin", "*")
                            self.end_headers()
                            self.wfile.write(v_data)
                            return
                except Exception as hls_err:
                    logger.warning(f"Failed to stream converted HLS: {hls_err}")

            # Direct 302 Redirect to high-speed CDN URL (Photos, Videos)
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
