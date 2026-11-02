# Telegram Universal Video Downloader Bot ⚡

A high-performance Telegram bot that downloads public videos from 1,500+ platforms with automatic platform detection, adaptive FFmpeg compression (<50 MB), and 24/7 serverless & cloud keep-alive support.

---

## 🚀 Key Features

- **Automatic Platform Detection:** Detects and flags incoming URLs instantly:
  - 📸 **Instagram** (Reels, Posts, Stories)
  - 🎵 **TikTok** (No watermark)
  - 🔴 **YouTube** (Shorts & Standard Videos)
  - 🐦 **X (Twitter)** Media
  - 👽 **Reddit** Video Streams
  - 📘 **Facebook** Videos
  - 🟣 **Twitch, Pinterest, Vimeo**, and 1,500+ more
- **Dual Deployment Ready:**
  - **Vercel Serverless (Webhooks):** 24/7 serverless zero-maintenance bot.
  - **Docker / Render (Long Polling):** Full containerized deployment with FFmpeg adaptive compression for massive files.
- **24/7 Keep-Alive HTTP Ping Server:** Active ping and healthcheck endpoints.

---

## 🌐 Live URLs & Ping Endpoint

- **Vercel Production URL:** `https://botdownloaderbymk.vercel.app`
- **Ping URL (Keep-Alive):** `https://botdownloaderbymk.vercel.app/ping`
- **Health Check URL:** `https://botdownloaderbymk.vercel.app/health`
- **Telegram Webhook Endpoint:** `https://botdownloaderbymk.vercel.app/api/webhook`
- **One-Click Webhook Setup:** `https://botdownloaderbymk.vercel.app/setup`

### How to Keep the Bot Awake 24/7:
1. Open [UptimeRobot](https://uptimerobot.com) or [cron-job.org](https://cron-job.org).
2. Create an HTTP monitor pointing to:
   `https://botdownloaderbymk.vercel.app/ping`
3. Set interval to **5 or 10 minutes**.

---

## 🛠️ Deploying & Updating on Vercel

The project is connected to the GitHub repository [`mkalgo1/botdownloaderbymk`](https://github.com/mkalgo1/botdownloaderbymk).

1. Push your changes to `main`.
2. Vercel automatically rebuilds and redeploys to `botdownloaderbymk.vercel.app`.
3. To activate the Telegram Webhook, visit:
   `https://botdownloaderbymk.vercel.app/setup`
   or execute:
   ```bash
   curl -X POST "https://api.telegram.org/bot9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s/setWebhook?url=https://botdownloaderbymk.vercel.app/api/webhook"
   ```

---

## 💻 Local Testing

```bash
# Clone
git clone https://github.com/mkalgo1/botdownloaderbymk.git
cd botdownloaderbymk

# Virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Run
python bot.py
```
