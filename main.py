import asyncio
import csv
import os
import json
import re
import random
import string
import shutil
import aiomysql
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, FSInputFile, CallbackQuery
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.network import ConnectionTcpFull
from contextlib import asynccontextmanager
import hashlib
import socks
from aiohttp import web

# ==================== CONFIGURATION ====================
API_TOKEN = os.getenv("API_TOKEN", "8979163459:AAFc5FJGlMTPW72SKdrFsMrfzJ18bjW6zRA")
ADMIN_ID = int(os.getenv("ADMIN_ID", "670059053"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@lock_support")
BOT_USERNAME_LOGIN = os.getenv("BOT_USERNAME_LOGIN", "@lock_numberbot")

# MySQL Configuration
MYSQL_CONFIG = {
    'host': os.getenv("MYSQL_HOST", "localhost"),
    'port': int(os.getenv("MYSQL_PORT", "3306")),
    'user': os.getenv("MYSQL_USER", "nomerbot"),
    'password': os.getenv("MYSQL_PASSWORD", "saidakbar0044@"),
    'db': os.getenv("MYSQL_DB", "nomerbot"),
    'charset': 'utf8mb4',
    'autocommit': True,
    'pool_recycle': 3600
}

# Telethon Configuration
TELETHON_API_ID = int(os.getenv("TELETHON_API_ID", "39187658"))
TELETHON_API_HASH = os.getenv("TELETHON_API_HASH", "4046fb5177b0701a33a73076b8a213aa")

# File paths
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "sessions")

# Constants
MIN_DEPOSIT = 2000
MIN_WITHDRAW = 1500
FEE_PERCENT = 0
MAX_ACCOUNTS_PER_PROXY = 50

# ==================== PROXY CONFIGURATION ====================
PROXY_LIST = [
    {'id': 1, 'ip': '213.139.192.47', 'port': 63203, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 63202},
    {'id': 2, 'ip': '45.149.81.230', 'port': 63455, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 63454},
    {'id': 3, 'ip': '2.56.139.216', 'port': 62523, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 62522},
    {'id': 4, 'ip': '194.59.12.44', 'port': 62785, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 62784},
    {'id': 5, 'ip': '45.149.80.107', 'port': 62581, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 62580},
    {'id': 6, 'ip': '109.94.218.139', 'port': 63747, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 63746},
    {'id': 7, 'ip': '193.176.23.234', 'port': 62885, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 62884},
    {'id': 8, 'ip': '155.212.125.199', 'port': 63217, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 63216},
    {'id': 9, 'ip': '45.137.155.110', 'port': 63869, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 63868},
    {'id': 10, 'ip': '141.133.85.158', 'port': 64413, 'login': 'iujy3iVc', 'password': '19QGu9mj', 'http_port': 64412}
]

# ==================== BOT INITIALIZATION ====================
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# ==================== DATABASE CONNECTION POOL ====================
class DatabasePool:
    _pool = None
    
    @classmethod
    async def get_pool(cls):
        if cls._pool is None:
            cls._pool = await aiomysql.create_pool(**MYSQL_CONFIG)
        return cls._pool
    
    @classmethod
    async def close_pool(cls):
        if cls._pool:
            cls._pool.close()
            await cls._pool.wait_closed()

@asynccontextmanager
async def get_db():
    pool = await DatabasePool.get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            try:
                await cur.execute("SET NAMES utf8mb4")
                await cur.execute("SET CHARACTER SET utf8mb4")
                await cur.execute("SET character_set_connection=utf8mb4")
            except:
                pass
            yield cur, conn

# ==================== STATES ====================
class AdminStates(StatesGroup):
    wait_country_name = State()
    wait_country_price = State()
    wait_user_id = State()
    wait_user_balance = State()
    wait_user_withdraw = State()
    wait_payment_card = State()
    wait_payment_owner = State()
    wait_sell_country = State()
    wait_sell_phone = State()
    wait_sell_code = State()
    wait_sell_2fa = State()
    wait_edit_country_select = State()
    wait_edit_country_name = State()
    wait_edit_country_price = State()

class DepositStates(StatesGroup):
    wait_amount = State()
    wait_receipt = State()

class WithdrawStates(StatesGroup):
    wait_amount = State()
    wait_card_or_phone = State()

# ==================== PROXY MANAGER ====================
class ProxyManager:
    def __init__(self):
        self.proxies = PROXY_LIST
        self.usage_cache = {}
        self.cache_time = {}
        self.cache_ttl = 30
    
    async def get_proxy_usage(self, proxy_id: int) -> int:
        now = datetime.now()
        if proxy_id in self.usage_cache and proxy_id in self.cache_time:
            if (now - self.cache_time[proxy_id]).total_seconds() < self.cache_ttl:
                return self.usage_cache[proxy_id]
        
        async with get_db() as (cur, conn):
            await cur.execute(
                "SELECT COUNT(*) as count FROM phone_numbers WHERE proxy_id = %s AND status = 'available'",
                (proxy_id,)
            )
            result = await cur.fetchone()
            count = result['count'] if result else 0
        
        self.usage_cache[proxy_id] = count
        self.cache_time[proxy_id] = now
        return count
    
    async def get_available_proxy(self) -> dict:
        available_proxies = []
        for proxy in self.proxies:
            usage = await self.get_proxy_usage(proxy['id'])
            if usage < MAX_ACCOUNTS_PER_PROXY:
                available_proxies.append((proxy, usage))
        
        if not available_proxies:
            return None
        
        proxy, usage = random.choice(available_proxies)
        return {
            'proxy': proxy,
            'current_usage': usage,
            'remaining': MAX_ACCOUNTS_PER_PROXY - usage
        }
    
    def get_proxy_config(self, proxy_id: int) -> dict:
        for proxy in self.proxies:
            if proxy['id'] == proxy_id:
                return proxy
        return None
    
    def create_proxy_client(self, proxy_config: dict) -> tuple:
        if not proxy_config:
            return None
        proxy = (socks.SOCKS5, proxy_config['ip'], proxy_config['port'],
                 True, proxy_config['login'], proxy_config['password'])
        return proxy
    
    async def clear_cache(self, proxy_id: int = None):
        if proxy_id:
            self.usage_cache.pop(proxy_id, None)
            self.cache_time.pop(proxy_id, None)
        else:
            self.usage_cache.clear()
            self.cache_time.clear()

proxy_manager = ProxyManager()

# ==================== MAIN MENU ====================
def get_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📞 Nomer olish"), KeyboardButton(text="💰 Hisobim")],
        [KeyboardButton(text="🛒 Xaridlarim"), KeyboardButton(text="💳 Hisob to'ldirish")],
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️️ Admin panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕹 Raqam sotish", callback_data="admin_sell_number")],
        [InlineKeyboardButton(text="🌐 Davlatlarni sozlash", callback_data="admin_countries")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🪪 Foydalanuvchi", callback_data="admin_user")],
        [InlineKeyboardButton(text="💳 To'lov sozlamalari ⚙️", callback_data="admin_payment")],
        [InlineKeyboardButton(text="📡 Proxy status", callback_data="admin_proxy_status")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_admin")]
    ])

# ==================== HELPER FUNCTIONS ====================
async def get_or_create_user(user_id: int, fullname: str = None, username: str = None):
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = await cur.fetchone()
        if not user:
            await cur.execute(
                "INSERT INTO users (user_id, fullname, username) VALUES (%s, %s, %s)",
                (user_id, fullname, username)
            )
            await conn.commit()
            return {'user_id': user_id, 'fullname': fullname, 'username': username,
                    'purchase_balance': 0, 'withdraw_balance': 0, 'total_purchased': 0}
        return user

async def get_user_balance(user_id: int) -> dict:
    async with get_db() as (cur, conn):
        await cur.execute(
            "SELECT purchase_balance, withdraw_balance FROM users WHERE user_id = %s",
            (user_id,)
        )
        result = await cur.fetchone()
        if result:
            return {'purchase': result['purchase_balance'], 'withdraw': result['withdraw_balance']}
        return {'purchase': 0, 'withdraw': 0}

async def update_balance(user_id: int, amount: int, balance_type: str = 'purchase'):
    async with get_db() as (cur, conn):
        if balance_type == 'purchase':
            await cur.execute(
                "UPDATE users SET purchase_balance = purchase_balance + %s WHERE user_id = %s",
                (amount, user_id)
            )
        else:
            await cur.execute(
                "UPDATE users SET withdraw_balance = withdraw_balance + %s WHERE user_id = %s",
                (amount, user_id)
            )
        await conn.commit()

async def get_countries_with_stats():
    async with get_db() as (cur, conn):
        await cur.execute("""
            SELECT c.*, 
                   COUNT(CASE WHEN p.status = 'available' THEN 1 END) as available_count,
                   COALESCE(c.price, 0) as price
            FROM countries c
            LEFT JOIN phone_numbers p ON c.code = p.country_code AND p.status = 'available'
            GROUP BY c.code, c.name, c.phone_prefix, c.price
            ORDER BY c.name
        """)
        return await cur.fetchall()

async def generate_random_password():
    length = random.randint(8, 12)
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(random.choices(chars, k=length))
        if (any(c.islower() for c in password) and
            any(c.isupper() for c in password) and
            any(c.isdigit() for c in password) and
            any(c in "!@#$%^&*" for c in password)):
            return password

async def create_session_folder(session_id: str) -> str:
    folder_path = os.path.join(SESSIONS_DIR, session_id)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

async def save_session_file(session_string: str, session_id: str):
    folder_path = await create_session_folder(session_id)
    filepath = os.path.join(folder_path, "connect.session")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(session_string)
    return filepath

async def read_session_file(session_id: str):
    filepath = os.path.join(SESSIONS_DIR, session_id, "connect.session")
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return None

async def delete_session_folder(session_id: str):
    folder_path = os.path.join(SESSIONS_DIR, session_id)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
        return True
    return False

async def notify_admin_new_sale(phone_data: dict, buyer_id: int, buyer_name: str):
    try:
        text = (
            f"✅ <b>Yangi raqam sotildi!</b>\n\n"
            f"📞 Raqam: <code>{phone_data['phone']}</code>\n"
            f"🌍 Davlat: {phone_data.get('country_name', 'Nomalum')}\n"
            f"💰 Narxi: {phone_data.get('price', 0):,} so'm\n"
            f"🔒 Parol: <code>{phone_data['password']}</code>\n"
            f"🆔 Sessiya ID: <code>{phone_data['session_id']}</code>\n\n"
            f"👤 Xaridor:\n"
            f"   ID: <code>{buyer_id}</code>\n"
            f"   Ism: {buyer_name}\n\n"
            f"📅 Sana: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        print(f"Admin notification error: {e}")

async def notify_admin_broken_session(phone_data: dict, refund_amount: int):
    try:
        buyer_id = phone_data.get('buyer_id', 'Nomalum')
        async with get_db() as (cur, conn):
            await cur.execute("SELECT * FROM users WHERE user_id = %s", (buyer_id,))
            user = await cur.fetchone()
        
        text = (
            f"⚠️ <b>Sessiya buzildi va pul qaytarildi!</b>\n\n"
            f"📞 Raqam: <code>{phone_data['phone']}</code>\n"
            f"🌍 Davlat: {phone_data.get('country_name', 'Nomalum')}\n"
            f"💰 Qaytarilgan summa: {refund_amount:,} so'm\n"
            f"🆔 Sessiya ID: <code>{phone_data.get('session_id', 'Nomalum')}</code>\n\n"
            f"👤 Foydalanuvchi:\n"
            f"   ID: <code>{buyer_id}</code>\n"
            f"   Ism: {user['fullname'] if user else 'Nomalum'}\n"
            f"   Username: @{user['username'] if user and user['username'] else 'yoq'}\n\n"
            f"📅 Sana: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        print(f"Admin broken session notification error: {e}")

async def refund_for_broken_session(phone_id: int, user_id: int):
    try:
        async with get_db() as (cur, conn):
            await cur.execute("""
                SELECT p.*, c.price as country_price, c.name as country_name
                FROM phone_numbers p
                JOIN countries c ON p.country_code = c.code
                WHERE p.id = %s
            """, (phone_id,))
            phone = await cur.fetchone()
            
            if phone and phone['buyer_id']:
                refund_amount = phone['country_price']
                await cur.execute(
                    "UPDATE users SET purchase_balance = purchase_balance + %s WHERE user_id = %s",
                    (refund_amount, phone['buyer_id'])
                )
                await conn.commit()
                await notify_admin_broken_session(phone, refund_amount)
                try:
                    await bot.send_message(
                        phone['buyer_id'],
                        f"⚠️ <b>Sessiya buzilganligi sababli pul qaytarildi!</b>\n\n"
                        f"📞 Raqam: <code>{phone['phone']}</code>\n"
                        f"💰 Qaytarilgan summa: {refund_amount:,} so'm\n\n"
                        f"Balansingizga pul qaytarildi."
                    )
                except:
                    pass
                return True
        return False
    except Exception as e:
        print(f"Refund error: {e}")
        return False

async def cleanup_broken_session(phone_id: int, session_id: str, proxy_id: int = None):
    try:
        await delete_session_folder(session_id)
        async with get_db() as (cur, conn):
            await cur.execute("DELETE FROM phone_numbers WHERE id = %s", (phone_id,))
            await conn.commit()
        if proxy_id:
            await proxy_manager.clear_cache(proxy_id)
        return True
    except Exception as e:
        print(f"Cleanup error: {e}")
        return False

async def fetch_code_from_session(session_id: str, user_id: int, proxy_id: int = None, phone_id: int = None):
    session_string = await read_session_file(session_id)
    
    if not session_string:
        if phone_id:
            await refund_for_broken_session(phone_id, user_id)
            await cleanup_broken_session(phone_id, session_id, proxy_id)
        return None, False, "Sessiya topilmadi va o'chirildi! Pulingiz qaytarildi."
    
    proxy_config = proxy_manager.get_proxy_config(proxy_id) if proxy_id else None
    proxy = proxy_manager.create_proxy_client(proxy_config) if proxy_config else None
    
    client = TelegramClient(
        StringSession(session_string), 
        TELETHON_API_ID, 
        TELETHON_API_HASH,
        proxy=proxy
    )
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            if phone_id:
                await refund_for_broken_session(phone_id, user_id)
                await cleanup_broken_session(phone_id, session_id, proxy_id)
            return None, False, "Sessiya ishlamay qolgan va o'chirildi! Pulingiz qaytarildi."
        
        messages = await client.get_messages(777000, limit=5)
        found_code = None
        
        for msg in messages:
            if msg.message and msg.date:
                code_match = re.search(r'(?:Login code:?\s*)(\d[\d\-\s]{4,8})', msg.message, re.IGNORECASE)
                if not code_match:
                    code_match = re.search(r'\b(\d{5,6})\b', msg.message)
                
                if code_match:
                    raw_code = code_match.group(1)
                    clean_code = re.sub(r'[^\d]', '', raw_code)
                    if 5 <= len(clean_code) <= 6:
                        found_code = clean_code
                        break
        
        await client.disconnect()
        
        if not found_code:
            return None, False, None
        
        if hasattr(dp, 'temp_purchases') and user_id in dp.temp_purchases:
            old_code = dp.temp_purchases[user_id].get('last_code', '')
            if found_code == old_code:
                return found_code, False, None
            else:
                dp.temp_purchases[user_id]['last_code'] = found_code
                return found_code, True, None
        else:
            if hasattr(dp, 'temp_purchases') and user_id in dp.temp_purchases:
                dp.temp_purchases[user_id]['last_code'] = found_code
            return found_code, True, None
        
    except errors.rpcerrorlist.AuthKeyDuplicatedError:
        try:
            await client.disconnect()
        except:
            pass
        if phone_id:
            await refund_for_broken_session(phone_id, user_id)
            await cleanup_broken_session(phone_id, session_id, proxy_id)
        return None, False, "Sessiya buzilgan va o'chirildi! Pulingiz qaytarildi."
    except Exception as e:
        try:
            await client.disconnect()
        except:
            pass
        error_str = str(e)
        if 'auth' in error_str.lower() or 'session' in error_str.lower() or 'key' in error_str.lower():
            if phone_id:
                await refund_for_broken_session(phone_id, user_id)
                await cleanup_broken_session(phone_id, session_id, proxy_id)
            return None, False, f"Sessiya xatosi va o'chirildi! Pulingiz qaytarildi. Xato: {error_str}"
        return None, False, error_str

async def send_code_result_message(chat_id: int, phone: str, password: str, code: str, is_new: bool, error: str, phone_id: int):
    if error:
        text = (
            f"❌ <b>Xatolik yuz berdi!</b>\n\n"
            f"Sabab: {error}\n\n"
            f"Admin bilan bog'laning: {ADMIN_USERNAME}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta urinish", callback_data=f"get_purchase_code:{phone_id}")],
            [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
        ])
    elif code is None:
        text = (
            f"❌ <b>Kod hali kelmagan!</b>\n\n"
            f"📞 Raqam: <code>{phone}</code>\n\n"
            f"🔒 <b>2-bosqich parol:</b> <code>{password}</code>\n\n"
            f"💡 Kod kelishi uchun iloji boricha Telegram ilovasidan kiring.\n"
            f"Kod kelgach, \"Qayta kod olish\" tugmasini bosing."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta kod olish", callback_data=f"refresh_purchase_code:{phone_id}")]
        ])
    elif not is_new:
        formatted_code = '-'.join(list(code))
        text = (
            f"❌ <b>Yangi kod hali kelmadi!</b>\n\n"
            f"📞 Raqam: <code>{phone}</code>\n"
            f"🔑 Joriy kod: <code>{formatted_code}</code>\n\n"
            f"🔒 <b>2-bosqich parol:</b> <code>{password}</code>\n\n"
            f"🔄 Yangi kod kelishi uchun Telegram ilovasida faollik kuting."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta kod olish", callback_data=f"refresh_purchase_code:{phone_id}")],
            [InlineKeyboardButton(text="✅ Akkauntni oldim", callback_data=f"confirm_purchase:{phone_id}")]
        ])
    else:
        formatted_code = '-'.join(list(code))
        text = (
            f"📞 <b>Raqam:</b> <code>{phone}</code>\n\n"
            f"🔑 <b>Kod:</b> <code>{formatted_code}</code>\n\n"
            f"🔒 <b>2-bosqich parol:</b> <code>{password}</code>\n\n"
            f"⚠️ <b>Eslatma:</b> \"Akkauntni oldim\" tugmasini bossangiz, "
            f"bot akkauntni tark etadi va sessiya o'chiriladi!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta kod olish", callback_data=f"refresh_purchase_code:{phone_id}")],
            [InlineKeyboardButton(text="✅ Akkauntni oldim", callback_data=f"confirm_purchase:{phone_id}")]
        ])
    
    await bot.send_message(chat_id, text, reply_markup=kb)

