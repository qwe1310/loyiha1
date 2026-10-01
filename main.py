import os
import asyncio
import logging
import pymysql
from aiohttp import web
from telethon import TelegramClient

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
API_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

TELETHON_API_ID = int(os.getenv("TELETHON_API_ID", "0"))
TELETHON_API_HASH = os.getenv("TELETHON_API_HASH", "")

if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN Environment Variable sozlanmagan!")

if not TELETHON_API_ID or not TELETHON_API_HASH:
    raise RuntimeError("TELETHON_API_ID va TELETHON_API_HASH Environment Variables sozlanmagan!")

ADMIN_ID = 6225462652
ADMIN_USERNAME = "@uktmvch16"
BOT_USERNAME_LOGIN = "@DynastyDonat_bot"

# MySQL Konfiguratsiyasi
MYSQL_CONFIG = {
    'host': os.getenv("MYSQL_HOST", "localhost"),
    'port': int(os.getenv("MYSQL_PORT", "3306")),
    'user': os.getenv("MYSQL_USER", "nomerbot"),
    'password': os.getenv("MYSQL_PASSWORD", ""),
    'db': os.getenv("MYSQL_DATABASE", "nomerbot"),
    'charset': 'utf8mb4',
    'autocommit': True
}

# ==================== DATABASE FUNCTIONS ====================
def get_db_connection():
    try:
        return pymysql.connect(**MYSQL_CONFIG)
    except Exception as e:
        logger.error(f"Ma'lumotlar bazasiga ulanishda xatolik: {e}")
        return None

def update_balance(user_id, amount):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE users SET balance = balance + %s WHERE user_id = %s"
            cursor.execute(sql, (amount, user_id))
        return True
    except Exception as e:
        logger.error(f"Balansni yangilashda xatolik (User ID: {user_id}): {e}")
        return False
    finally:
        conn.close()

# ==================== DUMMY WEB SERVER (Render uchun) ====================
async def handle_ping(request):
    return web.Response(text="Bot is running active!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Dummy Web-Server {PORT}-portda ishga tushdi.")

# ==================== MAIN EXECUTION ====================
async def main():
    logger.info("Bot muvaffaqiyatli ishga tushdi...")
    
    # Render o'chirib qo'ymasligi uchun fon veb-serverini ishga tushiramiz
    await start_web_server()

    # Telethon mijozini ishga tushirish (agar seans fayli yoki bot token ishlatilsa)
    client = TelegramClient('bot_session', TELETHON_API_ID, TELETHON_API_HASH)
    await client.start(bot_token=API_TOKEN)
    
    logger.info("Telethon mijozi muvaffaqiyatli ulashda...")
    
    # Dasturni to'xtamasdan ushlab turish uchun doimiy sikl
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
