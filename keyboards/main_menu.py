"""
Клавиатуры главного меню
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [
            InlineKeyboardButton(text="➕ Доход", callback_data="family_income"),
            InlineKeyboardButton(text="📋 Операции", callback_data="menu_operations")
        ],
        [
            InlineKeyboardButton(text="💼 Бизнес", callback_data="menu_business"),
            InlineKeyboardButton(text="💰 Копилки", callback_data="menu_piggy")
        ],
        [
            InlineKeyboardButton(text="💳 Платежи", callback_data="menu_credits"),
            InlineKeyboardButton(text="🤝 Долги", callback_data="menu_debts")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu_stats")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_business_menu() -> InlineKeyboardMarkup:
    """Меню бизнеса"""
    keyboard = [
        [
            InlineKeyboardButton(text="➕ Доход", callback_data="business_income"),
            InlineKeyboardButton(text="➖ Расход", callback_data="business_expense")
        ],
        [
            InlineKeyboardButton(text="💵 Выдать зарплату", callback_data="business_salary")
        ],
        [
            InlineKeyboardButton(text="📋 Операции бизнеса", callback_data="business_operations")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_credits_menu() -> InlineKeyboardMarkup:
    """Меню кредитов"""
    keyboard = [
        [
            InlineKeyboardButton(text="➕ Добавить кредит", callback_data="credit_add")
        ],
        [
            InlineKeyboardButton(text="✏️ Редактировать кредит", callback_data="credit_edit"),
            InlineKeyboardButton(text="🗑️ Удалить кредит", callback_data="credit_delete")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_piggy_menu() -> InlineKeyboardMarkup:
    """Меню копилок"""
    keyboard = [
        [
            InlineKeyboardButton(text="➕ Создать копилку", callback_data="piggy_create")
        ],
        [
            InlineKeyboardButton(text="💰 Пополнить копилку", callback_data="piggy_deposit"),
            InlineKeyboardButton(text="💸 Снять из копилки", callback_data="piggy_withdraw")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