async def get_available_phone_by_country(country_code: str):
    async with get_db() as (cur, conn):
        await cur.execute(
            """SELECT * FROM phone_numbers 
               WHERE country_code = %s AND status = 'available' 
               ORDER BY RAND() LIMIT 1""",
            (country_code,)
        )
        return await cur.fetchone()

# ==================== START COMMAND ====================
@dp.message(Command("start"))
async def start_command(msg: Message):
    user = await get_or_create_user(msg.from_user.id, msg.from_user.full_name, msg.from_user.username)
    await msg.answer(
        f"👋 Xush kelibsiz, {msg.from_user.full_name}!\n\n"
        "📱 Bu bot orqali siz Telegram akkauntlarini sotib olishingiz mumkin.\n\n"
        "👇 Quyidagi menyudan kerakli bo'limni tanlang:",
        reply_markup=get_main_menu(msg.from_user.id)
    )

# ==================== CANCEL HANDLER ====================
@dp.callback_query(F.data == "cancel_admin")
async def cancel_admin_process(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if 'client' in data:
        try:
            client = data['client']
            await client.disconnect()
        except:
            pass
    if 'temp_session_id' in data:
        await delete_session_folder(data['temp_session_id'])
    
    await state.clear()
    await call.message.delete()
    await call.message.answer("❌ Jarayon bekor qilindi.", reply_markup=get_main_menu(call.from_user.id))
    await call.answer()

@dp.callback_query(F.data == "close_message")
async def close_message(call: CallbackQuery):
    await call.message.delete()
    await call.answer()

# ==================== ADMIN PANEL ====================
@dp.message(F.text == "⚙️ Admin panel")
async def admin_panel(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("⛔ Siz admin emassiz!")
        return
    await msg.answer(
        "⚙️ <b>Admin panel</b>\n\nKerakli bo'limni tanlang:",
        reply_markup=get_admin_menu()
    )

# ==================== ADMIN: PROXY STATUS ====================
@dp.callback_query(F.data == "admin_proxy_status")
async def admin_proxy_status(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    text = "📡 <b>Proxy holati:</b>\n\n"
    for proxy in PROXY_LIST:
        usage = await proxy_manager.get_proxy_usage(proxy['id'])
        remaining = MAX_ACCOUNTS_PER_PROXY - usage
        status_emoji = "🟢" if remaining > 0 else "🔴"
        text += (
            f"{status_emoji} <b>Proxy #{proxy['id']}</b>\n"
            f"   IP: <code>{proxy['ip']}:{proxy['port']}</code>\n"
            f"   Akkauntlar: {usage}/{MAX_ACCOUNTS_PER_PROXY}\n"
            f"   Bo'sh: {remaining} ta\n\n"
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

# ==================== ADMIN: STATISTIKA ====================
@dp.callback_query(F.data == "admin_stats")
async def admin_statistics(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    async with get_db() as (cur, conn):
        await cur.execute("SELECT COUNT(*) as total FROM users")
        total_users = (await cur.fetchone())['total']
        await cur.execute("SELECT SUM(purchase_balance) as total FROM users")
        total_balance = (await cur.fetchone())['total'] or 0
        await cur.execute("SELECT COUNT(*) as total FROM phone_numbers")
        total_phones = (await cur.fetchone())['total']
        await cur.execute("SELECT COUNT(*) as total FROM phone_numbers WHERE status = 'available'")
        available_phones = (await cur.fetchone())['total']
        await cur.execute("SELECT COUNT(*) as total FROM phone_numbers WHERE status = 'sold'")
        sold_phones = (await cur.fetchone())['total']
        await cur.execute("SELECT SUM(price) as total FROM phone_numbers WHERE status = 'sold'")
        total_sold_price = (await cur.fetchone())['total'] or 0
    
    text = (
        f"📊 <b>Bot statistikasi</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users}</b> ta\n"
        f"💰 Jami balans: <b>{total_balance:,}</b> so'm\n\n"
        f"📱 Jami raqamlar: <b>{total_phones}</b> ta\n"
        f"🟢 Sotuvda: <b>{available_phones}</b> ta\n"
        f"✅ Sotilgan: <b>{sold_phones}</b> ta\n\n"
        f"💵 Sotilgan raqamlar narxi: <b>{total_sold_price:,}</b> so'm"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    await call.message.edit_text(
        "⚙️ <b>Admin panel</b>\n\nKerakli bo'limni tanlang:",
        reply_markup=get_admin_menu()
    )
    await call.answer()

# ==================== ADMIN: DAVLATLARNI SOZLASH ====================
@dp.callback_query(F.data == "admin_countries")
async def admin_countries_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi qo'shish", callback_data="country_add")],
        [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="country_edit_list")],
        [InlineKeyboardButton(text="➖ O'chirish", callback_data="country_delete")],
        [InlineKeyboardButton(text="📋 Ro'yxat", callback_data="country_list")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])
    await call.message.edit_text("🌐 <b>Davlatlarni sozlash</b>\n\nKerakli amalni tanlang:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "country_add")
async def country_add_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    await call.message.edit_text(
        "🌐 Davlat nomini va bayrog'ini kiriting:\nMasalan: 🇺🇿 O'zbekiston",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.wait_country_name)
    await call.answer()

@dp.message(AdminStates.wait_country_name)
async def country_add_name(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    country_name = msg.text.strip()
    await state.update_data(country_name=country_name)
    await msg.answer(
        f"💰 <b>{country_name}</b> uchun narx kiriting (so'mda):\nMasalan: 8000",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.wait_country_price)

@dp.message(AdminStates.wait_country_price)
async def country_add_price(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    try:
        price = int(msg.text.strip().replace(',', '').replace(' ', ''))
        if price < 1000:
            raise ValueError()
    except:
        await msg.answer("❌ Noto'g'ri narx! Kamida 1000 so'm bo'lishi kerak.", reply_markup=get_cancel_keyboard())
        return
    
    data = await state.get_data()
    country_name = data['country_name']
    
    import uuid
    code = str(uuid.uuid4())[:5].upper()
    
    async with get_db() as (cur, conn):
        await cur.execute(
            "INSERT INTO countries (code, name, phone_prefix, price) VALUES (%s, %s, %s, %s)",
            (code, country_name, '+', price)
        )
        await conn.commit()
    
    await state.clear()
    await msg.answer(
        f"✅ <b>{country_name}</b> muvaffaqiyatli qo'shildi!\n💰 Narxi: {price:,} so'm\n🆔 Kodi: {code}",
        reply_markup=get_main_menu(ADMIN_ID)
    )

@dp.callback_query(F.data == "country_edit_list")
async def country_edit_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    countries = await get_countries_with_stats()
    if not countries:
        await call.answer("❌ Hech qanday davlat mavjud emas!", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for country in countries:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"✏️ {country['name']} - {country['price']:,} so'm",
                callback_data=f"country_edit_select:{country['code']}"
            )
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_countries")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")])
    
    await call.message.edit_text("✏️ <b>Davlatni tahrirlash</b>\n\nTahrirlamoqchi bo'lgan davlatni tanlang:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("country_edit_select:"))
async def country_edit_select(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    code = call.data.split(":")[1]
    
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM countries WHERE code = %s", (code,))
        country = await cur.fetchone()
    
    if not country:
        await call.answer("❌ Davlat topilmadi!", show_alert=True)
        return
    
    await state.update_data(edit_country_code=code, edit_country_name=country['name'], edit_country_price=country['price'])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Nomini o'zgartirish", callback_data="country_edit_name")],
        [InlineKeyboardButton(text="💰 Narxini o'zgartirish", callback_data="country_edit_price")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="country_edit_list")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])
    await call.message.edit_text(f"✏️ <b>{country['name']}</b> - {country['price']:,} so'm\n\nNimani tahrirlamoqchisiz?", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "country_edit_name")
async def country_edit_name_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    data = await state.get_data()
    await call.message.edit_text(
        f"📝 Yangi nom kiriting (bayroq emoji bilan):\n\nEski nom: {data.get('edit_country_name', 'Nomalum')}\n\nMasalan: 🇺🇿 O'zbekiston",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.wait_edit_country_name)
    await call.answer()

@dp.message(AdminStates.wait_edit_country_name)
async def country_edit_name_finish(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    new_name = msg.text.strip()
    data = await state.get_data()
    code = data['edit_country_code']
    
    async with get_db() as (cur, conn):
        await cur.execute("UPDATE countries SET name = %s WHERE code = %s", (new_name, code))
        await conn.commit()
    
    await state.clear()
    await msg.answer(f"✅ Davlat nomi yangilandi: <b>{new_name}</b>", reply_markup=get_main_menu(ADMIN_ID))

@dp.callback_query(F.data == "country_edit_price")
async def country_edit_price_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    data = await state.get_data()
    await call.message.edit_text(
        f"💰 Yangi narx kiriting (so'mda):\n\nEski narx: {data.get('edit_country_price', 0):,} so'm",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.wait_edit_country_price)
    await call.answer()

@dp.message(AdminStates.wait_edit_country_price)
async def country_edit_price_finish(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    try:
        new_price = int(msg.text.strip().replace(',', '').replace(' ', ''))
        if new_price < 1000:
            raise ValueError()
    except:
        await msg.answer("❌ Noto'g'ri narx! Kamida 1000 so'm bo'lishi kerak.", reply_markup=get_cancel_keyboard())
        return
    
    data = await state.get_data()
    code = data['edit_country_code']
    
    async with get_db() as (cur, conn):
        await cur.execute("UPDATE countries SET price = %s WHERE code = %s", (new_price, code))
        await cur.execute("UPDATE phone_numbers SET price = %s WHERE country_code = %s AND status = 'available'", (new_price, code))
        await conn.commit()
    
    await state.clear()
    await msg.answer(f"✅ Narx yangilandi: <b>{new_price:,} so'm</b>", reply_markup=get_main_menu(ADMIN_ID))

@dp.callback_query(F.data == "country_delete")
async def country_delete_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    countries = await get_countries_with_stats()
    if not countries:
        await call.answer("❌ Hech qanday davlat mavjud emas!", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for country in countries:
        if country['available_count'] == 0:
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ {country['name']} (0 ta raqam)", callback_data=f"country_delete_confirm:{country['code']}")])
        else:
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"🔒 {country['name']} ({country['available_count']} ta raqam)", callback_data="country_cant_delete")])
    
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_countries")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")])
    
    await call.message.edit_text("🗑 <b>Davlatni o'chirish</b>\n\nFaqat faol raqamlari bo'lmagan davlatlarni o'chira olasiz!\nO'chirmoqchi bo'lgan davlatni tanlang:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "country_cant_delete")
async def country_cant_delete(call: CallbackQuery):
    await call.answer("⚠️ Bu davlatda faol raqamlar mavjud! Avval ularni o'chiring.", show_alert=True)

@dp.callback_query(F.data.startswith("country_delete_confirm:"))
async def country_delete_confirm(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    code = call.data.split(":")[1]
    
    async with get_db() as (cur, conn):
        await cur.execute("DELETE FROM countries WHERE code = %s", (code,))
        await conn.commit()
    
    await call.answer("✅ Davlat o'chirildi!", show_alert=True)
    await country_delete_list(call)

@dp.callback_query(F.data == "country_list")
async def country_list_show(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    countries = await get_countries_with_stats()
    if not countries:
        text = "❌ Hech qanday davlat mavjud emas!"
    else:
        text = "📋 <b>Davlatlar ro'yxati:</b>\n\n"
        for i, country in enumerate(countries, 1):
            text += f"{i}. <b>{country['name']}</b>\n   💰 Narx: {country['price']:,} so'm\n   🟢 Faol raqamlar: {country['available_count']} ta\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_countries")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

# ==================== ADMIN: FOYDALANUVCHI BOSHQARUVI ====================
@dp.callback_query(F.data == "admin_user")
async def admin_user_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    await call.message.edit_text("👤 <b>Foydalanuvchi boshqaruvi</b>\n\nBoshqarmoqchi bo'lgan foydalanuvchi ID raqamini kiriting:", reply_markup=get_cancel_keyboard())
    await state.set_state(AdminStates.wait_user_id)
    await call.answer()

@dp.message(AdminStates.wait_user_id)
async def admin_user_show(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(msg.text.strip())
    except:
        await msg.answer("❌ Noto'g'ri ID! Raqam kiriting.", reply_markup=get_cancel_keyboard())
        return
    
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = await cur.fetchone()
    
    if not user:
        await msg.answer("❌ Bunday foydalanuvchi topilmadi!", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(edit_user_id=user_id)
    text = (
        f"👤 <b>Foydalanuvchi ma'lumotlari</b>\n\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"📛 Ism: {user['fullname']}\n"
        f"📱 Username: @{user['username'] or 'yoq'}\n\n"
        f"💰 Sotib olish balansi: {user['purchase_balance']:,} so'm\n"
        f"💵 Yechib olish balansi: {user['withdraw_balance']:,} so'm\n"
        f"🛒 Xaridlar: {user['total_purchased']} ta"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Balans qo'shish", callback_data="user_add_balance")],
        [InlineKeyboardButton(text="💸 Balansdan yechish", callback_data="user_sub_balance")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])
    await msg.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "user_add_balance")
async def user_add_balance_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    await call.message.edit_text("💰 Qo'shmoqchi bo'lgan summani kiriting (so'mda):", reply_markup=get_cancel_keyboard())
    await state.set_state(AdminStates.wait_user_balance)
    await call.answer()

@dp.callback_query(F.data == "user_sub_balance")
async def user_sub_balance_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    await call.message.edit_text("💸 Yechmoqchi bo'lgan summani kiriting (so'mda):", reply_markup=get_cancel_keyboard())
    await state.set_state(AdminStates.wait_user_withdraw)
    await call.answer()

@dp.message(AdminStates.wait_user_balance)
async def user_add_balance_finish(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(msg.text.strip().replace(',', '').replace(' ', ''))
        if amount <= 0:
            raise ValueError()
    except:
        await msg.answer("❌ Noto'g'ri summa!", reply_markup=get_cancel_keyboard())
        return
    
    data = await state.get_data()
    user_id = data.get('edit_user_id')
    await update_balance(user_id, amount, 'purchase')
    await state.clear()
    await msg.answer(f"✅ Foydalanuvchi (ID: {user_id}) balansiga {amount:,} so'm qo'shildi!", reply_markup=get_main_menu(ADMIN_ID))

@dp.message(AdminStates.wait_user_withdraw)
async def user_sub_balance_finish(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(msg.text.strip().replace(',', '').replace(' ', ''))
        if amount <= 0:
            raise ValueError()
    except:
        await msg.answer("❌ Noto'g'ri summa!", reply_markup=get_cancel_keyboard())
        return
    
    data = await state.get_data()
    user_id = data.get('edit_user_id')
    await update_balance(user_id, -amount, 'purchase')
    await state.clear()
    await msg.answer(f"✅ Foydalanuvchi (ID: {user_id}) balansidan {amount:,} so'm yechildi!", reply_markup=get_main_menu(ADMIN_ID))

# ==================== ADMIN: TO'LOV SOZLAMALARI ====================
@dp.callback_query(F.data == "admin_payment")
async def admin_payment_settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM payment_methods WHERE is_active = TRUE LIMIT 1")
        method = await cur.fetchone()
    
    if method:
        text = (
            "💳 <b>Joriy to'lov ma'lumotlari:</b>\n\n"
            f"💳 Karta raqami: <code>{method['card_number']}</code>\n"
            f"👤 Karta egasi: <b>{method['card_owner']}</b>\n\n"
            "O'zgartirish uchun quyidagi tugmani bosing:"
        )
    else:
        text = "💳 Hozircha to'lov ma'lumotlari qo'shilmagan."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="payment_edit")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "payment_edit")
async def payment_edit_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    await call.message.edit_text("💳 Yangi karta raqamini kiriting:\nMasalan: 8600123456789012", reply_markup=get_cancel_keyboard())
    await state.set_state(AdminStates.wait_payment_card)
    await call.answer()

@dp.message(AdminStates.wait_payment_card)
async def payment_edit_card(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    card_number = msg.text.strip()
    await state.update_data(card_number=card_number)
    await msg.answer("👤 Karta egasi ismini kiriting:\nMasalan: ALIYEV ALISHER", reply_markup=get_cancel_keyboard())
    await state.set_state(AdminStates.wait_payment_owner)

@dp.message(AdminStates.wait_payment_owner)
async def payment_edit_finish(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    async with get_db() as (cur, conn):
        await cur.execute("UPDATE payment_methods SET is_active = FALSE")
        await cur.execute(
            "INSERT INTO payment_methods (name, card_number, card_owner, is_active) VALUES (%s, %s, %s, TRUE)",
            ("To'lov kartasi", data['card_number'], msg.text.strip())
        )
        await conn.commit()
    
    await state.clear()
    await msg.answer(
        f"✅ To'lov ma'lumotlari yangilandi!\n\n💳 {data['card_number']}\n👤 {msg.text.strip()}",
        reply_markup=get_main_menu(ADMIN_ID)
    )

# ==================== ADMIN: RAQAM SOTISH ====================
@dp.callback_query(F.data == "admin_sell_number")
async def admin_sell_number_start(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    proxy_info = await proxy_manager.get_available_proxy()
    if not proxy_info:
        await call.answer("⚠️ Barcha proxylarda bo'sh joy qolmagan!\n\nIltimos, avval akkauntlarni soting yoki yangi proxy qo'shing.", show_alert=True)
        return
    
    countries = await get_countries_with_stats()
    if not countries:
        await call.answer("❌ Hech qanday davlat mavjud emas!", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for country in countries:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{country['name']} - {country['price']:,} so'm", callback_data=f"admin_sell_country:{country['code']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")])
    
    await call.message.edit_text(
        f"🕹 <b>Raqam sotish</b>\n\n"
        f"📡 Proxy holati:\n"
        f"   Bo'sh joy: {proxy_info['remaining']}/{MAX_ACCOUNTS_PER_PROXY}\n"
        f"   Proxy IP: {proxy_info['proxy']['ip']}\n\n"
        f"Qaysi davlat raqamini sotmoqchisiz?",
        reply_markup=kb
    )
    await call.answer()

@dp.callback_query(F.data.startswith("admin_sell_country:"))
async def admin_sell_get_phone(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    country_code = call.data.split(":")[1]
    proxy_info = await proxy_manager.get_available_proxy()
    if not proxy_info:
        await call.answer("⚠️ Proxylarda bo'sh joy qolmadi!", show_alert=True)
        return
    
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM countries WHERE code = %s", (country_code,))
        country = await cur.fetchone()
    
    await state.update_data(
        country_code=country_code, 
        country_name=country['name'],
        proxy_id=proxy_info['proxy']['id'],
        proxy_ip=proxy_info['proxy']['ip']
    )
    
    await call.message.edit_text(
        f"📱 <b>{country['name']}</b> uchun raqamni yuboring:\n\nFormat: +998901234567\n\n📡 Proxy: {proxy_info['proxy']['ip']}",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.wait_sell_phone)
    await call.answer()

@dp.message(AdminStates.wait_sell_phone)
async def admin_sell_send_code(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    phone = msg.text.strip().replace(' ', '')
    if not phone.startswith('+') or not re.match(r'^\+\d+$', phone):
        await msg.answer("❌ Noto'g'ri format! + bilan boshlanib, faqat raqamlar bo'lishi kerak.", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(phone=phone)
    data = await state.get_data()
    proxy_config = proxy_manager.get_proxy_config(data['proxy_id'])
    proxy = proxy_manager.create_proxy_client(proxy_config) if proxy_config else None
    
    wait_msg = await msg.answer(f"⏳ Kod yuborilmoqda... (Proxy: {proxy_config['ip']})")
    
    client = TelegramClient(StringSession(), TELETHON_API_ID, TELETHON_API_HASH, proxy=proxy)
    try:
        await client.connect()
        sent_code = await client.send_code_request(phone)
        
        import uuid
        temp_session_id = str(uuid.uuid4())
        session_string = client.session.save()
        
        folder_path = await create_session_folder(temp_session_id)
        filepath = os.path.join(folder_path, "connect.session")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(session_string)
        
        await state.update_data(
            client=client,
            phone_code_hash=sent_code.phone_code_hash,
            temp_session_id=temp_session_id
        )
        
        await wait_msg.edit_text(
            f"✅ Kod yuborildi!\n\n📱 {phone}\n📡 Proxy: {proxy_config['ip']}\n\nKodni 8-8-8-8-8 formatida yuboring:",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.wait_sell_code)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {str(e)}\n\nQaytadan urinib ko'ring.", reply_markup=get_cancel_keyboard())
        await client.disconnect()

@dp.message(AdminStates.wait_sell_code)
async def admin_sell_verify_code(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    code_input = msg.text.strip()
    code_clean = code_input.replace('-', '').replace(' ', '')
    
    if not code_clean.isdigit():
        await msg.answer("❌ Kod faqat raqamlardan iborat bo'lishi kerak!", reply_markup=get_cancel_keyboard())
        return
    
    data = await state.get_data()
    client = data.get("client")
    phone = data.get("phone")
    phone_code_hash = data.get("phone_code_hash")
    
    try:
        await client.sign_in(phone, code_clean, phone_code_hash=phone_code_hash)
        has_2fa = False
        try:
            await client.get_me()
        except errors.SessionPasswordNeededError:
            has_2fa = True
        
        if has_2fa:
            await msg.answer("🔐 Bu akkauntda 2-bosqichli parol mavjud!\n\nIltimos, 2FA parolini kiriting:", reply_markup=get_cancel_keyboard())
            await state.set_state(AdminStates.wait_sell_2fa)
            return
        
        await setup_2fa_and_save(client, phone, data, msg, state)
    except errors.SessionPasswordNeededError:
        await msg.answer("🔐 2FA parolini kiriting:", reply_markup=get_cancel_keyboard())
        await state.set_state(AdminStates.wait_sell_2fa)
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {str(e)}", reply_markup=get_cancel_keyboard())
        await client.disconnect()
        await state.clear()

@dp.message(AdminStates.wait_sell_2fa)
async def admin_sell_verify_2fa(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    password_2fa = msg.text.strip()
    data = await state.get_data()
    client = data.get("client")
    phone = data.get("phone")
    
    try:
        await client.sign_in(password=password_2fa)
        await setup_2fa_and_save(client, phone, data, msg, state)
    except Exception as e:
        await msg.answer(f"❌ Noto'g'ri parol! Qaytadan kiriting:", reply_markup=get_cancel_keyboard())

async def setup_2fa_and_save(client, phone, data, msg_or_call, state):
    new_password = await generate_random_password()
    try:
        try:
            await client.delete_dialog(777000)
        except Exception as e:
            print(f"⚠️ Chat tozalashda xatolik: {e}")
        
        try:
            await client.edit_2fa(new_password=new_password)
        except Exception as e:
            print(f"⚠️️ 2FA o'rnatishda xatolik: {e}")
        
        session_string = client.session.save()
        import uuid
        session_id = str(uuid.uuid4())
        await save_session_file(session_string, session_id)
        
        country_code = data.get('country_code')
        proxy_id = data.get('proxy_id')
        
        async with get_db() as (cur, conn):
            await cur.execute(
                """INSERT INTO phone_numbers 
                   (phone, country_code, session_id, password, price, status, seller_id, has_2fa, proxy_id) 
                   VALUES (%s, %s, %s, %s, 
                           (SELECT price FROM countries WHERE code = %s), 
                           'available', %s, TRUE, %s)""",
                (phone, country_code, session_id, new_password, country_code, ADMIN_ID, proxy_id)
            )
            await conn.commit()
        
        if 'temp_session_id' in data:
            await delete_session_folder(data['temp_session_id'])
        
        await state.clear()
        await proxy_manager.clear_cache(proxy_id)
        proxy_config = proxy_manager.get_proxy_config(proxy_id)
        proxy_ip = proxy_config['ip'] if proxy_config else 'Nomalum'
        
        success_text = (
            f"✅ <b>Raqam muvaffaqiyatli qo'shildi!</b>\n\n"
            f"📞 Raqam: <code>{phone}</code>\n"
            f"🔒 2FA parol: <code>{new_password}</code>\n"
            f"🆔 Sessiya ID: <code>{session_id}</code>\n"
            f"📡 Proxy: <code>{proxy_ip}</code>\n"
            f"🧹 Kod xabarlari: Tozalandi ✅\n\n"
            f"⚠️ Parolni xavfsiz joyda saqlang!"
        )
        
        if hasattr(msg_or_call, 'answer'):
            await msg_or_call.answer(success_text, reply_markup=get_main_menu(ADMIN_ID))
        else:
            await msg_or_call.message.edit_text(success_text)
            await msg_or_call.message.answer("🔙 Admin panelga qaytish uchun:", reply_markup=get_main_menu(ADMIN_ID))
        await client.disconnect()
    except Exception as e:
        error_text = f"❌ Xatolik yuz berdi: {str(e)}"
        if 'temp_session_id' in data:
            await delete_session_folder(data['temp_session_id'])
        
        if hasattr(msg_or_call, 'answer'):
            await msg_or_call.answer(error_text, reply_markup=get_cancel_keyboard())
        else:
            await msg_or_call.message.edit_text(error_text)
        await client.disconnect()
        await state.clear()

# ==================== ASOSIY PANEL: NOMER OLISH ====================
@dp.message(F.text == "📞 Nomer olish")
async def buy_number_intro(msg: Message):
    await msg.answer(
        "📱 <b>Nomer sotib olish</b>\n\n"
        "⚠️ <b>Muhim eslatma:</b>\n"
        "• Akkauntni sotib olganingizdan so'ng bot boshqa hech narsaga javob bermaydi\n"
        "• Siz faqat kod olish va akkauntni qabul qilish tugmalaridan foydalanasiz\n"
        "• Akkauntni olgach, darhol parolni o'zgartiring\n\n"
        "Davom etish uchun tugmani bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Davom etish", callback_data="buy_continue")]
        ])
    )

@dp.callback_query(F.data == "buy_continue")
async def buy_show_countries(call: CallbackQuery):
    countries = await get_countries_with_stats()
    available_countries = [c for c in countries if c['available_count'] > 0]
    
    if not available_countries:
        await call.message.edit_text(
            "❌ Hozircha sotuvda hech qanday raqam mavjud emas!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")]
            ])
        )
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for country in available_countries:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{country['name']} - {country['price']:,} so'm | {country['available_count']} ta",
                callback_data=f"buy_country:{country['code']}"
            )
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="close_message")])
    await call.message.edit_text("🌍 <b>Davlatni tanlang:</b>\n\nDavlat nomi - Narxi - Mavjud raqamlar soni", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("buy_country:"))
async def buy_show_country_info(call: CallbackQuery):
    country_code = call.data.split(":")[1]
    async with get_db() as (cur, conn):
        await cur.execute(
            """SELECT c.*, 
                      COUNT(CASE WHEN p.status = 'available' THEN 1 END) as available_count
               FROM countries c
               LEFT JOIN phone_numbers p ON c.code = p.country_code AND p.status = 'available'
               WHERE c.code = %s
               GROUP BY c.code, c.name, c.phone_prefix, c.price""",
            (country_code,)
        )
        country = await cur.fetchone()
    
    if not country or country['available_count'] == 0:
        await call.answer("❌ Bu davlatda raqam qolmagan!", show_alert=True)
        return
    
    text = (
        f"🌍 <b>{country['name']}</b>\n\n"
        f"📊 Mavjud raqamlar: <b>{country['available_count']} ta</b>\n"
        f"💰 Narxi: <b>{country['price']:,} so'm</b>\n\n"
        f"Ma'lumot bilan tanishib chiqib, sotib olish tugmasini bosing:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Sotib olish", callback_data=f"buy_confirm:{country_code}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="buy_continue")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("buy_confirm:"))
async def buy_process_purchase(call: CallbackQuery):
    user_id = call.from_user.id
    country_code = call.data.split(":")[1]
    balances = await get_user_balance(user_id)
    
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM countries WHERE code = %s", (country_code,))
        country = await cur.fetchone()
    
    if balances['purchase'] < country['price']:
        await call.answer(
            f"❌ Balansingiz yetarli emas!\nKerak: {country['price']:,} so'm\nSizda: {balances['purchase']:,} so'm",
            show_alert=True
        )
        return
    
    phone = await get_available_phone_by_country(country_code)
    if not phone:
        await call.answer("❌ Kechirasiz, bu davlatda raqam qolmadi!", show_alert=True)
        return
    
    await update_balance(user_id, -country['price'], 'purchase')
    async with get_db() as (cur, conn):
        await cur.execute(
            """UPDATE phone_numbers 
               SET status = 'sold', buyer_id = %s, sold_at = NOW() 
               WHERE id = %s""",
            (user_id, phone['id'])
        )
        await cur.execute("UPDATE users SET total_purchased = total_purchased + 1 WHERE user_id = %s", (user_id,))
        await conn.commit()
    
    if phone.get('proxy_id'):
        await proxy_manager.clear_cache(phone['proxy_id'])
    
    phone['country_name'] = country['name']
    phone['price'] = country['price']
    await notify_admin_new_sale(phone, user_id, call.from_user.full_name)
    
    temp_data = {
        'phone_id': phone['id'],
        'phone': phone['phone'],
        'session_id': phone['session_id'],
        'password': phone['password'],
        'user_id': user_id,
        'proxy_id': phone.get('proxy_id'),
        'last_code': '',
        'country_name': country['name'],
        'price': country['price']
    }
    
    if not hasattr(dp, 'temp_purchases'):
        dp.temp_purchases = {}
    dp.temp_purchases[user_id] = temp_data
    
    await call.message.edit_text(
        f"✅ <b>Raqam sotib olindi!</b>\n\n"
        f"📞 Raqam: <code>{phone['phone']}</code>\n"
        f"💰 Narxi: {country['price']:,} so'm\n\n"
        f"Endi kod olishingiz mumkin:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Kodni olish", callback_data=f"get_purchase_code:{phone['id']}")],
            [InlineKeyboardButton(text="✅ Akkauntni oldim", callback_data=f"confirm_purchase:{phone['id']}")]
        ])
    )
    await call.answer("✅ Sotib olindi!")

