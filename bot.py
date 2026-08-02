import os
import uuid
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import init_db_pool, get_db_pool, close_db_pool

load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

async def register_user(user):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE 
            SET username = EXCLUDED.username, first_name = EXCLUDED.first_name;
        """, user.id, user.username, user.first_name)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await register_user(user)

    keyboard = [
        [InlineKeyboardButton("🎮 لعب ضد الكمبيوتر (AI)", callback_query_data="mode_ai")],
        [InlineKeyboardButton("⚔️ تحدي صديق (PvP)", callback_query_data="mode_pvp")],
        [InlineKeyboardButton("🏆 الترتيب والإحصائيات", callback_query_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"أهلاً بك يا {user.first_name} في بوت الشطرنج الاحترافي! ♟️\nاختر نمط اللعب للبدء:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data == "mode_ai":
        keyboard = [
            [InlineKeyboardButton("سهل 🟢", callback_data="ai_1"), InlineKeyboardButton("متوسط 🟡", callback_data="ai_2")],
            [InlineKeyboardButton("صعب 🔴", callback_data="ai_3")]
        ]
        await query.edit_message_text("اختر مستوى صعوبة الذكاء الاصطناعي:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("ai_"):
        difficulty = int(data.split("_")[1])
        game_id = str(uuid.uuid4())
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO games (game_id, white_player_id, fen, game_mode, difficulty)
                VALUES ($1, $2, 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'ai', $3);
            """, game_id, user.id, difficulty)

        play_url = f"{WEBAPP_URL}?game_id={game_id}&user_id={user.id}"
        keyboard = [[InlineKeyboardButton("♟️ فتح اللوحة والتحدي", web_app=WebAppInfo(url=play_url))]]
        await query.edit_message_text("تمت إنشاء المباراة! اضغط زر الأسفل للبدء:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "stats":
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            stats = await conn.fetchrow("SELECT rating, wins, losses, draws FROM users WHERE user_id = $1", user.id)
            if stats:
                msg = f"📊 **إحصائياتك يا {user.first_name}:**\n\n" \
                      f"⭐ التقييم: {stats['rating']}\n" \
                      f"🥇 الانتصارات: {stats['wins']}\n" \
                      f"💔 الهزائم: {stats['losses']}\n" \
                      f"🤝 التعادلات: {stats['draws']}"
            else:
                msg = "لم يتم العثور على بيانات."
        await query.edit_message_text(msg, parse_mode="Markdown")

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db_pool())

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    logging.info("البوت يعمل بنجاح...")
    application.run_polling()

if __name__ == "__main__":
    main()
