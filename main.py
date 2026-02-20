"""
Главный файл телеграм бота для учёта финансов
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database import init_db
from handlers import start, family_budget, business, credits, piggy_banks, operations, callbacks, edit_operations, receipt, debts

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота"""
    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("База данных инициализирована")
    
    # Создание бота и диспетчера
    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрация обработчиков (порядок важен!)
    dp.include_router(start.router)
    dp.include_router(receipt.router)       # Чеки (фото) - раньше текстовых
    dp.include_router(callbacks.router)     # Callback обработчики
    dp.include_router(edit_operations.router)  # Редактирование операций
    dp.include_router(business.router)
    dp.include_router(credits.router)
    dp.include_router(piggy_banks.router)
    dp.include_router(debts.router)
    dp.include_router(operations.router)
    dp.include_router(family_budget.router)  # Последним - обрабатывает все текстовые сообщения
    
    # Запуск бота
    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