@dp.callback_query(F.data.startswith("get_purchase_code:"))
async def get_purchase_code(call: CallbackQuery):
    user_id = call.from_user.id
    phone_id = int(call.data.split(":")[1])
    await call.answer("⏳ Kod olinmoqda...")
    
    if not hasattr(dp, 'temp_purchases') or user_id not in dp.temp_purchases:
        await call.message.edit_text("❌ Ma'lumot topilmadi!")
        await call.answer("❌ Ma'lumot topilmadi!", show_alert=True)
        return
    
    data = dp.temp_purchases[user_id]
    try:
        await call.message.delete()
    except:
        pass
    
    code, is_new, error = await fetch_code_from_session(
        data['session_id'], 
        user_id, 
        data.get('proxy_id'),
        data.get('phone_id')
    )
    
    await send_code_result_message(call.message.chat.id, data['phone'], data['password'], code, is_new, error, phone_id)

@dp.callback_query(F.data.startswith("refresh_purchase_code:"))
async def refresh_purchase_code(call: CallbackQuery):
    user_id = call.from_user.id
    phone_id = int(call.data.split(":")[1])
    await call.answer("🔄 Kod yangilanmoqda...")
    
    if not hasattr(dp, 'temp_purchases') or user_id not in dp.temp_purchases:
        await call.message.edit_text("❌ Ma'lumot topilmadi!")
        await call.answer("❌ Ma'lumot topilmadi!", show_alert=True)
        return
    
    data = dp.temp_purchases[user_id]
    try:
        await call.message.delete()
    except:
        pass
    
    code, is_new, error = await fetch_code_from_session(
        data['session_id'], 
        user_id,
        data.get('proxy_id'),
        data.get('phone_id')
    )
    
    await send_code_result_message(call.message.chat.id, data['phone'], data['password'], code, is_new, error, phone_id)

