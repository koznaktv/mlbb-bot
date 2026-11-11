import os
import re
import html
import asyncio
import sqlite3
import logging
import urllib.parse
from html import escape

from dotenv import load_dotenv
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "mlbb_bot.db")
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# Animated Stickers (working across all Telegram apps)
STICKER_GAME = "CAACAgEAAxkBAAEwdXxq8yLaW2py9CQmYO8-otTp8ieJRwACVgMAAr-QIUR8-pez2EZI2z0E"
STICKER_LIGHTNING = "CAACAgEAAxkBAAEwdStq8xrpcnlC4U7SKxVt5GedlYuqAQACAwkAAuN4BAABpjXNpeoaPeI9BA"
STICKER_BAG = "CAACAgEAAxkBAAEwdIRq8xW_39AYN6yT9oRH0vljHjAhEwACygIAAvzW0EZtPC0-cOSVBD0E"

# Standard Unicode Emojis (crystal clear on all devices, no black boxes)
EMOJI_CARD = "💳"
EMOJI_CHECK = "✔️"
EMOJI_USER = "👤"
EMOJI_RED_DOT = "🔴"
EMOJI_DOWN = "🔽"
EMOJI_THINK = "🤔"
EMOJI_HOME = "🏠"
EMOJI_SHOP = "🛍️"
EMOJI_TOP = "🔝"
EMOJI_MAIL = "✉️"
EMOJI_GLOBE = "🌐"
EMOJI_PIN = "📍"
EMOJI_STAR = "🌟"
EMOJI_ARROW = "➡️"

# Conversation States
UID, SERVER, RANK, PRICE, DESC, PHOTO = range(6)
SEARCH_QUERY = 6
TEAM_ACTION, TEAM_COUNT, TEAM_ROLES = range(7, 10)

ROLE_NAMES = {
    "mage": "🔮 سېھىرگەر (Mage)",
    "jungle": "🗡 ئورمانچى (Jungle)",
    "marksman": "🏹 ئاتقۇچى (Marksman)",
    "tank": "🛡 تانكا / Roam (Tank)",
    "exp": "⚔️ EXP جەڭچى (Fighter)",
}

