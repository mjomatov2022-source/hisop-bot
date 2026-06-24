import asyncio
import aiohttp
import aiofiles
import sqlite3
import os
import json
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# === SOZLAMALAR ===
BOT_TOKEN = "SIZNING_BOT_TOKENINGIZ"
GROQ_API_KEY = "SIZNING_GROQ_API_KALITINGIZ"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# === DATABASE ===
def init_db():
    conn = sqlite3.connect("hisobchi.db")
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,  -- 'kirim' yoki 'chiqim'
        amount REAL,
        currency TEXT DEFAULT 'UZS',
        description TEXT,
        date TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        person_name TEXT,
        amount REAL,
        currency TEXT DEFAULT 'UZS',
        type TEXT,  -- 'berilgan' yoki 'olingan'
        date TEXT,
        is_paid INTEGER DEFAULT 0
    )""")
    
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect("hisobchi.db")
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(CASE WHEN type='kirim' THEN amount ELSE -amount END), 0) FROM transactions WHERE user_id=? AND currency='UZS'", (user_id,))
    balance = c.fetchone()[0]
    conn.close()
    return balance

def add_transaction(user_id, type_, amount, currency, description):
    conn = sqlite3.connect("hisobchi.db")
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, type, amount, currency, description, date) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, type_, amount, currency, description, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def get_stats(user_id):
    conn = sqlite3.connect("hisobchi.db")
    c = conn.cursor()
    month = datetime.now().strftime("%Y-%m")
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=? AND type='kirim' AND date LIKE ?", (user_id, f"{month}%"))
    kirim = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=? AND type='chiqim' AND date LIKE ?", (user_id, f"{month}%"))
    chiqim = c.fetchone()[0]
    conn.close()
    return kirim, chiqim

def get_debts(user_id):
    conn = sqlite3.connect("hisobchi.db")
    c = conn.cursor()
    c.execute("SELECT * FROM debts WHERE user_id=? AND is_paid=0", (user_id,))
    debts = c.fetchall()
    conn.close()
    return debts

def add_debt(user_id, person_name, amount, currency, type_):
    conn = sqlite3.connect("hisobchi.db")
    c = conn.cursor()
    c.execute("INSERT INTO debts (user_id, person_name, amount, currency, type, date) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, person_name, amount, currency, type_, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

# === VALYUTA KURSI ===
async def get_currency_rates():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/") as resp:
                data = await resp.json()
                rates = {}
                for item in data:
                    if item["Ccy"] == "USD":
                        rates["USD"] = float(item["Rate"])
                    if item["Ccy"] == "RUB":
                        rates["RUB"] = float(item["Rate"])
                return rates
    except:
        return {"USD": 12800, "RUB": 140}

# === OVOZNI MATNGA AYLANTIRISH (GROQ) ===
async def transcribe_voice(file_path):
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename="voice.ogg", content_type="audio/ogg")
                data.add_field("model", "whisper-large-v3")
                data.add_field("language", "uz")
                
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
                async with session.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    data=data,
                    headers=headers
                ) as resp:
                    result = await resp.json()
                    return result.get("text", "")
    except Exception as e:
        return ""

# === MATNNI TAHLIL QILISH (GROQ AI) ===
async def analyze_text(text):
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama3-8b-8192",
                "messages": [
                    {
                        "role": "system",
                        "content": """Siz moliyaviy yordamchisiz. Foydalanuvchi matnini tahlil qiling va JSON formatida qaytaring:
{"type": "kirim" yoki "chiqim", "amount": raqam, "currency": "UZS" yoki "USD" yoki "RUB", "description": "tavsif"}
Faqat JSON qaytaring, boshqa hech narsa yozmang."""
                    },
                    {"role": "user", "content": text}
                ],
                "max_tokens": 200
            }
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers
            ) as resp:
                result = await resp.json()
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)
    except:
        return None

# === KLAVIATURA ===
def main_keyboard():
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💚 Kirim qo'shish"), KeyboardButton(text="❤️ Chiqim qo'shish")],
        [KeyboardButton(text="💰 Balans"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🤝 Qarzlar"), KeyboardButton(text="💱 Valyuta kursi")],
        [KeyboardButton(text="📋 Oxirgi hisobotlar")]
    ], resize_keyboard=True)
    return kb

# === HOLATLAR ===
class Form(StatesGroup):
    waiting_kirim = State()
    waiting_chiqim = State()
    waiting_debt_name = State()
    waiting_debt_amount = State()
    waiting_debt_type = State()

# === HANDLERS ===
@dp.message(Command("start"))
async def start(message: types.Message):
    name = message.from_user.first_name
    await message.answer(
        f"Salom, {name}! 👋\n\n"
        f"Men <b>Hisobchi Bot</b>man 💚\n"
        f"Kirim-chiqimlaringizni kuzatib boraman!\n\n"
        f"Ovozli xabar ham yuborishingiz mumkin 🎤",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

@dp.message(F.text == "💰 Balans")
async def show_balance(message: types.Message):
    balance = get_balance(message.from_user.id)
    rates = await get_currency_rates()
    usd_balance = balance / rates["USD"] if rates["USD"] > 0 else 0
    
    await message.answer(
        f"💰 <b>Sizning balansingiz:</b>\n\n"
        f"🟢 {balance:,.0f} UZS\n"
        f"💵 {usd_balance:,.1f} USD\n",
        parse_mode="HTML"
    )

@dp.message(F.text == "💚 Kirim qo'shish")
async def add_income(message: types.Message, state: FSMContext):
    await message.answer("💚 Kirim summasini kiriting:\n\nMasalan: 500000")
    await state.set_state(Form.waiting_kirim)

@dp.message(Form.waiting_kirim)
async def process_kirim(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", "").replace(",", ""))
        add_transaction(message.from_user.id, "kirim", amount, "UZS", "Kirim")
        balance = get_balance(message.from_user.id)
        await message.answer(
            f"✅ <b>Kirim qo'shildi!</b>\n\n"
            f"💚 Kirim: +{amount:,.0f} UZS\n"
            f"💰 Balans: {balance:,.0f} UZS",
            parse_mode="HTML"
        )
        await state.clear()
    except:
        await message.answer("❌ Noto'g'ri format! Faqat raqam kiriting.")

@dp.message(F.text == "❤️ Chiqim qo'shish")
async def add_expense(message: types.Message, state: FSMContext):
    await message.answer("❤️ Chiqim summasini kiriting:\n\nMasalan: 50000")
    await state.set_state(Form.waiting_chiqim)

@dp.message(Form.waiting_chiqim)
async def process_chiqim(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", "").replace(",", ""))
        add_transaction(message.from_user.id, "chiqim", amount, "UZS", "Chiqim")
        balance = get_balance(message.from_user.id)
        await message.answer(
            f"✅ <b>Chiqim qo'shildi!</b>\n\n"
            f"❤️ Chiqim: -{amount:,.0f} UZS\n"
            f"💰 Balans: {balance:,.0f} UZS",
            parse_mode="HTML"
        )
        await state.clear()
    except:
        await message.answer("❌ Noto'g'ri format! Faqat raqam kiriting.")

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    kirim, chiqim = get_stats(message.from_user.id)
    foyda = kirim - chiqim
    month = datetime.now().strftime("%B %Y")
    
    await message.answer(
        f"📊 <b>{month} statistikasi:</b>\n\n"
        f"💚 Kirim: +{kirim:,.0f} UZS\n"
        f"❤️ Chiqim: -{chiqim:,.0f} UZS\n"
        f"{'✅' if foyda >= 0 else '⚠️'} Natija: {foyda:,.0f} UZS",
        parse_mode="HTML"
    )

@dp.message(F.text == "💱 Valyuta kursi")
async def show_rates(message: types.Message):
    await message.answer("⏳ Kurs yuklanmoqda...")
    rates = await get_currency_rates()
    await message.answer(
        f"💱 <b>Valyuta kurslari (CBU):</b>\n\n"
        f"💵 1 USD = {rates['USD']:,.0f} UZS\n"
        f"🇷🇺 1 RUB = {rates['RUB']:,.1f} UZS\n\n"
        f"🕐 Yangilangan: {datetime.now().strftime('%H:%M')}",
        parse_mode="HTML"
    )

@dp.message(F.text == "🤝 Qarzlar")
async def show_debts(message: types.Message):
    debts = get_debts(message.from_user.id)
    
    if not debts:
        await message.answer("✅ Hozircha qarz yo'q!")
        return
    
    text = "🤝 <b>Qarzlar:</b>\n\n"
    berilgan = [d for d in debts if d[5] == "berilgan"]
    olingan = [d for d in debts if d[5] == "olingan"]
    
    if berilgan:
        text += "📤 <b>Berilgan qarzlar:</b>\n"
        for d in berilgan:
            text += f"  • {d[2]}: {d[3]:,.0f} {d[4]}\n"
    
    if olingan:
        text += "\n📥 <b>Olingan qarzlar:</b>\n"
        for d in olingan:
            text += f"  • {d[2]}: {d[3]:,.0f} {d[4]}\n"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📋 Oxirgi hisobotlar")
async def show_history(message: types.Message):
    conn = sqlite3.connect("hisobchi.db")
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10", (message.from_user.id,))
    transactions = c.fetchall()
    conn.close()
    
    if not transactions:
        await message.answer("📋 Hozircha hisobotlar yo'q!")
        return
    
    text = "📋 <b>Oxirgi 10 ta hisobot:</b>\n\n"
    for t in transactions:
        emoji = "💚" if t[2] == "kirim" else "❤️"
        sign = "+" if t[2] == "kirim" else "-"
        text += f"{emoji} {sign}{t[3]:,.0f} {t[4]} — {t[6]}\n"
    
    await message.answer(text, parse_mode="HTML")

# === OVOZLI XABAR ===
@dp.message(F.voice)
async def handle_voice(message: types.Message):
    await message.answer("🎤 Ovozli xabar tahlil qilinmoqda...")
    
    # Ovozni yuklab olish
    file = await bot.get_file(message.voice.file_id)
    file_path = f"/tmp/voice_{message.from_user.id}.ogg"
    await bot.download_file(file.file_path, file_path)
    
    # Matnga aylantirish
    text = await transcribe_voice(file_path)
    
    if not text:
        await message.answer("❌ Ovozni tushunib bo'lmadi. Qaytadan urinib ko'ring.")
        return
    
    await message.answer(f"🎤 Eshitildi: <i>{text}</i>", parse_mode="HTML")
    
    # AI tahlil
    result = await analyze_text(text)
    
    if result and "type" in result and "amount" in result:
        add_transaction(
            message.from_user.id,
            result["type"],
            result["amount"],
            result.get("currency", "UZS"),
            result.get("description", text)
        )
        balance = get_balance(message.from_user.id)
        emoji = "💚" if result["type"] == "kirim" else "❤️"
        sign = "+" if result["type"] == "kirim" else "-"
        
        await message.answer(
            f"✅ <b>Avtomatik qo'shildi!</b>\n\n"
            f"{emoji} {result['type'].capitalize()}: {sign}{result['amount']:,.0f} {result.get('currency', 'UZS')}\n"
            f"💰 Balans: {balance:,.0f} UZS",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "⚠️ Aniq tushunmadim. Iltimos aniqroq ayting:\n"
            "Masalan: '50 ming kirim' yoki '20000 chiqim'"
        )
    
    # Faylni o'chirish
    if os.path.exists(file_path):
        os.remove(file_path)

# === ISHGA TUSHIRISH ===
async def main():
    init_db()
    print("✅ Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