@dp.callback_query(F.data.startswith("confirm_purchase:"))
async def confirm_purchase_taken(call: CallbackQuery):
    user_id = call.from_user.id
    phone_id = int(call.data.split(":")[1])
    
    if not hasattr(dp, 'temp_purchases') or user_id not in dp.temp_purchases:
        await call.message.edit_text("❌ Ma'lumot topilmadi!")
        await call.answer("❌ Ma'lumot topilmadi!", show_alert=True)
        return
    
    data = dp.temp_purchases[user_id]
    try:
        await call.message.delete()
    except:
        pass
    
    session_string = await read_session_file(data['session_id'])
    if session_string:
        proxy_config = proxy_manager.get_proxy_config(data.get('proxy_id')) if data.get('proxy_id') else None
        proxy = proxy_manager.create_proxy_client(proxy_config) if proxy_config else None
        client = TelegramClient(StringSession(session_string), TELETHON_API_ID, TELETHON_API_HASH, proxy=proxy)
        try:
            await client.connect()
            if await client.is_user_authorized():
                await client.log_out()
        except:
            pass
        finally:
            await client.disconnect()
    
    await delete_session_folder(data['session_id'])
    if data.get('proxy_id'):
        await proxy_manager.clear_cache(data['proxy_id'])
    
    if user_id in dp.temp_purchases:
        del dp.temp_purchases[user_id]
    
    await bot.send_message(
        call.message.chat.id,
        f"✅ <b>Akkaunt qabul qilindi!</b>\n\n"
        f"📞 Raqam: <code>{data['phone']}</code>\n\n"
        f"🤖 Bot akkauntingizni tark etdi.\n"
        f"🔒 Endi siz akkauntdan xavfsiz foydalanishingiz mumkin.\n\n"
        f"⚠️ <b>Parolni darhol o'zgartirishni unutmang!</b>",
        reply_markup=get_main_menu(user_id)
    )
    await call.answer("✅ Akkaunt qabul qilindi!")