def is_cancel(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    return "توختىتىش" in t or "بىكار" in t or t.lower() in ["cancel", "/cancel", "x", "❌"] or "❌" in t

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user INTEGER NOT NULL,
                username TEXT,
                uid TEXT,
                server TEXT,
                rank TEXT,
                price TEXT,
                description TEXT,
                photo1 TEXT,
                photo2 TEXT,
                video TEXT,
                channel_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        for col_name, col_type in [
            ("user", "INTEGER"),
            ("username", "TEXT"),
            ("uid", "TEXT"),
            ("server", "TEXT"),
            ("rank", "TEXT"),
            ("price", "TEXT"),
            ("description", "TEXT"),
            ("channel_message_id", "INTEGER"),
            ("photo1", "TEXT"),
            ("photo2", "TEXT"),
            ("video", "TEXT"),
        ]:
            if col_name not in cols:
                try:
                    conn.execute(f"ALTER TABLE accounts ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user INTEGER NOT NULL,
                username TEXT,
                count INTEGER NOT NULL,
                roles TEXT NOT NULL,
                channel_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📲 ھېساب يوللاش"), KeyboardButton("🔎 ھېساب ئىزدەش")],
            [KeyboardButton("📋 مېنىڭ ھېسابلىرىم"), KeyboardButton("🔔 ئۇقتۇرۇشلار")],
            [KeyboardButton("🎮 كوماندا يىغىش"), KeyboardButton("👥 دوست تەكلىپ قىلىش")],
            [KeyboardButton("ℹ️ ئۇچۇر")],
        ],
        resize_keyboard=True,
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ توختىتىش")]], resize_keyboard=True)

# ----------------- Start & Cancel -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    try:
        await update.message.reply_sticker(STICKER_GAME)
    except Exception:
        pass
    welcome_text = (
        "🎮 <b>MLBB بوتىغا خۇش كەلدىڭىز!</b>\n\n"
        f"{EMOJI_STAR} {EMOJI_HOME} <b>MLBB UYGHUR PLAYERS</b> {EMOJI_STAR}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 ئەسسالامۇئەلەيكۇم! سەرخىل سەپداشلار ۋە ھېساب بازىرىغا خۇش كەلدىڭىز!\n\n"
        f"{EMOJI_SHOP} <b>ھېساب يوللاش</b> — ھېسابىڭىزنى قانالغا كۆركەم ئېلان قىلىش\n"
        f"{EMOJI_THINK} <b>ھېساب ئىزدەش</b> — UID، Rank ياكى Server بويىچە تاپىش\n"
        f"{EMOJI_CARD} <b>مېنىڭ ھېسابلىرىم</b> — ئۆزىڭىز يوللىغان ھېسابلارنى كۆرۈش ۋە ئۆچۈرۈش\n"
        f"{EMOJI_PIN} <b>ئۇقتۇرۇشلار</b> — مۇھىم بىخەتەرلىك قائىدىلىرى\n"
        f"{EMOJI_TOP} <b>كوماندا يىغىش</b> — Rank ئۆرلەيدىغان سەپداشلارنى تېپىش ۋە ئوچۇق كوماندىلار\n"
        f"{EMOJI_USER} <b>دوست تەكلىپ قىلىش</b> — سەپداشلارنى سۇپىغا تەكلىپ قىلىش\n"
        f"{EMOJI_GLOBE} <b>ئۇچۇر</b> — سۇپا ۋە مۇلازىمەت ھەققىدە\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_DOWN} <i>باشلاش ئۈچۈن تۆۋەندىكى كۇنۇپكىلاردىن بىرنى تاللاڭ:</i>"
    )
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(
            "❌ <b>مەشغۇلات ئەمەلدىن قالدۇرۇلدى.</b>\n\nتۆۋەندىكى تىزىملىكتىن تاللاڭ:",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
    return ConversationHandler.END

# ----------------- Account Posting Flow -----------------
async def begin_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["account"] = {}
    try:
        await update.message.reply_sticker(STICKER_BAG)
    except Exception:
        pass
    await update.message.reply_text(
        "🆔 <b>1-قەدەم:</b> ھېسابىڭىزنىڭ <b>UID</b> نى كىرگۈزۈڭ:\n(مەسىلەن: <code>12345678</code>)",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    return UID

async def get_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_cancel(text):
        return await cancel(update, context)
    context.user_data["account"]["uid"] = text
    await update.message.reply_text(
        "🌐 <b>2-قەدەم:</b> Server رايون نومۇرىنى كىرگۈزۈڭ:\n(مەسىلەن: <code>2145</code>)",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    return SERVER

async def get_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_cancel(text):
        return await cancel(update, context)
    context.user_data["account"]["server"] = text
    await update.message.reply_text(
        "🏆 <b>3-قەدەم:</b> ھېسابنىڭ دەرىجىسى (Rank) نى كىرگۈزۈڭ:\n(مەسىلەن: <code>Mythic Immortal</code>، <code>Glory</code>، <code>Legend</code>)",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    return RANK

async def get_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_cancel(text):
        return await cancel(update, context)
    context.user_data["account"]["rank"] = text
    await update.message.reply_text(
        "💰 <b>4-قەدەم:</b> سېتىش باھاسىنى كىرگۈزۈڭ:\n(مەسىلەن: <b>150</b>)",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    return PRICE

async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_cancel(text):
        return await cancel(update, context)
    context.user_data["account"]["price"] = text
    await update.message.reply_text(
        "📝 <b>5-قەدەم:</b> ھېساب ھەققىدە قىسقىچە ئۇچۇر يېزىڭ:\n(مەسىلەن: <code>120 Hero, 95 Skin, Collector ۋە تەستىقلار بار</code>)",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    return DESC

async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_cancel(text):
        return await cancel(update, context)
    context.user_data["account"]["description"] = text[:700]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ رەسىمسىز يوللاش (ئۆتكۈزۈش)", callback_data="skip_photo")]
    ])
    await update.message.reply_text(
        "📸 <b>6-قەدەم:</b> ھېسابنىڭ رەسىمى (Screenshot) بولسا ئەۋەتىڭ.\nئەگەر رەسىم بولمىسا تۆۋەندىكى <b>«ئۆتكۈزۈش»</b> كۇنۇپكىسىنى بېسىڭ.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    return PHOTO

def make_account_post(account_id, data, user):
    username = f"@{user.username}" if user.username else f"ID: <code>{user.id}</code>"
    return (
        f"╔═══════════════════════╗\n"
        f"  {EMOJI_RED_DOT} {EMOJI_SHOP} <b>MLBB سەرخىل ھېساب سېتىلىدۇ</b> {EMOJI_RED_DOT}\n"
        f"╚═══════════════════════╝\n\n"
        f"{EMOJI_TOP} <b>تەرتىپ نومۇرى:</b> <code>#{account_id}</code>\n"
        f"🆔 <b>UID:</b> <code>{escape(str(data.get('uid', '')))}</code>\n"
        f"{EMOJI_GLOBE} <b>Server:</b> <code>{escape(str(data.get('server', '')))}</code>\n"
        f"🏆 <b>Rank:</b> <b>{escape(str(data.get('rank', '')))}</b>\n"
        f"{EMOJI_CARD} <b>باھاسى:</b> <b>{escape(str(data.get('price', '')))}</b> 💵\n"
        f"📝 <b>ئۇچۇر:</b> <i>{escape(str(data.get('description', 'كۆرسىتىلمىگەن')))}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_USER} <b>ئالاقىلاشقۇچى:</b> {username}\n"
        f"🤖 <b>ئېلان سۇپىسى:</b> @mlbb_uy_players_bot"
    )

async def publish_account(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_id=None):
    user = update.effective_user
    data = context.user_data.get("account", {})
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO accounts (user, username, uid, server, rank, price, description, photo1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user.id, user.username or "",
            data.get("uid", ""), data.get("server", ""),
            data.get("rank", ""), data.get("price", ""),
            data.get("description", ""), photo_id
        ))
        account_id = cur.lastrowid

    post_text = make_account_post(account_id, data, user)
    channel_msg_id = None
    channel_result = "ھېساب ساندانغا ساقلاندى."

    if CHANNEL_ID:
        try:
            try:
                await context.bot.send_sticker(chat_id=CHANNEL_ID, sticker=STICKER_BAG)
            except Exception:
                pass

            if photo_id:
                sent = await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=photo_id,
                    caption=post_text,
                    parse_mode="HTML"
                )
            else:
                sent = await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=post_text,
                    parse_mode="HTML"
                )
            channel_msg_id = sent.message_id
            with db() as conn:
                conn.execute("UPDATE accounts SET channel_message_id = ? WHERE id = ?", (channel_msg_id, account_id))
            channel_result = "ھېسابىڭىز قانالغا ئاپتوماتىك ئېلان قىلىندى!"
        except Exception:
            log.exception("Channel publishing failed")
            channel_result = "ھېساب ساندانغا ساقلاندى، لېكىن قانالغا يوللاش مەغلۇپ بولدى."

    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(
            f"✅ <b>{channel_result}</b>\nتەرتىپ نومۇرى: <code>#{account_id}</code>",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
    context.user_data.pop("account", None)
    return ConversationHandler.END

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("⚠️ رەسىم يوللاڭ ياكى «ئۆتكۈزۈش» نى بېسىڭ.")
        return PHOTO
    photo_id = update.message.photo[-1].file_id
    return await publish_account(update, context, photo_id=photo_id)

async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(reply_markup=None)
    return await publish_account(update, context, photo_id=None)

async def photo_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_cancel(text):
        return await cancel(update, context)
    txt = text.lower()
    if txt in ["يوق", "ئۆتكۈزۈش", "ئۆتكۈزۈۋېتىش", "skip", "no", "yoq", "بولدى"]:
        return await publish_account(update, context, photo_id=None)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ رەسىمسىز يوللاش (ئۆتكۈزۈش)", callback_data="skip_photo")]
    ])
    await update.message.reply_text(
        "⚠️ سىز تېكىست ئەۋەتتىڭىز. رەسىم (Screenshot) يوللاڭ ياكى تۆۋەندىكى «ئۆتكۈزۈش» كۇنۇپكىسىنى بېسىڭ.\nتوختاتماقچى بولسىڭىز «❌ توختىتىش» نى بېسىڭ.",
        reply_markup=keyboard,
    )
    return PHOTO

# ----------------- Account Search Flow -----------------
async def begin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJI_THINK} <b>ئىزدەيدىغان UID، Rank ياكى Server نى كىرگۈزۈڭ:</b>\n"
        "(مەسىلەن: <code>Mythic</code>، <code>2145</code> ياكى باھا)",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    return SEARCH_QUERY

async def search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if is_cancel(query):
        return await cancel(update, context)
    pattern = f"%{query}%"
    with db() as conn:
        rows = conn.execute("""
            SELECT * FROM accounts
            WHERE uid LIKE ? OR rank LIKE ? OR server LIKE ? OR price LIKE ? OR description LIKE ?
            ORDER BY id DESC LIMIT 10
        """, (pattern, pattern, pattern, pattern, pattern)).fetchall()

    if not rows:
        await update.message.reply_text("😔 بۇ بويىچە ھېچقانداق ھېساب تېپىلمىدى.", reply_markup=main_keyboard())
        return ConversationHandler.END

    await update.message.reply_text(f"🔍 <b>تېپىلغان ھېسابلار (جەمئىي {len(rows)} تال):</b>", parse_mode="HTML")
    for row in rows:
        acc_text = (
            f"🎮 <b>ھېساب #{row['id']}</b>\n"
            f"🆔 <b>UID:</b> <code>{row['uid'] or 'يوق'}</code>\n"
            f"🌐 <b>Server:</b> <code>{row['server'] or 'يوق'}</code>\n"
            f"🏆 <b>Rank:</b> <b>{row['rank'] or 'يوق'}</b>\n"
            f"{EMOJI_CARD} <b>باھاسى:</b> <b>{row['price']}</b> 💵\n"
            f"📝 <b>ئۇچۇر:</b> <i>{row['description'] or 'كۆرسىتىلمىگەن'}</i>\n"
            f"👤 <b>ئىگىسى:</b> @{row['username'] or row['user']}"
        )
        if row["photo1"]:
            await update.message.reply_photo(photo=row["photo1"], caption=acc_text, parse_mode="HTML")
        else:
            await update.message.reply_text(acc_text, parse_mode="HTML")

    await update.message.reply_text("✨ ئىزدەش تاماملاندى.", reply_markup=main_keyboard())
    return ConversationHandler.END

# ----------------- My Accounts & Channel Auto-Deletion -----------------
async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE user = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            f"📭 <b>ھازىرچە سىز يوللىغان ھېساب يوق.</b>\n\n"
            f"{EMOJI_CHECK} «📲 ھېساب يوللاش» كۇنۇپكىسىنى بېسىپ يېڭى ھېساب چىقارسىڭىز بولىدۇ.",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
        return

    await update.message.reply_text(
        f"📋 <b>سىز يوللىغان ھېساب سانى: {len(rows)}</b>",
        parse_mode="HTML",
    )
    for row in rows:
        account_id = row["id"]
        acc_text = (
            f"🎮 <b>ھېسابىڭىز #{account_id}</b>\n\n"
            f"🆔 <b>UID:</b> <code>{row['uid'] or 'يوق'}</code>\n"
            f"🌐 <b>Server:</b> <code>{row['server'] or 'يوق'}</code>\n"
            f"🏆 <b>Rank:</b> <b>{row['rank'] or 'يوق'}</b>\n"
            f"{EMOJI_CARD} <b>باھاسى:</b> <b>{row['price']}</b> 💵\n"
            f"📝 <b>ئۇچۇر:</b> <i>{row['description'] or 'كۆرسىتىلمىگەن'}</i>\n"
            f"📅 <b>ۋاقتى:</b> {row['created_at']}"
        )
        del_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 سېتىلدى / ئۆچۈرۈش", callback_data=f"delete:{account_id}")]
        ])
        if row["photo1"]:
            await update.message.reply_photo(
                photo=row["photo1"],
                caption=acc_text,
                parse_mode="HTML",
                reply_markup=del_keyboard,
            )
        else:
            await update.message.reply_text(
                acc_text,
                parse_mode="HTML",
                reply_markup=del_keyboard,
            )

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    account_id = int(q.data.split(":")[1])
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ ھەئە، ئۆچۈر", callback_data=f"confirm_delete:{account_id}"),
            InlineKeyboardButton("❌ ياق، قالدۇر", callback_data=f"cancel_delete:{account_id}"),
        ]
    ])
    await q.edit_message_reply_markup(reply_markup=keyboard)

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    account_id = int(q.data.split(":")[1])
    user_id = q.from_user.id

    with db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ? AND user = ?", (account_id, user_id)).fetchone()

    if not row:
        await q.edit_message_text("❌ بۇ ھېساب سىزنىڭ ئەمەس ياكى ئاللىقاچان ئۆچۈرۈلگەن.")
        return

    channel_message_id = row["channel_message_id"]

    # Delete post from Telegram channel
    if CHANNEL_ID and channel_message_id:
        try:
            await context.bot.delete_message(chat_id=CHANNEL_ID, message_id=channel_message_id)
        except Exception:
            log.warning("Could not delete message %s from channel", channel_message_id)

    with db() as conn:
        conn.execute("DELETE FROM accounts WHERE id = ? AND user = ?", (account_id, user_id))

    del_text = (
        f"🗑 <b>ھېساب #{account_id} مۇۋەپپەقىيەتلىك ئۆچۈرۈلدى!</b>\n\n"
        "✨ قانالدىكى ئېلانمۇ ئاپتوماتىك ئۆچۈرۈلدى."
    )
    if q.message.caption is not None:
        await q.edit_message_caption(caption=del_text, parse_mode="HTML", reply_markup=None)
    else:
        await q.edit_message_text(text=del_text, parse_mode="HTML", reply_markup=None)

