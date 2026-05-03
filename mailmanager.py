"""
TempMail Telegram Bot
====================================
A Telegram bot that provides temporary email addresses on your custom domain.

How it works:
  1. User sends /start → gets a random email like abc123@yourdomain.com
  2. All emails to *@yourdomain.com are forwarded to your Gmail (already configured)
  3. Bot polls Gmail every 10 seconds for new emails
  4. When an email arrives for a user's address, bot sends it to their Telegram chat

Commands:
  /start    - Get a new random temp email
  /newmail  - Generate a new random email
  /custom   - Create a custom email (e.g. /custom john → john@yourdomain.com)
  /mymail   - Show your current email address
  /check    - Manually check for new emails
  /history  - Show all received emails

Requirements:
  - .env file with all credentials (see .env.example)
  - All emails to *@yourdomain.com forwarded to your Gmail
"""

import os
import sys
import json
import base64
import re
import html as html_module
import random
import string
import sqlite3
import asyncio
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

# ─── Load .env ───────────────────────────────────────────────────────────────

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────────────────

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
DOMAIN        = os.getenv("MAIL_DOMAIN", "yourdomain.com")
POLL_INTERVAL = int(os.getenv("TELEGRAM_POLL_INTERVAL", "10"))

if not BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN is missing from .env — aborting.")
    sys.exit(1)

SCOPES = ["https://mail.google.com/"]
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE       = os.path.join(BASE_DIR, "token.json")
DB_FILE          = os.path.join(BASE_DIR, "tempmail.db")

# ─── Generate credentials.json & token.json from .env if they don't exist ───