# ==================== ASOSIY PANEL: HISOBIM ====================
@dp.message(F.text == "💰 Hisobim")
async def show_balance(msg: Message):
    user = await get_or_create_user(msg.from_user.id, msg.from_user.full_name, msg.from_user.username)
    balances = await get_user_balance(msg.from_user.id)
    text = (
        f"👤 <b>Hisobingiz</b>\n\n"
        f"🆔 ID: <code>{msg.from_user.id}</code>\n"
        f"💰 Balans: <b>{balances['purchase']:,} so'm</b>\n\n"
        f"🛒 Xaridlar soni: <b>{user['total_purchased']} ta</b>"
    )
    await msg.answer(text)

# ==================== ASOSIY PANEL: XARIDLARIM ====================
@dp.message(F.text == "🛒 Xaridlarim")
async def show_purchases(msg: Message):
    async with get_db() as (cur, conn):
        await cur.execute(
            """SELECT p.*, c.name as country_name, c.price as country_price
               FROM phone_numbers p
               JOIN countries c ON p.country_code = c.code
               WHERE p.buyer_id = %s AND p.status = 'sold'
               ORDER BY p.sold_at DESC""",
            (msg.from_user.id,)
        )
        purchases = await cur.fetchall()
    
    if not purchases:
        await msg.answer("📭 Sizda hozircha xaridlar mavjud emas!")
        return
    
    page_size = 5
    total_pages = (len(purchases) + page_size - 1) // page_size
    await show_purchases_page(msg, purchases, 1, page_size, total_pages, is_first=True)