async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("ئۆچۈرۈش بىكار قىلىندى.")
    account_id = int(q.data.split(":")[1])
    del_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 سېتىلدى / ئۆچۈرۈش", callback_data=f"delete:{account_id}")]
    ])
    await q.edit_message_reply_markup(reply_markup=del_keyboard)

# ----------------- Open Teams Display Helper -----------------
async def display_open_teams(target_message, context: ContextTypes.DEFAULT_TYPE):
    with db() as conn:
        rows = conn.execute("SELECT * FROM teams ORDER BY id DESC LIMIT 10").fetchall()

    if not rows:
        await target_message.reply_text(
            f"🔥 <b>ھازىرچە ئوچۇق كوماندىلار يوق.</b>\n\n"
            f"{EMOJI_CHECK} «🎮 كوماندا يىغىش» كۇنۇپكىسىنى بېسىپ ئۆزىڭىز كوماندا قۇرۇپ سەپداش تەكلىپ قىلسىڭىز بولىدۇ!",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
        return

    await target_message.reply_text(
        f"🔥 <b>نۆۋەتتىكى ئوچۇق كوماندىلار (ئەڭ يېڭى {len(rows)} تال):</b>",
        parse_mode="HTML",
    )
    for row in rows:
        user_display = f"@{row['username']}" if row['username'] else f"ID: {row['user']}"
        team_card = (
            f"🏆 <b>كوماندا #{row['id']}</b>\n"
            f"👥 <b>لازىملىق ئەزا:</b> <b>{row['count']} نەپەر</b>\n"
            f"🎯 <b>روللار:</b> {row['roles']}\n"
            f"👑 <b>كاپىتان:</b> {user_display}\n"
            f"📅 <b>ۋاقتى:</b> {row['created_at']}"
        )
        contact_kb = None
        if row["username"]:
            contact_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 كاپىتانغا ئۇچۇر يېزىش", url=f"https://t.me/{row['username']}")]
            ])
        await target_message.reply_text(team_card, parse_mode="HTML", reply_markup=contact_kb)

    await target_message.reply_text("✨ كوماندىغا قوشۇلۇش ئۈچۈن كاپىتان بىلەن ئالاقىلىشىڭ!", reply_markup=main_keyboard())

