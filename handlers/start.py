"""
Обработчик команды /start
"""
from aiogram import Router, types
from aiogram.filters import Command
from database import get_session, User, BusinessAccount, PiggyBank

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    session = get_session()
    try:
        # Проверка, зарегистрирован ли пользователь
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        
        if not user:
            # Регистрация нового пользователя
            user = User(
                telegram_id=message.from_user.id,
                name=message.from_user.full_name
            )
            session.add(user)
            session.flush()
            
            # Создание бизнес-аккаунта
            business_account = BusinessAccount(
                user_id=user.id,
                name=f"Бизнес {user.name}"
            )
            session.add(business_account)
            session.flush()
            
            # Проверяем - существует ли уже копилка "Шекель 10%" (для второго пользователя)
            existing_piggy = session.query(PiggyBank).filter_by(is_auto=True, name="Шекель 10%").first()
            
            if not existing_piggy:
                # Создаём копилку только для первого пользователя
                piggy_bank = PiggyBank(
                    business_account_id=business_account.id,
                    name="Шекель 10%",
                    is_auto=True
                )
                session.add(piggy_bank)
                piggy_msg = "\n✅ Создана автоматическая копилка 'Шекель 10%'"
            else:
                piggy_msg = ""
            
            session.commit()
            
            await message.answer(
                f"🎉 Добро пожаловать, {user.name}!\n\n"
                f"✅ Создан бизнес-аккаунт{piggy_msg}"
            )
        
        # Показать главное меню для всех
        from handlers.family_budget import get_dashboard
        from keyboards.main_menu import get_main_menu
        
        dashboard_text = await get_dashboard(session, user)
        await message.answer(dashboard_text, reply_markup=get_main_menu())
    finally:
        session.close()


@router.message(Command("menu"))
async def cmd_menu(message: types.Message, state=None):
    """Возврат в главное меню"""
    # Очистка состояния если есть
    if state:
        await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, используйте /start для регистрации")
            return
        
        from handlers.family_budget import get_dashboard
        from keyboards.main_menu import get_main_menu
        
        dashboard_text = await get_dashboard(session, user)
        await message.answer(dashboard_text, reply_markup=get_main_menu())
        
    finally:
        session.close()


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state=None):
    """Отмена текущей операции"""
    if state:
        current_state = await state.get_state()
        if current_state is not None:
            await state.clear()
            await message.answer(
                "❌ Операция отменена.\n\n"
                "Используйте /menu для возврата в главное меню."
            )
        else:
            await message.answer("Нет активных операций для отмены.")
    else:
        await message.answer("Нет активных операций для отмены.")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработка команды /help"""
    help_text = """
📖 Справка по боту

🏠 Команды:
/start - Регистрация/вход
/menu - Главное меню
/cancel - Отменить текущую операцию
/help - Справка

💼 Бизнес:
• Доход - добавление дохода в бизнес
• Расход - расход бизнеса
• Зарплата - 90% в семью, 10% в копилку

👨‍👩‍👧 Семейный бюджет:
Просто напишите в чат:
"100 рублей шоколадка" - добавит расход
Деньги списываются из семейного бюджета

📋 Операции:
Просмотр истории всех операций

💳 Кредиты:
Управление фиксированными платежами

💰 Копилки:
• Создать копилку
• Пополнить (из семейного бюджета)
• Снять (возврат в семейный бюджет)

📊 Статистика:
Расходы по категориям за месяц

💡 Советы:
• /menu - вернуться в главное меню
• /cancel - отменить ввод данных
"""
    await message.answer(help_text)
