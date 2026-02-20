"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN')

# DeepSeek API
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')

# OpenAI API (для Vision - анализ чеков)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Database
DATABASE_PATH = os.getenv('DATABASE_PATH', './data/finance.db')

# Admin Users
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

# Проверка обязательных параметров
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env файле")

if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY не установлен в .env файле")