# ----------------- Team Recruitment Flow -----------------
async def begin_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["team"] = {"roles": []}
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ يېڭى كوماندا قۇرۇش", callback_data="team_act:new")],
        [InlineKeyboardButton("🔥 ئوچۇق كوماندىلارنى كۆرۈش", callback_data="team_act:open")],
    ])
    try:
        await update.message.reply_sticker(STICKER_LIGHTNING)
    except Exception:
        pass
    await update.message.reply_text(
        f"🎮 {EMOJI_TOP} <b>MLBB كوماندا ۋە سەپداشلار مەركىزى</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "بىرلىكتە Rank ئۆرلەيدىغان سەرخىل سەپداشلارنى تېپىڭ ياكى ئۆزىڭىز كوماندا تەشكىللەڭ!\n\n"
        "👇 <i>تۆۋەندىكى تۈرلەردىن بىرنى تاللاڭ:</i>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    return TEAM_ACTION

async def team_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    act = q.data.split(":")[1]
    if act == "open":
        await q.edit_message_reply_markup(reply_markup=None)
        await display_open_teams(q.message, context)
        return ConversationHandler.END
    elif act == "new":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 1 نەپەر سەپداش", callback_data="count:1"),
             InlineKeyboardButton("👥 2 نەپەر سەپداش", callback_data="count:2")],
            [InlineKeyboardButton("⚔️ 3 نەپەر سەپداش", callback_data="count:3"),
             InlineKeyboardButton("🔥 4 نەپەر سەپداش", callback_data="count:4")],
        ])
        await q.edit_message_text(
            "⚔️ <b>كوماندا ئۈچۈن قانچە سەپداش لازىم؟</b>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return TEAM_COUNT

async def team_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    count = int(q.data.split(":")[1])
    context.user_data["team"]["count"] = count
    context.user_data["team"]["roles"] = []
    await q.edit_message_reply_markup(reply_markup=None)
    await show_role_keyboard(q.message, context, count)
    return TEAM_ROLES

async def show_role_keyboard(message, context, count):
    selected = context.user_data["team"]["roles"]
    rows = []
    role_order = ["mage", "jungle", "marksman", "tank", "exp"]
    for role in role_order:
        mark = "✅ " if role in selected else "▫️ "
        rows.append([InlineKeyboardButton(
            mark + ROLE_NAMES[role],
            callback_data=f"role:{role}",
        )])
    rows.append([InlineKeyboardButton("🔄 تاللاشنى قايتا تازىلاش", callback_data="role_reset")])
    await message.reply_text(
        f"🎯 <b>دەل {count} رولنى تاللاڭ:</b> (ھازىر: {len(selected)}/{count})",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML",
    )

async def team_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    team = context.user_data["team"]
    selected = team["roles"]
    if q.data == "role_reset":
        selected.clear()
        await q.edit_message_reply_markup(reply_markup=None)
        await show_role_keyboard(q.message, context, team["count"])
        return TEAM_ROLES

    role = q.data.split(":")[1]
    if role in selected:
        selected.remove(role)
    elif len(selected) < team["count"]:
        selected.append(role)
    else:
        await q.answer(f"⚠️ پەقەت {team['count']} روللا تاللىيالايسىز.", show_alert=True)
        return TEAM_ROLES

    if len(selected) == team["count"]:
        names = [ROLE_NAMES[x] for x in selected]
        user = q.from_user
        username = f"@{user.username}" if user.username else f"ID: <code>{user.id}</code>"
        roles_text = " • ".join(names)

        post = (
            f"╔═══════════════════════╗\n"
            f"  {EMOJI_STAR} <b>MLBB سەپداش تەكلىپى</b> {EMOJI_STAR}\n"
            f"╚═══════════════════════╝\n\n"
            f"{EMOJI_USER} <b>كېرەكلىك ئەزا:</b> <b>{team['count']} نەپەر</b> 🔥\n"
            f"{EMOJI_CHECK} <b>تەلەپ قىلىنغان روللار:</b>\n" + "\n".join([f"  {EMOJI_ARROW} {name}" for name in names]) + "\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{EMOJI_TOP} <b>تەشكىللىگۈچى (Leader):</b> {username}\n"
            f"⚡ <i>بىرلىكتە غەلىبە قازىنىدىغان سەپداشلار دەرھال ئالاقىلىشىڭلار!</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>ئېلان سۇپىسى:</b> @mlbb_uy_players_bot"
        )
        channel_msg_id = None
        try:
            try:
                await context.bot.send_sticker(chat_id=CHANNEL_ID, sticker=STICKER_LIGHTNING)
            except Exception:
                pass
            sent = await context.bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode="HTML")
            channel_msg_id = sent.message_id
            await q.edit_message_text(
                f"✅ <b>كوماندا ئېلانى قانالغا يوللاندى!</b>\n👥 كىشى: {team['count']}\n🎯 روللار: {', '.join(names)}",
                parse_mode="HTML",
            )
        except Exception:
            log.exception("Could not publish team post")
            await q.edit_message_text("❌ قانالغا يوللاش مەغلۇپ بولدى. قانال ID ۋە بوت ھوقۇقىنى تەكشۈرۈڭ.")

        with db() as conn:
            conn.execute("""
                INSERT INTO teams (user, username, count, roles, channel_message_id)
                VALUES (?, ?, ?, ?, ?)
            """, (user.id, user.username or "", team["count"], roles_text, channel_msg_id))

        context.user_data.pop("team", None)
        return ConversationHandler.END

    await q.edit_message_reply_markup(reply_markup=None)
    await show_role_keyboard(q.message, context, team["count"])
    return TEAM_ROLES

