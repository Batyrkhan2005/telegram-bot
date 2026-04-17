#!/usr/bin/env python
# coding: utf-8

# In[1]:


get_ipython().system('pip install aiogram aiosqlite apscheduler')


# In[ ]:


import asyncio
import nest_asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiosqlite
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Патч для работы в Jupyter
nest_asyncio.apply()

# Замените токен на новый (после отзыва старого)
TOKEN = "8774071198:AAEZ0baDm2bj6cUhLzBWU6PQkJS4j2kBMfI"

# --- КАТЕГОРИИ ---
categories = {
    "Фантастика": ["Dune", "Foundation", "Neuromancer"],
    "Классика": ["1984", "Crime and Punishment"],
    "Фэнтези": ["The Hobbit", "Lord of the Rings"]
}

PER_PAGE = 5

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("books.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            author TEXT,
            status TEXT,
            user_id INTEGER,
            deadline TEXT
        )
        """)
        await db.commit()

# --- ДОБАВИТЬ КНИГИ ---
async def seed_books():
    async with aiosqlite.connect("books.db") as db:
        books = await db.execute("SELECT COUNT(*) FROM books")
        count = (await books.fetchone())[0]

        if count == 0:
            await db.executemany("""
            INSERT INTO books (title, author, status)
            VALUES (?, ?, 'free')
            """, [
                ("1984", "George Orwell"),
                ("The Hobbit", "J.R.R. Tolkien"),
                ("Crime and Punishment", "Dostoevsky")
            ])
            await db.commit()

# --- СПИСОК КНИГ ---
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Категории", callback_data="categories")],
        [InlineKeyboardButton(text="📖 Мои книги", callback_data="my_books")]
    ])

async def books_menu(cat_name, page=0):
    async with aiosqlite.connect("books.db") as db:
        cursor = await db.execute("SELECT title FROM books WHERE status='taken'")
        taken_books = [b[0] for b in await cursor.fetchall()]

    books = categories[cat_name]
    start = page * PER_PAGE
    end = start + PER_PAGE

    kb = []

    for book in books[start:end]:
        if book in taken_books:
            kb.append([InlineKeyboardButton(text=f"❌ {book}", callback_data="none")])
        else:
            kb.append([InlineKeyboardButton(text=f"📗 {book}", callback_data=f"book|{book}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"books|{cat_name}|{page-1}"))
    if end < len(books):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"books|{cat_name}|{page+1}"))

    if nav:
        kb.append(nav)

    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="categories")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

async def my_books_menu(user_id):
    async with aiosqlite.connect("books.db") as db:
        cursor = await db.execute("""
        SELECT id, title FROM books WHERE user_id=?
        """, (user_id,))
        books = await cursor.fetchall()

    kb = []

    for b in books:
        kb.append([
            InlineKeyboardButton(
                text=f"❌ Отменить: {b[1]}",
                callback_data=f"cancel|{b[0]}"
            )
        ])

    kb.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

def categories_menu():
    kb = []
    for cat in categories:
        kb.append([InlineKeyboardButton(text=f"📖 {cat}", callback_data=f"cat|{cat}")])
    kb.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("books"))
async def show_books(message: types.Message):
    async with aiosqlite.connect("books.db") as db:
        cursor = await db.execute("SELECT id, title, author, status FROM books")
        books = await cursor.fetchall()

    text = "📚 Список книг:\n\n"
    for b in books:
        status = "✅ Свободна" if b[3] == "free" else "❌ Занята"
        text += f"{b[0]}. {b[1]} — {b[2]} ({status})\n"

    await message.answer(text)

# --- БРОНЬ ---
@dp.message(Command("reserve"))
async def reserve_book(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используй: /reserve ID")
        return
    
    try:
        book_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    async with aiosqlite.connect("books.db") as db:
        cursor = await db.execute("SELECT status FROM books WHERE id=?", (book_id,))
        book = await cursor.fetchone()

        if not book:
            await message.answer("Книга не найдена")
            return

        if book[0] == "taken":
            await message.answer("❌ Уже занята")
            return

        deadline = datetime.now() + timedelta(days=7)

        await db.execute("""
        UPDATE books
        SET status='taken', user_id=?, deadline=?
        WHERE id=?
        """, (message.from_user.id, deadline.isoformat(), book_id))
        await db.commit()

    await message.answer(f"✅ Забронировано до {deadline.date()}")

# --- ВОЗВРАТ ---
@dp.message(Command("return"))
async def return_book(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используй: /return ID")
        return
    
    try:
        book_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    async with aiosqlite.connect("books.db") as db:
        await db.execute("""
        UPDATE books
        SET status='free', user_id=NULL, deadline=NULL
        WHERE id=?
        """, (book_id,))
        await db.commit()

    await message.answer("📖 Книга возвращена")
    
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = call.data

    if data == "categories":
        await call.message.edit_text("Выберите категорию:", reply_markup=categories_menu())

    elif data.startswith("cat|"):
        cat_name = data.split("|")[1]
        kb = await books_menu(cat_name, 0)
        await call.message.edit_text(f"📚 {cat_name}", reply_markup=kb)

    elif data.startswith("books|"):
        _, cat_name, page = data.split("|")
        kb = await books_menu(cat_name, int(page))
        await call.message.edit_text(f"📚 {cat_name}", reply_markup=kb)

    elif data.startswith("book|"):
        book_name = data.split("|")[1]

        async with aiosqlite.connect("books.db") as db:
            deadline = datetime.now() + timedelta(days=7)

            await db.execute("""
            UPDATE books
            SET status='taken', user_id=?, deadline=?
            WHERE title=?
            """, (user_id, deadline.isoformat(), book_name))
            await db.commit()

        await call.answer("Забронировано!")
        await call.message.answer(f"✅ {book_name} забронирована до {deadline.date()}")

    elif data == "my_books":
        kb = await my_books_menu(user_id)
        await call.message.edit_text("📖 Ваши книги:", reply_markup=kb)

    elif data.startswith("cancel|"):
        book_id = int(data.split("|")[1])

        async with aiosqlite.connect("books.db") as db:
            await db.execute("""
            UPDATE books
            SET status='free', user_id=NULL, deadline=NULL
            WHERE id=?
            """, (book_id,))
            await db.commit()

        await call.answer("Отменено")
        kb = await my_books_menu(user_id)
        await call.message.edit_text("📖 Ваши книги:", reply_markup=kb)

    elif data == "back_main":
        await call.message.edit_text("Главное меню:", reply_markup=main_menu())

    elif data == "none":
        await call.answer("Книга занята ❌", show_alert=True)

# --- ПРОВЕРКА ДЕДЛАЙНОВ ---
async def check_deadlines():
    async with aiosqlite.connect("books.db") as db:
        cursor = await db.execute("""
        SELECT id, user_id, deadline FROM books
        WHERE status='taken'
        """)
        books = await cursor.fetchall()

    now = datetime.now()
    for b in books:
        if not b[2]: continue
        deadline = datetime.fromisoformat(b[2])
        diff = (deadline - now).days

        if diff == 0: # Напоминание в день дедлайна
            await bot.send_message(b[1], f"⏰ Сегодня дедлайн книги ID {b[0]}!")

        if deadline < now:
            async with aiosqlite.connect("books.db") as db:
                await db.execute("""
                UPDATE books
                SET status='free', user_id=NULL, deadline=NULL
                WHERE id=?
                """, (b[0],))
                await db.commit()
            await bot.send_message(b[1], f"❗ Срок истёк. Книга ID {b[0]} освобождена")

# --- СТАРТ ---
async def main():
    await init_db()
    await seed_books()

    scheduler.add_job(check_deadlines, "interval", hours=1)
    scheduler.start()

    print("Бот запущен...")
    await dp.start_polling(bot)

# Запуск в Jupyter
await main()


# In[ ]:




