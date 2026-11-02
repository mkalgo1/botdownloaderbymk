# Telegram Universal Video Downloader Bot ⚡

A production-ready Telegram bot that downloads public videos from 1,500+ platforms (TikTok, Instagram Reels, YouTube Shorts & Videos, X/Twitter, Reddit, Facebook, Vimeo, Twitch) with automatic adaptive FFmpeg compression (<50 MB) and a built-in keep-alive HTTP ping server to prevent cloud instances from sleeping.

---

## 🚀 Key Features

- **1,500+ Platforms Supported:** TikTok (no watermark), Instagram Reels/Stories, YouTube (Shorts & Standard), X/Twitter, Reddit, Facebook, Twitch, Vimeo, etc.
- **Adaptive FFmpeg Engine:** Files exceeding Telegram's 48 MB safety margin are automatically re-encoded and scaled down to ~44 MB for smooth streaming.
- **In-App Streaming:** Delivered with `supports_streaming=True` and MP4 faststart headers.
- **24/7 Keep-Alive HTTP Server:** Integrated `aiohttp` web server running alongside the bot on port `8080` (or dynamic cloud `$PORT`) with `/ping` and `/health` endpoints.
- **Zero Disk Leakage:** Downloads are processed in ephemeral sandbox directories pruned immediately on completion or failure.

---

## 🌐 24/7 Awake & Ping URL System

Free cloud platforms (like Render, Koyeb, Glitch) put applications to sleep after 15 minutes of inactivity if they do not receive HTTP traffic. 

This bot includes a built-in HTTP server listening on `/ping` and `/health`.

### Your Ping URL Format:
When deployed to **Render** or similar cloud hosts:
- **Root URL:** `https://<YOUR-APP-NAME>.onrender.com/`
- **Ping URL:** `https://<YOUR-APP-NAME>.onrender.com/ping`
- **Health Check URL:** `https://<YOUR-APP-NAME>.onrender.com/health`

### How to Keep the Bot Awake 24/7 (Free):
1. Deploy the bot to [Render](https://render.com) (Web Service) or [Koyeb](https://www.koyeb.com).
2. Copy your service URL (e.g., `https://botdownloaderbymk.onrender.com`).
3. Sign up for free at [UptimeRobot](https://uptimerobot.com) or [cron-job.org](https://cron-job.org).
4. Create a new monitor:
   - **Monitor Type:** HTTP(s)
   - **URL:** `https://<YOUR-APP-NAME>.onrender.com/ping`
   - **Monitoring Interval:** Every 5 or 10 minutes
5. *(Optional)* You can also set the environment variable in Render:
   - `PING_URL=https://<YOUR-APP-NAME>.onrender.com/ping`
   The bot will also self-ping every 10 minutes from inside its own background worker!

---

## 🛠️ Local Development Setup

### 1. Prerequisites
- Python 3.10 or higher
- FFmpeg and FFprobe installed on your operating system:
  - **Ubuntu/Debian:** `sudo apt update && sudo apt install -y ffmpeg`
  - **macOS:** `brew install ffmpeg`
  - **Windows:** Download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or `winget install Gyan.FFmpeg`

### 2. Installation
```bash
git clone https://github.com/mkalgo1/botdownloaderbymk.git
cd botdownloaderbymk
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Run Locally
```bash
# Set your bot token
export BOT_TOKEN="9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s"

# Run bot
python bot.py
```

---

## ☁️ Cloud Deployment (Render / Docker)

### Option A: Render (Recommended Free Web Service)
1. Go to [Render Dashboard](https://dashboard.render.com/) and click **New +** → **Web Service**.
2. Connect your GitHub repository: `botdownloaderbymk`.
3. Choose **Docker** as runtime (Render detects the `Dockerfile` automatically).
4. Under **Environment Variables**, add:
   - `BOT_TOKEN`: `9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s`
   - `PING_URL`: `https://<your-service-name>.onrender.com/ping`
5. Click **Deploy Web Service**.
6. Once deployed, copy your URL and paste `https://<your-service-name>.onrender.com/ping` into UptimeRobot!

### Option B: Railway
1. Go to [Railway](https://railway.com) → **New Project** → **Deploy from GitHub repo**.
2. Select `botdownloaderbymk`.
3. In **Variables**, add:
   - `BOT_TOKEN`: `9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s`
4. Railway will automatically build the Dockerfile with FFmpeg and run 24/7.