async def show_purchases_page(msg_or_call, purchases, page, page_size, total_pages, is_first=False):
    start = (page - 1) * page_size
    end = min(start + page_size, len(purchases))
    page_purchases = purchases[start:end]
    
    text = f"🛒 <b>Xaridlarim</b>\n\n"
    for i, purchase in enumerate(page_purchases, start + 1):
        country_name = purchase['country_name'] if purchase['country_name'] else 'Nomalum'
        sold_date = purchase['sold_at'].strftime('%d.%m.%Y %H:%M') if purchase['sold_at'] else 'Nomalum'
        text += (
            f"{i}. <b>{country_name}</b>\n"
            f"   📞 Raqam: <code>{purchase['phone']}</code>\n"
            f"   💰 Narxi: {purchase['country_price']:,} so'm\n"
            f"   🔒 Parol: <code>{purchase['password']}</code>\n"
            f"   📅 Sana: {sold_date}\n\n"
        )
    
    text += f"📄 Sahifa: {page}/{total_pages}"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"purchases_page:{page-1}"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"purchases_page:{page+1}"))
    
    if nav_row:
        kb.inline_keyboard.append(nav_row)
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Yopish", callback_data="close_message")])
    
    if is_first or hasattr(msg_or_call, 'answer'):
        await msg_or_call.answer(text, reply_markup=kb)
    else:
        try:
            await msg_or_call.edit_text(text, reply_markup=kb)
        except:
            try:
                await msg_or_call.delete()
            except:
                pass
            if hasattr(msg_or_call, 'message'):
                await msg_or_call.message.answer(text, reply_markup=kb)
            else:
                await bot.send_message(msg_or_call.chat.id, text, reply_markup=kb)

