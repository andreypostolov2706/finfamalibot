"""
Главный файл телеграм бота для учёта финансов с поддержкой вебхуков
"""
import asyncio
import logging
import ssl
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
from database import init_db
from handlers import start, family_budget, business, credits, piggy_banks, operations, callbacks, edit_operations, receipt, debts

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Действия при запуске бота"""
    if config.WEBHOOK_URL:
        await bot.set_webhook(
            url=config.WEBHOOK_URL,
            # certificate=ssl.CERT_NONE,  # Раскомментируйте если используете SSL
            drop_pending_updates=True
        )
        logger.info(f"Webhook установлен: {config.WEBHOOK_URL}")
    else:
        logger.info("Webhook не настроен, используется polling")


async def on_shutdown(bot: Bot) -> None:
    """Действия при остановке бота"""
    if config.WEBHOOK_URL:
        await bot.delete_webhook()
        logger.info("Webhook удалён")
    await bot.session.close()


def create_app() -> web.Application:
    """Создание aiohttp приложения для вебхуков"""
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
    
    # Настройка startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создание aiohttp приложения
    app = web.Application()
    
    if config.WEBHOOK_URL:
        # Установка вебхука
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        )
        
        # Регистрация webhook пути
        webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
        
        # Настройка приложения
        setup_application(app, dp, bot=bot)
        
        logger.info(f"Вебхук приложение создано для пути: {config.WEBHOOK_PATH}")
    else:
        logger.info("Режим polling активирован")
    
    return app


async def main():
    """Главная функция запуска бота"""
    app = create_app()
    
    if config.WEBHOOK_URL:
        # Запуск веб-сервера для вебхуков
        logger.info(f"Запуск веб-сервера на {config.WEBAPP_HOST}:{config.WEBAPP_PORT}")
        await web._run_app(
            app,
            host=config.WEBAPP_HOST,
            port=config.WEBAPP_PORT,
            print=lambda *args: None  # Отключаем стандартный вывод
        )
    else:
        # Запуск в режиме polling
        logger.info("Бот запущен в режиме polling")
        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
