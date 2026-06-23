"""
💰 Hisob-Kitob Telegram Bot
Kutubxona: aiogram 3.x
O'rnatish: pip install aiogram aiosqlite
"""

import asyncio
import aiosqlite
import logging
import re
from datetime import datetime, date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ===================== SOZLAMALAR =====================
BOT_TOKEN = "8880362591:AAFQK-pfOUhPqrcPhZLCVSOGJenocGmcsdk"
DB_FILE = "hisob.db"
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ===================== HOLATLAR =====================
class Qoshish(StatesGroup):
    summa = State()
    kategoriya = State()
    izoh = State()

# ===================== KATEGORIYALAR =====================
KATEGORIYALAR = {
    "oziq": "🛒 Oziq-ovqat",
    "transport": "🚗 Transport",
    "kommunal": "💡 Kommunal",
    "kiyim": "👗 Kiyim",
    "salomatlik": "🏥 Salomatlik",
    "boshqa": "📦 Boshqa",
}

# Kategoriya kalit so'zlari
KAT_SOZLAR = {
    "oziq": ["non", "go'sht", "gosht", "ovqat", "oziq", "supermarket", "bozor", "sabzavot", "meva", "sut", "guruch", "un", "yog", "shakar", "ichimlik", "mineral"],
    "transport": ["benzin", "taksi", "avtobus", "metro", "mashina", "moshina", "yo'l", "yol", "transport", "uber", "yandex"],
    "kommunal": ["gaz", "suv", "elektr", "tok", "internet", "kommunal", "uy haqi", "ijara"],
    "kiyim": ["kiyim", "ko'ylak", "koylak", "shim", "bosh", "oyoq", "kros", "sumka", "kiyinish"],
    "salomatlik": ["dori", "doktor", "shifokor", "klinika", "kasalxona", "apteka", "tibbiy", "salomatlik"],
}

# Daromad kalit so'zlari
DAROMAD_SOZLAR = [
    "ishladim", "oldim", "topdim", "tushdi", "kirim", "daromad",
    "maosh", "oylik", "bonus", "sovg'a", "sovga", "berdim emas",
    "topdi", "pul keldi", "pul tushdi", "sotdim"
]

# Chiqim kalit so'zlari  
CHIQIM_SOZLAR = [
    "xarjladim", "sarfladim", "to'ladim", "toladim", "soldim",
    "berdim", "ketdi", "chiqim", "harajat", "uchun", "xarid"
]

# Son so'zlari
SON_SOZLAR = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4,
    "besh": 5, "olti": 6, "yetti": 7, "sakkiz": 8, "to'qqiz": 9, "toqqiz": 9,
    "o'n": 10, "on": 10, "yigirma": 20, "o'ttiz": 30, "ottiz": 30,
    "qirq": 40, "ellik": 50, "oltmish": 60, "yetmish": 70,
    "sakson": 80, "to'qson": 90, "toqson": 90,
    "yuz": 100, "ming": 1000, "million": 1000000, "milyard": 1000000000
}