@dp.callback_query(F.data.startswith("purchases_page:"))
async def purchases_page_change(call: CallbackQuery):
    page = int(call.data.split(":")[1])
    async with get_db() as (cur, conn):
        await cur.execute(
            """SELECT p.*, c.name as country_name, c.price as country_price
               FROM phone_numbers p
               JOIN countries c ON p.country_code = c.code
               WHERE p.buyer_id = %s AND p.status = 'sold'
               ORDER BY p.sold_at DESC""",
            (call.from_user.id,)
        )
        purchases = await cur.fetchall()
    
    page_size = 5
    total_pages = (len(purchases) + page_size - 1) // page_size
    await show_purchases_page(call.message, purchases, page, page_size, total_pages, is_first=False)
    await call.answer()

# ==================== ASOSIY PANEL: HISOB TO'LDIRISH ====================
@dp.message(F.text == "💳 Hisob to'ldirish")
async def deposit_start(msg: Message, state: FSMContext):
    await msg.answer(
        f"💳 <b>Hisob to'ldirish</b>\n\n⬆️ Minimal to'ldirish: {MIN_DEPOSIT:,} so'm\n\nQancha summa kiritmoqchisiz? (so'mda)",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(DepositStates.wait_amount)

@dp.message(DepositStates.wait_amount)
async def deposit_get_amount(msg: Message, state: FSMContext):
    try:
        amount = int(msg.text.strip().replace(',', '').replace(' ', ''))
        if amount < MIN_DEPOSIT:
            raise ValueError()
    except:
        await msg.answer(f"❌ Minimal to'ldirish summasi: {MIN_DEPOSIT:,} so'm", reply_markup=get_cancel_keyboard())
        return
    
    fee = int(amount * FEE_PERCENT / 100)
    total = amount - fee
    await state.update_data(amount=total, fee=fee, total=amount)
    
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM payment_methods WHERE is_active = TRUE LIMIT 1")
        method = await cur.fetchone()
    
    if not method:
        await msg.answer("❌ To'lov usuli topilmadi! Admin bilan bog'laning.")
        await state.clear()
        return
    
    text = (
        f"💳 <b>To'lov ma'lumotlari:</b>\n\n"
        f"💳 Karta: <code>{method['card_number']}</code>\n"
        f"👤 Egasi: <b>{method['card_owner']}</b>\n\n"
        f"💰 Hisobga tushadi: <b>{total:,} so'm</b>\n"
        f"💵 To'lov qilinadi: <b>{amount:,} so'm</b>\n\n"
        f"To'lov qilgach, \"✅ To'lov qildim\" tugmasini bosing va chekni yuboring!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ To'lov qildim", callback_data="deposit_paid")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_admin")]
    ])
    await msg.answer(text, reply_markup=kb)
    await state.set_state(DepositStates.wait_receipt)

