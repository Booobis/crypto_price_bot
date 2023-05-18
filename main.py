import asyncio
import logging

import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import CommandStart
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import Message
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import config

TOKEN = config.token
ADMIN_ID = config.admin_id
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:87.0) Gecko/20100101 Firefox/87.0',
}
BINANCE_MARKETS_URL = 'https://www.binance.com/ru/markets'
BINANCE_MARKETS_URL2 = 'https://www.binance.com/ru/markets/overview?p=2'


class DB:
    def __init__(self):
        self._conn = None

    async def connect(self):
        self._conn = await aiosqlite.connect('users.db')

    async def disconnect(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def create_table(self):
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE
            )
            """
        )
        await self._conn.commit()

    async def add_user(self, user_id):
        cursor = await self._conn.execute(
            """
            SELECT user_id FROM users WHERE user_id=?
            """,
            (user_id,)
        )
        existing_user = await cursor.fetchone()
        if existing_user:
            return

        await self._conn.execute(
            """
            INSERT INTO users (user_id) VALUES (?)
            """,
            (user_id,)
        )
        await self._conn.commit()

    async def get_user_ids(self):
        cursor = await self._conn.execute(
            """
            SELECT user_id FROM users
            """
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


class BinanceMarketPrices:
    def __init__(self):
        self._session = None

    async def get_price(self, money):
        if not self._session:
            self._session = aiohttp.ClientSession(headers=HEADERS)
            print('ok', BINANCE_MARKETS_URL)
        async with self._session.get(BINANCE_MARKETS_URL) as response:
            html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')

        all_crypto = soup.find('div', style='min-height:800px').find_all('div', class_='css-vlibs4')
        print(money)
        for crypto in all_crypto:
            not_full_name = crypto.find('a').find('div').find_next('div').find_next('div')
            full_name = not_full_name.find_next('div').find('div')
            price = crypto.find('div', style='direction:ltr')
            proc = price.find_next('div', style='direction:ltr')
            if money.upper() == not_full_name.text:
                print(money, full_name.text, not_full_name.text)
                return f'Цена: {price.text}\nЦена понижена за день: {proc.text}'

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


class CurrencyStates(StatesGroup):
    waiting_for_currency = State()


class CurrencyConverterBot:
    def __init__(self, token):
        self.bot = Bot(token)
        self.dp = Dispatcher(self.bot, storage=MemoryStorage())
        self.db = DB()
        self.binance_market = BinanceMarketPrices()

    async def on_startup(self, dp):
        await self.db.connect()
        await self.db.create_table()

    async def on_shutdown(self, dp):
        await self.binance_market.close()
        await self.db.disconnect()

    async def start(self):
        self.dp.register_message_handler(self.start_handler, CommandStart())
        self.dp.register_message_handler(self.currency_handler, Text(equals='Курсы валют'))
        self.dp.register_callback_query_handler(self.currency_callback_handler)
        self.dp.register_message_handler(self.send_message_handler, commands=['send'])
        self.dp.register_message_handler(self.process_message_for_broadcasting,
                                         state=CurrencyStates.waiting_for_currency)
        await self.on_startup(self.dp)
        try:
            await self.dp.start_polling()
        finally:
            await self.on_shutdown(self.dp)

    async def start_handler(self, message: Message, state: FSMContext):
        await self.db.add_user(message.chat.id)
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("BTC", callback_data="btc"),
            InlineKeyboardButton("BNB", callback_data="bnb"),
            InlineKeyboardButton("ETH", callback_data="eth"),
        )
        markup.row(
            InlineKeyboardButton("USDT", callback_data="usdt"),
            InlineKeyboardButton("LTC", callback_data="ltc"),
            InlineKeyboardButton("TRX", callback_data="trx"),
        )
        markup.row(
            InlineKeyboardButton("ADA", callback_data="ada"),
            InlineKeyboardButton("DOGE", callback_data="doge"),
            InlineKeyboardButton("SOL", callback_data="sol"),
        )
        await message.reply("Выбери нужную валюту для тебя:", reply_markup=markup)

    async def currency_handler(self, message: Message, state: FSMContext):
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("BTC", callback_data="btc"),
            InlineKeyboardButton("BNB", callback_data="bnb"),
            InlineKeyboardButton("ETH", callback_data="eth"),
        )
        markup.row(
            InlineKeyboardButton("USDT", callback_data="usdt"),
            InlineKeyboardButton("APT", callback_data="apt"),
            InlineKeyboardButton("TRX", callback_data="trx"),
        )
        markup.row(
            InlineKeyboardButton("ADA", callback_data="ada"),
            InlineKeyboardButton("DOGE", callback_data="doge"),
            InlineKeyboardButton("SOL", callback_data="sol"),
        )
        await message.reply("Выбери нужную валюту для тебя:", reply_markup=markup)

    async def currency_callback_handler(self, query: CallbackQuery):
        currency = query.data
        message = query.message
        try:
            price = await self.binance_market.get_price(currency)
        except Exception as e:
            logger.exception(e)
            await message.answer(f"Не удалось получить курс {currency}")
            return
        await message.answer(f"Курс валюты для {currency}:\n{price}")

    async def send_message_handler(self, message: Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("У вас нет доступа к этой команде.")
            return
        await message.answer("Введите текст сообщения для отправки:")
        await CurrencyStates.waiting_for_currency.set()

    async def send_message_to_user(self, user_id: int, text: str) -> None:
        await self.bot.send_message(user_id, text)

    async def broadcast_message(self, text: str) -> None:
        user_ids = await self.db.get_user_ids()
        print(text)
        for user_id in user_ids:
            await self.send_message_to_user(user_id, text)

    async def process_message_for_broadcasting(self, message: Message, state: FSMContext):
        await state.finish()
        text = message.text
        await self.broadcast_message(text)
        await message.answer(f"Сообщение '{text}' было отправлено всем пользователям.")


if __name__ == '__main__':
    bot = CurrencyConverterBot(TOKEN)
    asyncio.run(bot.start())