# ----------------- Open Teams (Direct) -----------------
async def open_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await display_open_teams(update.message, context)

# ----------------- Notifications, Invite, Info -----------------
async def notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"🔔 {EMOJI_RED_DOT} <b>سۇپا ئۇقتۇرۇشلىرى ۋە بىخەتەرلىك ئەسكەرتىشى</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛡 <b>ھېساب سودىسىدا دىققەت قىلىدىغان مۇھىم نۇقتىلار:</b>\n\n"
        f"1️⃣ <b>مەخپىيلىكنى قوغداش:</b>\n"
        f"ھېسابىڭىزنىڭ مەخپىي شىفىرى (Password)، ئېلخەت ياكى تېلېفون كودىنى ھەرگىز ناتونۇشلارغا بەرمەڭ!\n\n"
        f"2️⃣ <b>ئىشەنچلىك ئوتتۇرىچى:</b>\n"
        f"{EMOJI_CARD} پۇل ۋە ھېساب بىخەتەرلىكى ئۈچۈن، ئىشەنچلىك قانال باشقۇرغۇچىسى ئارقىلىق سودا قىلىڭ.\n\n"
        f"3️⃣ <b>باغلىنىشلارنى تەكشۈرۈش:</b>\n"
        f"{EMOJI_CHECK} ھېساب سېتىۋېلىشتىن بۇرۇن Moonton، Google، FB قاتارلىق باغلىنىشلىرىنى ئېنىقلاڭ.\n\n"
        f"4️⃣ <b>رەسمىي سۇپا:</b>\n"
        f"{EMOJI_USER} بارلىق سەرخىل ھېسابلار ۋە كوماندا تەكلىپلىرى سۇپىمىزدا ئاپتوماتىك ئېلان قىلىنىدۇ.\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📢 <i>سوئال-پىكىرلىرىڭىز بولسا باشقۇرغۇچىغا ئىنكاس قالدۇرۇڭ!</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username or "mlbb_uy_players_bot"
    invite_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = "🎮 MLBB سەرخىل سەپداشلار ۋە ھېساب بازىرىغا قوشۇلۇڭ!"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text={urllib.parse.quote(share_text)}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 تېلېگراممىدا دوستلارغا ھەمبەھىرلەش", url=share_url)],
    ])

    text = (
        f"{EMOJI_USER} <b>دوستلارنى تەكلىپ قىلىش</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 دوستلىرىڭىزنى <b>MLBB UYGHUR PLAYERS</b> سۇپىسىغا تەكلىپ قىلىڭ!\n\n"
        f"{EMOJI_CHECK} كۈچلۈك سەپداشلار بىلەن بىرلىكتە دەرىجە ئۆرلەش ئەڭ قولايلىق!\n"
        f"{EMOJI_CARD} ھېسابنى بىخەتەر سېتىش ۋە ئالماشتۇرۇش مۇھىتى بار.\n\n"
        f"🔗 <b>سىزنىڭ شەخسىي تەكلىپ ئۇلانمىڭىز:</b>\n"
        f"<code>{invite_link}</code>\n\n"
        "👇 <i>تۆۋەندىكى كۇنۇپكىنى بېسىپ دوستلىرىڭىزغا ھەمبەھىرلەڭ:</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"ℹ️ {EMOJI_RED_DOT} <b>MLBB UYGHUR PLAYERS سۇپىسى ھەققىدە</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 <b>مەقسىتىمىز:</b>\n"
        f"Mobile Legends: Bang Bang (MLBB) ئۇيغۇر ئوينىغۇچىلىرىغا يۇقىرى سۈپەتلىك، كۆركەم، تېز ۋە ئىشەنچلىك سەپداش تېپىش ھەم ھېساب ئالماشتۇرۇش مۇھىتى يارىتىپ بېرىش.\n\n"
        f"{EMOJI_USER} <b>رەسمىي مۇلازىمەت بوتى:</b> @mlbb_uy_players_bot\n"
        f"{EMOJI_CHECK} <b>سىستېما نەشرى:</b> v3.0 Ultimate\n"
        f"⚡ <b>تېخنىكىلىق قوللاش:</b> بارلىق مەشغۇلاتلار تولۇق ئاپتوماتلاشقان.\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <i>ئويۇندا ۋە تۇرمۇشتا غەلىبە سىزگە يار بولسۇن!</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJI_DOWN} <i>تۆۋەندىكى كۇنۇپكىلاردىن بىرنى تاللاڭ:</i>",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

def main():
    if not TOKEN or not CHANNEL_ID:
        raise RuntimeError("BOT_TOKEN ۋە CHANNEL_ID نى .env ھۆججىتىگە كىرگۈزۈڭ.")
    init_db()
    app = Application.builder().token(TOKEN).build()

    CANCEL_HANDLER = MessageHandler(filters.Regex(r"(?i)(توختىتىش|بىكار|cancel|❌)"), cancel)

    account_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^(📲|💎\s*📤|📤)?\s*ھېساب\s*(يوللاش|سېتىش)$"), begin_account)],
        states={
            UID: [CANCEL_HANDLER, MessageHandler(filters.TEXT & ~filters.COMMAND, get_uid)],
            SERVER: [CANCEL_HANDLER, MessageHandler(filters.TEXT & ~filters.COMMAND, get_server)],
            RANK: [CANCEL_HANDLER, MessageHandler(filters.TEXT & ~filters.COMMAND, get_rank)],
            PRICE: [CANCEL_HANDLER, MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            DESC: [CANCEL_HANDLER, MessageHandler(filters.TEXT & ~filters.COMMAND, get_desc)],
            PHOTO: [
                CANCEL_HANDLER,
                CallbackQueryHandler(skip_photo, pattern="^skip_photo$"),
                MessageHandler(filters.PHOTO, get_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, photo_text_fallback),
            ],
        },
        fallbacks=[
            CANCEL_HANDLER,
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )

    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^(🔎|🔍\s*⚡|🔍)?\s*ھېساب\s*ئىزدەش$"), begin_search)],
        states={
            SEARCH_QUERY: [CANCEL_HANDLER, MessageHandler(filters.TEXT & ~filters.COMMAND, search_query)],
        },
        fallbacks=[
            CANCEL_HANDLER,
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )

    team_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^(🎮|⚔️\s*👥|👥)?\s*كوماندا\s*يىغىش$"), begin_team)],
        states={
            TEAM_ACTION: [
                CANCEL_HANDLER,
                CallbackQueryHandler(team_action, pattern="^team_act:(new|open)$")
            ],
            TEAM_COUNT: [
                CANCEL_HANDLER,
                CallbackQueryHandler(team_count, pattern="^count:[1-4]$")
            ],
            TEAM_ROLES: [
                CANCEL_HANDLER,
                CallbackQueryHandler(team_role, pattern="^(role:(mage|jungle|marksman|tank|exp)|role_reset)$")
            ],
        },
        fallbacks=[
            CANCEL_HANDLER,
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(account_conv)
    app.add_handler(search_conv)
    app.add_handler(team_conv)

    # My Accounts & Delete
    app.add_handler(MessageHandler(filters.Regex(r"^(📋)?\s*مېنىڭ\s*ھېسابلىرىم$"), my_accounts))
    app.add_handler(CallbackQueryHandler(delete_confirm, pattern=r"^delete:\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern=r"^confirm_delete:\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_delete, pattern=r"^cancel_delete:\d+$"))

    # Open Teams (Direct)
    app.add_handler(MessageHandler(filters.Regex(r"^(🔥)?\s*ئوچۇق\s*كوماندىلار$"), open_teams))

    # Other Menu Handlers
    app.add_handler(MessageHandler(filters.Regex(r"^(🔔)?\s*ئۇقتۇرۇشلار$"), notify))
    app.add_handler(MessageHandler(filters.Regex(r"^(👥)?\s*دوست\s*تەكلىپ\s*قىلىش$"), invite))
    app.add_handler(MessageHandler(filters.Regex(r"^(ℹ️)?\s*ئۇچۇر$"), info))

    app.add_handler(CANCEL_HANDLER)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    log.info("MLBB Telegram bot started")
    app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    main()