def _write_credentials_from_env():
    """Write credentials.json from env vars if the file doesn't exist."""
    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    project_id    = os.getenv("GOOGLE_PROJECT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if client_id and client_secret:
        data = {
            "installed": {
                "client_id": client_id,
                "project_id": project_id or "",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
            }
        }
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(data, f)

def _write_token_from_env():
    """Write token.json from env vars if the file doesn't exist."""
    access_token  = os.getenv("GOOGLE_ACCESS_TOKEN")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if refresh_token and client_id and client_secret:
        data = {
            "token": access_token or "",
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": SCOPES,
            "universe_domain": "googleapis.com",
            "account": "",
        }
        with open(TOKEN_FILE, "w") as f:
            json.dump(data, f)

if not os.path.exists(CREDENTIALS_FILE):
    _write_credentials_from_env()
if not os.path.exists(TOKEN_FILE):
    _write_token_from_env()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ─── Database ────────────────────────────────────────────────────────────────

def init_db():
    """Initialize SQLite database for user-email mappings."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id     INTEGER PRIMARY KEY,
            email       TEXT NOT NULL UNIQUE,
            created_at  TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS seen_emails (
            gmail_id    TEXT PRIMARY KEY,
            chat_id     INTEGER,
            delivered_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def db_get_email(chat_id: int) -> str | None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def db_set_email(chat_id: int, email: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        "INSERT OR REPLACE INTO users (chat_id, email, created_at) VALUES (?, ?, ?)",
        (chat_id, email, now),
    )
    conn.commit()
    conn.close()




def db_email_exists(email: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()
    return row is not None


def db_is_seen(gmail_id: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM seen_emails WHERE gmail_id = ?", (gmail_id,))
    row = c.fetchone()
    conn.close()
    return row is not None


def db_mark_seen(gmail_id: str, chat_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        "INSERT OR IGNORE INTO seen_emails (gmail_id, chat_id, delivered_at) VALUES (?, ?, ?)",
        (gmail_id, chat_id, now),
    )
    conn.commit()
    conn.close()


def db_get_all_users() -> list[tuple[int, str]]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id, email FROM users")
    rows = c.fetchall()
    conn.close()
    return rows


# ─── Gmail API ───────────────────────────────────────────────────────────────

def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Refreshing Gmail token ...")
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                log.error(f"Missing {CREDENTIALS_FILE}")
                sys.exit(1)
            log.info("Opening browser for Gmail authorization ...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            log.info("Token saved.")

    return build("gmail", "v1", credentials=creds)


def extract_links_from_html(html_text: str) -> list[tuple[str, str]]:
    """Extract all <a href="..."> links from HTML and return as (label, url) tuples."""
    links = []
    seen_urls = set()
    # Match <a ...href="URL"...>LABEL</a>  (handles single or double quotes)
    for match in re.finditer(
        r'<a\s[^>]*href=["\']([^"\'>]+)["\'][^>]*>(.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        url = html_module.unescape(match.group(1)).strip()
        # Skip mailto:, tel:, javascript:, anchors, and data URIs
        if not url or url.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        # De-duplicate by URL
        if url in seen_urls:
            continue
        seen_urls.add(url)
        # Clean up the label: strip inner HTML tags, unescape, and trim
        raw_label = re.sub(r"<[^>]+>", "", match.group(2))
        label = html_module.unescape(raw_label).strip()
        if not label:
            label = url[:60]  # fallback to the URL itself
        # Telegram button labels max 64 chars
        if len(label) > 64:
            label = label[:61] + "..."
        links.append((label, url))
    return links


def strip_html(html_text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_module.unescape(text)
    return text.strip()


def decode_body(payload: dict) -> tuple[str, str]:
    """Decode the email body. Returns (plain_text, raw_html).
    raw_html is the original HTML source (empty string if not available).
    """
    mime_type = payload.get("mimeType", "")

    if "body" in payload and payload["body"].get("data"):
        raw = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        if "html" in mime_type:
            return strip_html(raw), raw
        return raw, ""

    parts = payload.get("parts", [])
    plain_parts, html_parts = [], []

    for part in parts:
        part_mime = part.get("mimeType", "")
        if part.get("filename"):
            continue
        if part_mime.startswith("multipart/"):
            nested_text, nested_html = decode_body(part)
            if nested_text:
                plain_parts.append(nested_text)
            if nested_html:
                html_parts.append(nested_html)
            continue
        data = part.get("body", {}).get("data", "")
        if not data:
            continue
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if part_mime == "text/plain":
            plain_parts.append(decoded)
        elif part_mime == "text/html":
            html_parts.append(decoded)

    raw_html = "\n".join(html_parts) if html_parts else ""
    if plain_parts:
        return "\n".join(plain_parts).strip(), raw_html
    elif html_parts:
        return strip_html(raw_html), raw_html
    return "", ""


def get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def extract_recipient(headers: list) -> str:
    """Extract the original recipient email from headers.
    Check 'Delivered-To', 'X-Forwarded-To', 'To', and 'Envelope-To' headers.
    """
    # Priority order for finding the actual recipient on our domain
    for header_name in ["X-Forwarded-To", "Delivered-To", "X-Original-To", "To"]:
        value = get_header(headers, header_name)
        if value and DOMAIN in value.lower():
            # Extract email from "Name <email>" format
            match = re.search(r'[\w.+-]+@' + re.escape(DOMAIN), value, re.IGNORECASE)
            if match:
                return match.group(0).lower()
    return ""


def search_emails_for_address(service, email_address: str, max_results: int = 10) -> list:
    """Search Gmail for emails sent to a specific address."""
    query = f"to:{email_address}"

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results,
            includeSpamTrash=True
        ).execute()
        return results.get("messages", [])
    except Exception as e:
        log.error(f"Gmail search error: {e}")
        return []


def fetch_email_details(service, msg_id: str) -> dict | None:
    """Fetch full email details by message ID."""
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
        return msg
    except Exception as e:
        log.error(f"Failed to fetch email {msg_id}: {e}")
        return None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def generate_random_email() -> str:
    """Generate a random email address on our domain."""
    chars = string.ascii_lowercase + string.digits
    username = "".join(random.choices(chars, k=8))
    return f"{username}@{DOMAIN}"


def escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", text)


def format_email_message(msg: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    """Format an email into a nice Telegram message + inline link buttons.

    Returns (text, reply_markup).  reply_markup is None when there are no links.
    """
    headers = msg.get("payload", {}).get("headers", [])
    payload = msg.get("payload", {})

    from_addr = get_header(headers, "From")
    subject   = get_header(headers, "Subject") or "(No Subject)"
    date_str  = get_header(headers, "Date")

    body, raw_html = decode_body(payload)
    if len(body) > 2000:
        body = body[:2000] + "\n... [truncated]"

    # Extract clickable links from the HTML source
    links = extract_links_from_html(raw_html) if raw_html else []

    text = (
        f"📩 <b>New Email Received!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📤 <b>From:</b> {html_module.escape(from_addr)}\n"
        f"📋 <b>Subject:</b> {html_module.escape(subject)}\n"
        f"🕐 <b>Date:</b> {html_module.escape(date_str or 'Unknown')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<pre>{html_module.escape(body)}</pre>"
    )

    # Build InlineKeyboard with one URL button per link (max 20 to stay safe)
    reply_markup = None
    if links:
        buttons = []
        for label, url in links[:20]:
            try:
                buttons.append([InlineKeyboardButton(text=label, url=url)])
            except Exception:
                pass  # skip malformed URLs
        if buttons:
            reply_markup = InlineKeyboardMarkup(buttons)

    return text, reply_markup


# ─── Persistent Keyboard ─────────────────────────────────────────────────────

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔄 New Email"), KeyboardButton("📬 My Email")],
        [KeyboardButton("🔍 Check Inbox"), KeyboardButton("📜 History")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ─── Bot Commands ────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — create a random temp email for the user."""
    chat_id = update.effective_chat.id
    existing = db_get_email(chat_id)

    if existing:
        await update.message.reply_text(
            f"📬 You already have an active email:\n\n"
            f"<code>{existing}</code>\n\n"
            f"📋 Tap to copy! Emails sent here will appear in this chat.\n\n"
            f"💡 Want a custom name? Type:\n"
            f"<code>/custom yourname</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return

    email = generate_random_email()
    while db_email_exists(email):
        email = generate_random_email()

    db_set_email(chat_id, email)

    await update.message.reply_text(
        f"🎉 <b>Your Temp Email is Ready!</b>\n\n"
        f"📧 <code>{email}</code>\n\n"
        f"📋 Tap to copy! Any email sent to this address will appear here.\n\n"
        f"💡 Want a custom name? Type:\n"
        f"<code>/custom yourname</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )
    log.info(f"New user {chat_id} → {email}")


async def cmd_newmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /newmail — generate a new random email."""
    chat_id = update.effective_chat.id

    email = generate_random_email()
    while db_email_exists(email):
        email = generate_random_email()

    db_set_email(chat_id, email)

    await update.message.reply_text(
        f"🔄 <b>New Email Generated!</b>\n\n"
        f"📧 <code>{email}</code>\n\n"
        f"📋 Tap to copy! Old email is no longer active.",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )
    log.info(f"User {chat_id} new email → {email}")


async def cmd_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /custom <name> — create a custom email."""
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            f"Usage: <code>/custom yourname</code>\n"
            f"Example: <code>/custom john</code> → john@{DOMAIN}",
            parse_mode=ParseMode.HTML,
        )
        return

    username = context.args[0].lower().strip()

    # Validate username
    if not re.match(r"^[a-z0-9][a-z0-9._-]{1,30}[a-z0-9]$", username):
        await update.message.reply_text(
            "❌ Invalid username. Use only letters, numbers, dots, hyphens.\n"
            "Must be 3-32 characters, start and end with letter/number.",
        )
        return

    email = f"{username}@{DOMAIN}"

    if db_email_exists(email):
        await update.message.reply_text(
            f"❌ <code>{email}</code> is already taken. Try another name.",
            parse_mode=ParseMode.HTML,
        )
        return

    db_set_email(chat_id, email)

    await update.message.reply_text(
        f"✅ <b>Custom Email Created!</b>\n\n"
        f"📧 <code>{email}</code>\n\n"
        f"📋 Tap to copy! Emails sent here will appear in this chat.",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )
    log.info(f"User {chat_id} custom email → {email}")


async def cmd_mymail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mymail — show current email."""
    chat_id = update.effective_chat.id
    email = db_get_email(chat_id)

    if email:
        await update.message.reply_text(
            f"📬 Your current email:\n\n<code>{email}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text(
            "❌ You don't have an active email. Use /start to create one.",
        )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check — manually check for new emails."""
    chat_id = update.effective_chat.id
    email = db_get_email(chat_id)

    if not email:
        await update.message.reply_text("❌ No active email. Use /start first.")
        return

    await update.message.reply_text("🔍 Checking for new emails ...")

    service = context.bot_data.get("gmail_service")
    if not service:
        await update.message.reply_text("❌ Gmail service not available.")
        return

    messages = search_emails_for_address(service, email, max_results=20)
    new_count = 0

    for msg_info in messages:
        if db_is_seen(msg_info["id"]):
            continue

        msg = fetch_email_details(service, msg_info["id"])
        if not msg:
            continue

        text, reply_markup = format_email_message(msg)
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            db_mark_seen(msg_info["id"], chat_id)
            new_count += 1
        except Exception as e:
            log.error(f"Failed to send to {chat_id}: {e}")

    if new_count == 0:
        await update.message.reply_text(
            "📭 No new emails yet. They'll appear here automatically when they arrive!"
        )
    else:
        await update.message.reply_text(f"✅ Delivered {new_count} new email(s)!")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history — show all received emails."""
    chat_id = update.effective_chat.id
    email = db_get_email(chat_id)

    if not email:
        await update.message.reply_text("❌ No active email. Use /start first.")
        return

    service = context.bot_data.get("gmail_service")
    if not service:
        await update.message.reply_text("❌ Gmail service not available.")
        return

    messages = search_emails_for_address(service, email, max_results=20)

    if not messages:
        await update.message.reply_text("📭 No emails received yet for this address.")
        return

    await update.message.reply_text(f"📜 <b>Email History ({len(messages)} emails):</b>", parse_mode=ParseMode.HTML)

    for msg_info in messages:
        msg = fetch_email_details(service, msg_info["id"])
        if not msg:
            continue

        text, reply_markup = format_email_message(msg)
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            db_mark_seen(msg_info["id"], chat_id)
        except Exception as e:
            log.error(f"Failed to send history to {chat_id}: {e}")




# ─── Auto-Polling Gmail ─────────────────────────────────────────────────────

async def poll_gmail(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check Gmail for new emails and deliver to users."""
    service = context.bot_data.get("gmail_service")
    if not service:
        return

    users = db_get_all_users()
    if not users:
        return

    for chat_id, email in users:
        try:
            messages = search_emails_for_address(service, email, max_results=5)

            for msg_info in messages:
                if db_is_seen(msg_info["id"]):
                    continue

                msg = fetch_email_details(service, msg_info["id"])
                if not msg:
                    continue

                text, reply_markup = format_email_message(msg)
                try:
                    await context.bot.send_message(
                        chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                    )
                    db_mark_seen(msg_info["id"], chat_id)
                    log.info(f"📩 Delivered email to {chat_id} ({email})")
                except Exception as e:
                    log.error(f"Failed to deliver to {chat_id}: {e}")

        except Exception as e:
            log.error(f"Poll error for {chat_id} ({email}): {e}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  📧 TempMail Bot")
    print("=" * 50)
    print()

    # Initialize database
    init_db()
    log.info("Database initialized")

    # Initialize Gmail
    gmail_service = get_gmail_service()
    log.info("Gmail API connected")

    # Build Telegram bot
    app = Application.builder().token(BOT_TOKEN).build()

    # Store Gmail service in bot data
    app.bot_data["gmail_service"] = gmail_service

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("newmail", cmd_newmail))
    app.add_handler(CommandHandler("custom", cmd_custom))
    app.add_handler(CommandHandler("mymail", cmd_mymail))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("history", cmd_history))

    # Route keyboard button taps to commands
    BUTTON_MAP = {
        "🔄 New Email": cmd_newmail,
        "📬 My Email": cmd_mymail,
        "🔍 Check Inbox": cmd_check,
        "📜 History": cmd_history,
    }

    async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        handler = BUTTON_MAP.get(update.message.text)
        if handler:
            await handler(update, context)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(
            "^(" + "|".join(re.escape(k) for k in BUTTON_MAP) + ")$"
        ),
        handle_button,
    ))

    # Set up auto-polling job (every POLL_INTERVAL seconds)
    app.job_queue.run_repeating(poll_gmail, interval=POLL_INTERVAL, first=5)
    log.info(f"Auto-poll enabled: checking Gmail every {POLL_INTERVAL}s")

    # Start the bot
    log.info("Bot is running! Press Ctrl+C to stop.")
    print(f"\n🤖 Bot is LIVE! Send /start to your bot on Telegram.\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
