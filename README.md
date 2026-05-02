# 📧 TempMail Bot

A self-hosted Telegram bot that gives users **temporary email addresses** on your custom domain. Emails arrive instantly in their Telegram chat — no signup, no inbox, no hassle.

---

## ✨ Features

- 🎲 **Random emails** — Auto-generate addresses like `x8kq2m@yourdomain.com`
- ✏️ **Custom emails** — Users pick their own handle: `/custom john` → `john@yourdomain.com`
- ⚡ **Auto-delivery** — Gmail is polled every 10s, emails appear in Telegram instantly
- 📜 **Email history** — View all past emails with `/history`
- 🔒 **Private** — Each user only sees emails sent to their own address
- 🛠️ **Self-hosted** — You own the data, deploy anywhere

---

## 🏗️ Architecture

```
Sender → yourdomain.com → ImprovMX (catch-all) → Gmail → Bot polls Gmail → Telegram
```

1. Someone sends an email to `anything@yourdomain.com`
2. **ImprovMX** catches all emails and forwards them to your Gmail
3. The bot polls Gmail every 10 seconds for new messages
4. When a match is found, the email is delivered to the user's Telegram chat

---

## 📋 Prerequisites

- A **custom domain** (e.g. from Namecheap, Cloudflare, GoDaddy, etc.)
- A **Gmail account**
- A **Telegram bot** (created via BotFather)
- An [**ImprovMX**](https://improvmx.com) account (free tier works)

---

## 🚀 Setup Guide

### Step 1 — Create a Telegram Bot

1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot`
3. Choose a **name** (e.g. `TempMail Bot`) and a **username** (e.g. `mytempmail_bot`)
4. BotFather will give you a token like:
   ```
   7123456789:AAH1234abcd5678efgh9012ijkl
   ```
5. Copy this — it's your `TELEGRAM_BOT_TOKEN`

---

### Step 2 — Set Up ImprovMX (Email Forwarding)

ImprovMX forwards **all emails** sent to your domain into a single Gmail inbox. Free tier supports up to 25 aliases.

1. Go to [**app.improvmx.com**](https://app.improvmx.com) and sign up
2. Click **Add Domain** and enter your domain (e.g. `yourdomain.com`)
3. ImprovMX will show you **DNS records** to add. Go to your domain registrar's DNS settings and add:

   | Type | Host/Name | Value | Priority |
   |------|-----------|-------|----------|
   | **MX** | `@` | `mx1.improvmx.com` | `10` |
   | **MX** | `@` | `mx2.improvmx.com` | `20` |
   | **TXT** | `@` | `v=spf1 include:spf.improvmx.com ~all` | — |

4. Back in ImprovMX, create a **catch-all alias**:
   - **Alias:** `*` (asterisk = catch-all, receives ALL emails)
   - **Forward to:** `yourname@gmail.com`
5. Click **Check DNS** and wait for it to verify (can take a few minutes)
6. **Test it** — Send an email to `test123@yourdomain.com` and confirm it arrives in your Gmail

> **Note:** DNS propagation can take up to 24-48 hours, but usually completes within 5-10 minutes.

---

### Step 3 — Get Google OAuth2 Credentials

The bot reads your Gmail via the Gmail API. You need OAuth2 credentials for this.

#### 3a. Create a Google Cloud Project

1. Go to [**Google Cloud Console**](https://console.cloud.google.com/)
2. Click the project dropdown (top bar) → **New Project**
3. Name it (e.g. `TempMail Bot`) → **Create**
4. Note your **Project ID** — this is your `GOOGLE_PROJECT_ID`

#### 3b. Enable the Gmail API

1. In your project, go to **APIs & Services** → [**Library**](https://console.cloud.google.com/apis/library)
2. Search for **Gmail API**
3. Click it → **Enable**

#### 3c. Configure OAuth Consent Screen

1. Go to **APIs & Services** → [**OAuth consent screen**](https://console.cloud.google.com/apis/credentials/consent)
2. Select **External** → **Create**
3. Fill in the required fields:
   - **App name:** `TempMail Bot`
   - **User support email:** Your email
   - **Developer contact:** Your email
4. Click **Save and Continue** through the remaining steps
5. Under **Test users**, add your Gmail address

#### 3d. Create OAuth2 Credentials

1. Go to **APIs & Services** → [**Credentials**](https://console.cloud.google.com/apis/credentials)
2. Click **+ Create Credentials** → **OAuth client ID**
3. **Application type:** Desktop app
4. **Name:** `TempMail Bot`
5. Click **Create**
6. You'll see:
   - **Client ID** → this is your `GOOGLE_CLIENT_ID`
   - **Client secret** → this is your `GOOGLE_CLIENT_SECRET`

#### 3e. Get Access & Refresh Tokens

1. Clone this repo and create your `.env` file (see Step 4 below)
2. Run the bot for the first time:
   ```bash
   python mailmanager.py
   ```
3. A **browser window** will open asking you to sign in to Google
4. Sign in with the Gmail account that receives forwarded emails
5. Grant the requested permissions
6. The bot will save `token.json` automatically — this contains your `GOOGLE_ACCESS_TOKEN` and `GOOGLE_REFRESH_TOKEN`
7. Open `token.json` and copy the values into your `.env`:
   ```bash
   cat token.json
   ```
   - `"token"` → `GOOGLE_ACCESS_TOKEN`
   - `"refresh_token"` → `GOOGLE_REFRESH_TOKEN`

> **Note:** After copying the tokens to `.env`, you can delete `token.json` and `credentials.json` — the bot regenerates them from env vars automatically.

---

### Step 4 — Configure & Run

1. **Clone the repo:**
   ```bash
   git clone https://github.com/sagardn/tempmail.git
   cd tempmail
   ```

2. **Install dependencies:**
   ```bash
   pip install python-telegram-bot[job-queue] google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv
   ```

3. **Create your `.env` file:**
   ```bash
   cp .env.example .env
   ```

4. **Fill in your values:**
   ```env
   # ─── Telegram ─────────────────────────────────
   TELEGRAM_BOT_TOKEN=7123456789:AAH1234abcd5678efgh
   TELEGRAM_POLL_INTERVAL=10

   # ─── Mail ─────────────────────────────────────
   MAIL_DOMAIN=yourdomain.com

   # ─── Google OAuth2 ────────────────────────────
   GOOGLE_CLIENT_ID=123456789-xxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxx
   GOOGLE_PROJECT_ID=your-project-id
   GOOGLE_ACCESS_TOKEN=ya29.xxxxx
   GOOGLE_REFRESH_TOKEN=1//xxxxx
   ```

5. **Run the bot:**
   ```bash
   python mailmanager.py
   ```

---

## 💬 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Get a new random temp email |
| `/newmail` | Generate a new random email |
| `/custom <name>` | Create a custom email (e.g. `/custom john`) |
| `/mymail` | Show your current email |
| `/check` | Manually check for new emails |
| `/history` | View all received emails |

---

## 🖥️ Deploy to VPS (24/7)

For always-on hosting, deploy to any Linux VPS:

```bash
# Upload to server
scp -r ./tempmail root@YOUR_SERVER_IP:/opt/tempmail/

# SSH in and run the deploy script
ssh root@YOUR_SERVER_IP
bash /opt/tempmail/deploy.sh
```

The deploy script installs dependencies, creates a systemd service, and starts the bot with auto-restart on crash.

```bash
# Useful commands on the server
systemctl status tempmail-bot    # Check status
journalctl -u tempmail-bot -f    # View live logs
systemctl restart tempmail-bot   # Restart
systemctl stop tempmail-bot      # Stop
```

---

## 📁 Project Structure

```
tempmail/
├── mailmanager.py      # Main bot application
├── deploy.sh           # VPS deployment script
├── .env                # Your secrets (git-ignored)
├── .env.example        # Template for .env
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

---

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| `InvalidToken` error | Regenerate your bot token from [@BotFather](https://t.me/BotFather) |
| No emails arriving | Check ImprovMX DNS is verified, test with a manual email |
| `Missing credentials.json` | Make sure all `GOOGLE_*` env vars are set in `.env` |
| Browser doesn't open for OAuth | Run the bot on a machine with a desktop browser for the first auth |
| `Token has been expired or revoked` | Delete `token.json` and re-run to re-authenticate |

---

## 📄 License

MIT — use it, fork it, make it yours.
