# Universal Media Downloader & Facebook Page Auto-Checker Bot ⚡

A high-performance Telegram bot that **automatically monitors specified Facebook pages for new video/reel/photo uploads and downloads them directly into your Telegram chat**, while also serving as a universal on-demand media downloader for 1,500+ platforms (Instagram, TikTok, YouTube, Reddit, Pinterest, etc.).

---

## 🚀 Key Features

1. **Automated Facebook Page & Profile Checker:**
   - Automatically polls monitored Facebook pages:
     - `https://web.facebook.com/profile.php?id=61556328743295` (Paris France Tour)
     - `https://web.facebook.com/profile.php?id=100083193627339` (FX France Express)
     - `https://web.facebook.com/lavialyon` (La vie à Lyon France)
   - Discovers new Reels, Videos, and Photos immediately upon upload.
   - Automatically downloads the highest quality stream and pushes it directly into your Telegram bot chat with title, description, and source link!

2. **Advanced Anti-Bot Block Protection (Long-Term Reliability):**
   - **Browser TLS Fingerprint Impersonation:** Emulates real Chrome (`chrome120`, `chrome119`) and Safari desktop TLS handshakes using `curl_cffi`, completely bypassing Facebook's anti-bot blocks.
   - **Human Jitter & Polite Pacing:** Randomizes delays (5-14s between pages, ±60s between polling loops) to eliminate automated periodic signatures.
   - **Exponential Backoff:** Gracefully pauses (up to 25 mins) if Facebook issues a 429 rate limit or challenge, preventing account or IP flags.
   - **Persistent Deduplication DB (`seen_posts.json`):** Tracks post IDs and canonical links so duplicate posts are never sent or re-downloaded.
   - **Optional Cookies Support (`cookies.txt` / `FB_COOKIES_FILE`):** Supports authenticated session cookies if needed.

3. **Media Processing & Telegram Optimization:**
   - **Faststart Streaming (`-movflags +faststart`):** Remuxes MP4 containers so videos stream immediately without waiting for full buffer.
   - **Exact Frame Thumbnailing:** Captures a frame at `00:00:00.200` to ensure preview aspect ratios in Telegram match the source video.
   - **Adaptive Compression:** If a video exceeds Telegram's 50 MB limit, compresses it automatically to fit within limits.

4. **Universal On-Demand Downloader:**
   - Send or paste any link into the bot chat to download media on demand:
     - 📸 **Instagram** (Reels, Posts, Stories)
     - 🎵 **TikTok** (No watermark)
     - 🔴 **YouTube** (Shorts & Standard Videos)
     - 🐦 **X (Twitter)** Media
     - 👽 **Reddit** Clips
     - 📘 **Facebook** Videos & Reels
     - 📌 **Pinterest**, Twitch, Vimeo, etc.

---

## 🤖 Telegram Bot & Commands

**Bot Username:** `@fbdownloaderpagesvidsbot`

| Command | Action |
| :--- | :--- |
| `/start` | Subscribes your chat to receive auto-downloaded uploads and shows help |
| `/status` | Displays monitor status, total posts seen, active subscribers, and last check time |
| `/checknow` | Forces an immediate manual check of all Facebook pages |
| `/pages` | Lists all currently monitored Facebook pages |
| `/addpage <url>` | Adds a new Facebook page or profile URL to monitor |
| `/delpage <url>` | Removes a page from the monitor list |

---

## 🛠️ Configuration (`.env`)

```env
BOT_TOKEN=your_telegram_bot_token_here
PORT=8080
CHECK_INTERVAL_SECONDS=360
TARGET_CHAT_ID=
FB_COOKIES_FILE=cookies.txt
```

---

## 💻 Running the Bot Locally

```bash
# Navigate to project
cd C:\Users\DZ_NEXTECH\.gemini\antigravity\scratch\botdownloaderbymk

# Install dependencies
pip install -r requirements.txt

# Start the bot
python bot.py
```

---

## 🐳 Running with Docker / Render

The project includes a ready `Dockerfile` with static FFmpeg pre-installed:

```bash
docker build -t fb-downloader-bot .
docker run -d --name fb_bot --env-file .env fb-downloader-bot
```