@dp.callback_query(F.data == "deposit_paid")
async def deposit_paid_callback(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📸 Iltimos, to'lov chekini (skrinshot yoki PDF) yuboring:", reply_markup=get_cancel_keyboard())
    await state.set_state(DepositStates.wait_receipt)
    await call.answer()

@dp.message(DepositStates.wait_receipt, F.photo | F.document)
async def deposit_receipt_received(msg: Message, state: FSMContext):
    data = await state.get_data()
    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    
    async with get_db() as (cur, conn):
        await cur.execute(
            """INSERT INTO payment_requests 
               (user_id, amount, fee, total_amount, type, status, receipt_file_id) 
               VALUES (%s, %s, %s, %s, 'deposit', 'pending', %s)""",
            (msg.from_user.id, data['amount'], data['fee'], data['total'], file_id)
        )
        request_id = cur.lastrowid
        await conn.commit()
    
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_deposit:{request_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_deposit:{request_id}")
        ]
    ])
    
    caption = (
        f"💰 <b>Yangi to'lov!</b>\n\n"
        f"🆔 So'rov ID: {request_id}\n"
        f"👤 Foydalanuvchi ID: <code>{msg.from_user.id}</code>\n"
        f"📛 Ism: {msg.from_user.full_name}\n"
        f"📱 Username: @{msg.from_user.username or 'yoq'}\n"
        f"💵 Summa: {data['amount']:,} so'm\n"
        f"📅 Sana: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    
    if msg.photo:
        sent_msg = await bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=kb)
    else:
        sent_msg = await bot.send_document(ADMIN_ID, file_id, caption=caption, reply_markup=kb)
    
    try:
        await bot.pin_chat_message(ADMIN_ID, sent_msg.message_id)
    except Exception as e:
        print(f"Pin error: {e}")
    
    await msg.answer("✅ To'lov so'rovingiz qabul qilindi!\nAdmin tasdiqlaganidan so'ng balansingizga pul qo'shiladi.", reply_markup=get_main_menu(msg.from_user.id))

@dp.callback_query(F.data.startswith("approve_deposit:"))
async def approve_deposit(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    request_id = int(call.data.split(":")[1])
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM payment_requests WHERE id = %s AND status = 'pending'", (request_id,))
        request = await cur.fetchone()
    
    if not request:
        await call.answer("❌ So'rov topilmadi!", show_alert=True)
        return
    
    await update_balance(request['user_id'], request['amount'], 'purchase')
    async with get_db() as (cur, conn):
        await cur.execute("UPDATE payment_requests SET status = 'approved', processed_at = NOW() WHERE id = %s", (request_id,))
        await conn.commit()
    
    try:
        await bot.send_message(request['user_id'], f"✅ To'lovingiz tasdiqlandi!\n\n💰 Hisobingizga {request['amount']:,} so'm qo'shildi!")
    except:
        pass
    
    try:
        await bot.unpin_chat_message(chat_id=ADMIN_ID, message_id=call.message.message_id)
        await call.message.delete()
    except Exception as e:
        print(f"Pin/delete error: {e}")
    
    await bot.send_message(
        ADMIN_ID,
        f"✅ <b>To'lov tasdiqlandi!</b>\n\n🆔 So'rov ID: {request_id}\n👤 Foydalanuvchi ID: <code>{request['user_id']}</code>\n💰 Summa: {request['amount']:,} so'm\n📅 Sana: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    await call.answer("✅ To'lov tasdiqlandi!", show_alert=True)

@dp.callback_query(F.data.startswith("reject_deposit:"))
async def reject_deposit(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Faqat admin!")
    
    request_id = int(call.data.split(":")[1])
    async with get_db() as (cur, conn):
        await cur.execute("SELECT * FROM payment_requests WHERE id = %s AND status = 'pending'", (request_id,))
        request = await cur.fetchone()
    
    if not request:
        await call.answer("❌ So'rov topilmadi!", show_alert=True)
        return
    
    async with get_db() as (cur, conn):
        await cur.execute("UPDATE payment_requests SET status = 'rejected', processed_at = NOW() WHERE id = %s", (request_id,))
        await conn.commit()
    
    try:
        await bot.send_message(request['user_id'], "❌ To'lovingiz rad etildi!\n\nIltimos, to'g'ri ma'lumotlar bilan qaytadan urinib ko'ring.")
    except:
        pass
    
    try:
        await bot.unpin_chat_message(chat_id=ADMIN_ID, message_id=call.message.message_id)
        await call.message.delete()
    except Exception as e:
        print(f"Pin/delete error: {e}")
    
    await call.answer("❌ To'lov rad etildi!", show_alert=True)

# ==================== WEB SERVER (RENDER KEEP-ALIVE) ====================
async def handle_ping(request):
    return web.Response(text="OK, Bot running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/health', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Web server {port}-portda ishga tushdi.")

# ==================== MAIN EXECUTION ====================
async def main():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    
    # Web serverni Render uchun parallel yuritish
    await start_web_server()
    
    # Bot pollingni boshlash
    print("🚀 Bot muvaffaqiyatli ishga tushdi!")
    try:
        await dp.start_polling(bot)
    finally:
        await DatabasePool.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