# ===================== MATN PARSING =====================
def matn_parse(text):
    """
    '100 ming ishladim' -> (100000, 'daromad', 'boshqa', 'ishladim')
    '50 ming non uchun' -> (50000, 'chiqim', 'oziq', 'non uchun')
    """
    text = text.lower().strip()
    
    # 1. Summani top
    summa = None
    
    # Raqam + so'z (masalan: 100 ming, 2 million)
    pattern = r'(\d[\d\s]*)\s*(ming|million|milyard|yuz)?'
    matches = re.finditer(pattern, text)
    for m in matches:
        raqam = int(m.group(1).replace(" ", ""))
        kopaytiruvchi = m.group(2)
        if kopaytiruvchi == "ming":
            raqam *= 1000
        elif kopaytiruvchi == "million":
            raqam *= 1000000
        elif kopaytiruvchi == "milyard":
            raqam *= 1000000000
        if raqam > 0:
            summa = raqam
            break
    
    # So'z bilan yozilgan son (masalan: ikki ming)
    if summa is None:
        for soz, qiymat in SON_SOZLAR.items():
            if soz in text:
                # Keyingi multiplikatorni qidirish
                for mult_soz, mult_val in [("million", 1000000), ("ming", 1000), ("yuz", 100)]:
                    pattern2 = rf'{soz}\s+{mult_soz}'
                    if re.search(pattern2, text):
                        summa = qiymat * mult_val
                        break
                if summa is None and qiymat >= 100:
                    summa = qiymat
                if summa:
                    break
    
    if summa is None:
        return None
    
    # 2. Tur aniqlash (daromad yoki chiqim)
    tur = None
    for soz in DAROMAD_SOZLAR:
        if soz in text:
            tur = "daromad"
            break
    if tur is None:
        for soz in CHIQIM_SOZLAR:
            if soz in text:
                tur = "chiqim"
                break
    if tur is None:
        tur = "chiqim"  # Default chiqim
    
    # 3. Kategoriya aniqlash
    kategoriya = "boshqa"
    for kat, sozlar in KAT_SOZLAR.items():
        for soz in sozlar:
            if soz in text:
                kategoriya = kat
                break
    
    return summa, tur, kategoriya

