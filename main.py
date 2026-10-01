import os
import logging
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

# Telethon Konfiguratsiyasi (O'zgaruvchilar ishlatilishidan oldin e'lon qilindi)
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
import pymysql

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

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    logger.info("Bot muvaffaqiyatli ishga tushdi...")
