"""
💰 Hisob-Kitob Telegram Bot
Kutubxona: aiogram 3.x
O'rnatish: pip install aiogram aiosqlite
"""

import asyncio
import aiosqlite
import logging
from datetime import datetime, date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
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
    tur = State()
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
    if oy is None:
        oy = datetime.now().month
    if yil is None:
        yil = datetime.now().year
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

# ===================== FORMAT =====================
def pul(n):
    return f"{int(n):,} so'm".replace(",", " ")

# ===================== HANDLERLAR =====================
@dp.message(Command("start"))
async def start(msg: types.Message):
    await db_init()
    await msg.answer(
        f"Salom, {msg.from_user.first_name}! 👋\n\n"
        "💰 *Hisob-Kitob Botiga xush kelibsiz!*\n\n"
        "Bu bot sizning daromad va chiqimlaringizni kuzatib boradi.\n\n"
        "Quyidagi tugmalardan foydalaning 👇",
        parse_mode="Markdown",
        reply_markup=asosiy_menu()
    )

@dp.message(F.text == "ℹ️ Yordam")
async def yordam(msg: types.Message):
    await msg.answer(
        "📖 *Qo'llanma:*\n\n"
        "➕ *Chiqim qo'shish* — xarajat kiriting\n"
        "💚 *Daromad qo'shish* — daromad kiriting\n"
        "📊 *Hisobot* — bu oyning xulosasi\n"
        "📋 *So'nggi amallar* — oxirgi 5 ta amal\n\n"
        "❌ Istalgan vaqt bekor qilish uchun 'Bekor qilish' tugmasini bosing.",
        parse_mode="Markdown"
    )

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

# ——— SUMMA ———
@dp.message(Qoshish.summa)
async def summa_qabul(msg: types.Message, state: FSMContext):
    text = msg.text.replace(" ", "").replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await msg.answer("⚠️ Iltimos, to'g'ri summa kiriting!\n\nMasalan: `50000`", parse_mode="Markdown")
        return
    await state.update_data(summa=int(text))
    data = await state.get_data()
    if data["tur"] == "chiqim":
        await state.set_state(Qoshish.kategoriya)
        await msg.answer("📂 Kategoriyani tanlang:", reply_markup=kategoriya_menu())
    else:
        await state.set_state(Qoshish.izoh)
        await msg.answer("📝 Izoh kiriting (yoki /skip bosing):", reply_markup=bekor_menu())

# ——— KATEGORIYA ———
@dp.callback_query(F.data.startswith("kat_"), Qoshish.kategoriya)
async def kategoriya_qabul(call: types.CallbackQuery, state: FSMContext):
    kat = call.data.replace("kat_", "")
    await state.update_data(kategoriya=kat)
    await state.set_state(Qoshish.izoh)
    await call.message.edit_text(f"✅ Kategoriya: {KATEGORIYALAR[kat]}")
    await call.message.answer("📝 Izoh kiriting yoki /skip bosing:", reply_markup=bekor_menu())

# ——— IZOH ———
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

    # Kategoriya bo'yicha
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