# ===================== DATABASE =====================
async def db_init():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS amallar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tur TEXT NOT NULL,
                summa REAL NOT NULL,
                kategoriya TEXT,
                izoh TEXT,
                sana TEXT NOT NULL
            )
        """)
        await db.commit()

async def amal_qosh(user_id, tur, summa, kategoriya, izoh):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO amallar (user_id, tur, summa, kategoriya, izoh, sana) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, tur, summa, kategoriya, izoh, date.today().isoformat())
        )
        await db.commit()

async def amallar_ol(user_id, oy=None, yil=None):
    if oy is None: oy = datetime.now().month
    if yil is None: yil = datetime.now().year
    oy_str = f"{yil}-{oy:02d}"
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT * FROM amallar WHERE user_id=? AND sana LIKE ? ORDER BY sana DESC",
            (user_id, f"{oy_str}%")
        ) as cur:
            return await cur.fetchall()

async def oxirgi_amallar(user_id, limit=5):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT * FROM amallar WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return await cur.fetchall()

# ===================== KLAVIATURALAR =====================
def asosiy_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Chiqim qo'shish"), KeyboardButton(text="💚 Daromad qo'shish")],
        [KeyboardButton(text="📊 Hisobot"), KeyboardButton(text="📋 So'nggi amallar")],
        [KeyboardButton(text="ℹ️ Yordam")],
    ], resize_keyboard=True)

def kategoriya_menu():
    buttons = [[InlineKeyboardButton(text=v, callback_data=f"kat_{k}")] for k, v in KATEGORIYALAR.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def bekor_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True)

def pul(n):
    return f"{int(n):,} so'm".replace(",", " ")

# ===================== HANDLERLAR =====================
@dp.message(Command("start"))
async def start(msg: types.Message):
    await db_init()
    await msg.answer(
        f"Salom, {msg.from_user.first_name}! 👋\n\n"
        "💰 *Hisob-Kitob Botiga xush kelibsiz!*\n\n"
        "Oddiy yozib yuboring:\n"
        "• `100 ming ishladim` → daromad\n"
        "• `50 ming benzin` → chiqim\n"
        "• `2 million maosh oldim` → daromad\n\n"
        "Yoki tugmalardan foydalaning 👇",
        parse_mode="Markdown",
        reply_markup=asosiy_menu()
    )

@dp.message(F.text == "ℹ️ Yordam")
async def yordam(msg: types.Message):
    await msg.answer(
        "📖 *Qo'llanma:*\n\n"
        "🤖 *Avtomatik yozish:*\n"
        "Shunchaki yozing:\n"
        "• `100 ming ishladim`\n"
        "• `50 ming non uchun`\n"
        "• `2 million maosh oldim`\n"
        "• `30 ming benzin`\n"
        "• `500 ming ijara to'ladim`\n\n"
        "🔘 *Tugmalar:*\n"
        "➕ Chiqim qo'shish\n"
        "💚 Daromad qo'shish\n"
        "📊 Oylik hisobot\n"
        "📋 So'nggi amallar",
        parse_mode="Markdown"
    )

# ——— AVTOMATIK PARSING ———
@dp.message(F.text & ~F.text.startswith("/") & 
            ~F.text.in_(["➕ Chiqim qo'shish", "💚 Daromad qo'shish", 
                         "📊 Hisobot", "📋 So'nggi amallar", "ℹ️ Yordam",
                         "❌ Bekor qilish"]))
async def auto_parse(msg: types.Message, state: FSMContext):
    current = await state.get_state()
    if current is not None:
        return  # FSM holati bo'lsa, parserni ishlatma
    
    natija = matn_parse(msg.text)
    if natija:
        summa, tur, kategoriya = natija
        await amal_qosh(msg.from_user.id, tur, summa, kategoriya, msg.text)
        
        tur_icon = "💚" if tur == "daromad" else "📉"
        kat_nomi = KATEGORIYALAR.get(kategoriya, "")
        
        await msg.answer(
            f"{tur_icon} *Avtomatik saqlandi!*\n\n"
            f"💰 Summa: `{pul(summa)}`\n"
            f"📂 Kategoriya: {kat_nomi}\n"
            f"📝 Matn: _{msg.text}_\n"
            f"📅 Sana: {date.today().strftime('%d.%m.%Y')}\n\n"
            f"Noto'g'ri bo'lsa, ➕ tugmasi orqali qo'lda kiriting.",
            parse_mode="Markdown",
            reply_markup=asosiy_menu()
        )
    # Tushunmasa, jim turadi (faqat tugmalar ishlaydi)

# ——— CHIQIM QO'SHISH ———
@dp.message(F.text == "➕ Chiqim qo'shish")
async def chiqim_boshlash(msg: types.Message, state: FSMContext):
    await state.set_state(Qoshish.summa)
    await state.update_data(tur="chiqim")
    await msg.answer("💸 Chiqim summasini kiriting:\n\nMasalan: `50000`", parse_mode="Markdown", reply_markup=bekor_menu())

# ——— DAROMAD QO'SHISH ———
@dp.message(F.text == "💚 Daromad qo'shish")
async def daromad_boshlash(msg: types.Message, state: FSMContext):
    await state.set_state(Qoshish.summa)
    await state.update_data(tur="daromad")
    await msg.answer("💚 Daromad summasini kiriting:\n\nMasalan: `2000000`", parse_mode="Markdown", reply_markup=bekor_menu())

# ——— BEKOR QILISH ———
@dp.message(F.text == "❌ Bekor qilish")
async def bekor(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Bekor qilindi.", reply_markup=asosiy_menu())

# ——— SUMMA (FSM) ———
@dp.message(Qoshish.summa)
async def summa_qabul(msg: types.Message, state: FSMContext):
    text = msg.text.replace(" ", "").replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await msg.answer("⚠️ To'g'ri summa kiriting!\n\nMasalan: `50000`", parse_mode="Markdown")
        return
    await state.update_data(summa=int(text))
    data = await state.get_data()
    if data["tur"] == "chiqim":
        await state.set_state(Qoshish.kategoriya)
        await msg.answer("📂 Kategoriyani tanlang:", reply_markup=kategoriya_menu())
    else:
        await state.set_state(Qoshish.izoh)
        await msg.answer("📝 Izoh kiriting (yoki /skip):", reply_markup=bekor_menu())

# ——— KATEGORIYA (FSM) ———
@dp.callback_query(F.data.startswith("kat_"), Qoshish.kategoriya)
async def kategoriya_qabul(call: types.CallbackQuery, state: FSMContext):
    kat = call.data.replace("kat_", "")
    await state.update_data(kategoriya=kat)
    await state.set_state(Qoshish.izoh)
    await call.message.edit_text(f"✅ Kategoriya: {KATEGORIYALAR[kat]}")
    await call.message.answer("📝 Izoh kiriting yoki /skip:", reply_markup=bekor_menu())

# ——— IZOH (FSM) ———
@dp.message(Qoshish.izoh)
async def izoh_qabul(msg: types.Message, state: FSMContext):
    izoh = "" if msg.text == "/skip" else msg.text
    data = await state.get_data()
    await state.clear()
    kat = data.get("kategoriya", "boshqa")
    await amal_qosh(msg.from_user.id, data["tur"], data["summa"], kat, izoh)
    tur_icon = "📉" if data["tur"] == "chiqim" else "💚"
    kat_nomi = KATEGORIYALAR.get(kat, "") if data["tur"] == "chiqim" else ""
    await msg.answer(
        f"{tur_icon} *Saqlandi!*\n\n"
        f"💰 Summa: `{pul(data['summa'])}`\n"
        + (f"📂 Kategoriya: {kat_nomi}\n" if kat_nomi else "")
        + (f"📝 Izoh: {izoh}\n" if izoh else "")
        + f"📅 Sana: {date.today().strftime('%d.%m.%Y')}",
        parse_mode="Markdown",
        reply_markup=asosiy_menu()
    )

# ——— HISOBOT ———
@dp.message(F.text == "📊 Hisobot")
async def hisobot(msg: types.Message):
    amallar = await amallar_ol(msg.from_user.id)
    if not amallar:
        await msg.answer("📭 Bu oyda hech qanday amal yo'q.", reply_markup=asosiy_menu())
        return
    daromad = sum(a[3] for a in amallar if a[2] == "daromad")
    chiqim = sum(a[3] for a in amallar if a[2] == "chiqim")
    qoldiq = daromad - chiqim
    kat_stat = {}
    for a in amallar:
        if a[2] == "chiqim":
            k = a[4] or "boshqa"
            kat_stat[k] = kat_stat.get(k, 0) + a[3]
    kat_text = ""
    for k, v in sorted(kat_stat.items(), key=lambda x: -x[1]):
        kat_text += f"  {KATEGORIYALAR.get(k, k)}: `{pul(v)}`\n"
    oy = datetime.now().strftime("%B %Y")
    await msg.answer(
        f"📊 *{oy} hisoboti*\n\n"
        f"💚 Daromad: `{pul(daromad)}`\n"
        f"📉 Chiqim:  `{pul(chiqim)}`\n"
        f"{'✅' if qoldiq >= 0 else '⚠️'} Qoldiq:   `{pul(qoldiq)}`\n\n"
        + (f"📂 *Kategoriyalar:*\n{kat_text}" if kat_text else ""),
        parse_mode="Markdown",
        reply_markup=asosiy_menu()
    )

# ——— SO'NGGI AMALLAR ———
@dp.message(F.text == "📋 So'nggi amallar")
async def songgi_amallar(msg: types.Message):
    amallar = await oxirgi_amallar(msg.from_user.id)
    if not amallar:
        await msg.answer("📭 Hali hech qanday amal yo'q.", reply_markup=asosiy_menu())
        return
    text = "📋 *So'nggi 5 ta amal:*\n\n"
    for a in amallar:
        icon = "💚" if a[2] == "daromad" else "📉"
        kat = KATEGORIYALAR.get(a[4], "") if a[4] else ""
        sana = datetime.strptime(a[6], "%Y-%m-%d").strftime("%d.%m")
        izoh = f" — {a[5]}" if a[5] else ""
        text += f"{icon} `{pul(a[3])}` {kat}{izoh} _{sana}_\n"
    await msg.answer(text, parse_mode="Markdown", reply_markup=asosiy_menu())

# ===================== ISHGA TUSHIRISH =====================
async def main():
    await db_init()
    print("✅ Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
