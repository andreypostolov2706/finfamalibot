"""
Обработчики для бизнеса
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, User, BusinessAccount, Operation, OperationItem, Category, PiggyBank
from services import DeepSeekService
from keyboards.main_menu import get_business_menu, get_main_menu

router = Router()
deepseek = DeepSeekService()


class BusinessStates(StatesGroup):
    """Состояния для работы с бизнесом"""
    waiting_for_income = State()
    waiting_for_expense = State()
    waiting_for_salary = State()
    waiting_for_salary_account = State()


@router.message(BusinessStates.waiting_for_income)
async def process_income(message: types.Message, state: FSMContext):
    """Обработка дохода в бизнес"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
        
        # Получение категорий для анализа
        categories = session.query(Category).filter(
            Category.name.in_(['Продажи', 'Закупки', 'Операционные расходы'])
        ).all()
        categories_data = []
        for cat in categories:
            subcats = session.query(Category).filter_by(parent_id=cat.id).all()
            categories_data.append({
                "name": cat.name,
                "emoji": cat.emoji or "",
                "subcategories": [sc.name for sc in subcats]
            })
        
        # Анализ через DeepSeek
        await message.answer("🤖 Анализирую...")
        
        analysis = deepseek.analyze_expense(message.text, categories_data)
        
        if not analysis.get('amount') or analysis['amount'] <= 0:
            await message.answer(
                "❌ Не могу определить сумму.\n"
                "Попробуйте ещё раз:"
            )
            return
        
        # Поиск категории
        category = None
        subcategory_name = analysis.get('subcategory')
        
        if analysis.get('category'):
            category = session.query(Category).filter_by(
                name=analysis['category'],
                parent_id=None
            ).first()
        
        # Создание операции
        operation = Operation(
            user_id=user.id,
            type='business_income',
            total_amount=analysis['amount']
        )
        session.add(operation)
        session.flush()
        
        # Создание позиции
        operation_item = OperationItem(
            operation_id=operation.id,
            name=analysis.get('description') or 'Доход',
            amount=analysis['amount'],
            category_id=category.id if category else None,
            subcategory=subcategory_name
        )
        session.add(operation_item)
        
        # Обновление баланса бизнеса
        business_account.balance += analysis['amount']
        session.commit()
        
        # Формирование ответа
        response = "✅ Доход добавлен в бизнес!\n\n"
        response += f"Сумма: {analysis['amount']:,.2f} ₽\n"
        if category:
            cat_text = f"{category.emoji} {category.name}" if category.emoji else category.name
            if subcategory_name:
                response += f"Категория: {cat_text} → {subcategory_name}\n"
            else:
                response += f"Категория: {cat_text}\n"
        response += f"\n💼 Бизнес: {business_account.name}\n"
        response += f"Баланс: {business_account.balance:,.2f} ₽"
        
        # Кнопки навигации
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [
                InlineKeyboardButton(text="⬅️ Назад в бизнес", callback_data="menu_business"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")
            ]
        ]
        
        await message.answer(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
        
    finally:
        session.close()


@router.message(BusinessStates.waiting_for_expense)
async def process_expense(message: types.Message, state: FSMContext):
    """Обработка расхода в бизнесе"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
        
        # Получение категорий для анализа
        categories = session.query(Category).filter(
            Category.name.in_(['Продажи', 'Закупки', 'Операционные расходы'])
        ).all()
        categories_data = []
        for cat in categories:
            subcats = session.query(Category).filter_by(parent_id=cat.id).all()
            categories_data.append({
                "name": cat.name,
                "emoji": cat.emoji or "",
                "subcategories": [sc.name for sc in subcats]
            })
        
        # Анализ через DeepSeek
        await message.answer("🤖 Анализирую...")
        
        analysis = deepseek.analyze_expense(message.text, categories_data)
        
        if not analysis.get('amount') or analysis['amount'] <= 0:
            await message.answer(
                "❌ Не могу определить сумму.\n"
                "Попробуйте ещё раз:"
            )
            return
        
        # Проверка баланса
        if business_account.balance < analysis['amount']:
            await message.answer(
                f"❌ Недостаточно средств!\n\n"
                f"Баланс: {business_account.balance:,.2f} ₽\n"
                f"Требуется: {analysis['amount']:,.2f} ₽"
            )
            await state.clear()
            return
        
        # Поиск категории
        category = None
        subcategory_name = analysis.get('subcategory')
        
        if analysis.get('category'):
            category = session.query(Category).filter_by(
                name=analysis['category'],
                parent_id=None
            ).first()
        
        # Создание операции
        operation = Operation(
            user_id=user.id,
            type='business_expense',
            total_amount=analysis['amount']
        )
        session.add(operation)
        session.flush()
        
        # Создание позиции
        operation_item = OperationItem(
            operation_id=operation.id,
            name=analysis.get('description') or 'Расход',
            amount=analysis['amount'],
            category_id=category.id if category else None,
            subcategory=subcategory_name
        )
        session.add(operation_item)
        
        # Обновление баланса бизнеса
        business_account.balance -= analysis['amount']
        session.commit()
        
        # Формирование ответа
        response = "✅ Расход добавлен в бизнес!\n\n"
        response += f"Сумма: {analysis['amount']:,.2f} ₽\n"
        if category:
            cat_text = f"{category.emoji} {category.name}" if category.emoji else category.name
            if subcategory_name:
                response += f"Категория: {cat_text} → {subcategory_name}\n"
            else:
                response += f"Категория: {cat_text}\n"
        response += f"\n💼 Бизнес: {business_account.name}\n"
        response += f"Баланс: {business_account.balance:,.2f} ₽"
        
        # Кнопки навигации
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [
                InlineKeyboardButton(text="⬅️ Назад в бизнес", callback_data="menu_business"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")
            ]
        ]
        
        await message.answer(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
        
    finally:
        session.close()


@router.message(BusinessStates.waiting_for_salary)
async def process_salary(message: types.Message, state: FSMContext):
    """Обработка выдачи зарплаты"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
        import re
        numbers = re.findall(r'\d+(?:\.\d+)?', message.text)
        if not numbers:
            await message.answer("❌ Не могу определить сумму. Введите число:")
            return
        salary_amount = float(numbers[0])
        if salary_amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля")
            return
        if business_account.balance < salary_amount:
            await message.answer(
                f"❌ Недостаточно средств!\n\n"
                f"Баланс: {business_account.balance:,.2f} ₽\n"
                f"Требуется: {salary_amount:,.2f} ₽"
            )
            await state.clear()
            return
        # Сохраняем сумму во временное состояние и спрашиваем счет
        await state.update_data(salary_amount=salary_amount)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton(text="Карта", callback_data="salary_account_card")],
            [InlineKeyboardButton(text="Наличные", callback_data="salary_account_cash")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_business")]
        ]
        await state.set_state(BusinessStates.waiting_for_salary_account)
        await message.answer(
            f"Куда зачислить 90% зарплаты ({salary_amount*0.9:,.2f} ₽)?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    finally:
        session.close()

@router.callback_query(F.data.startswith("salary_account_"))
async def process_salary_account(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора счета для зарплаты"""
    data = await state.get_data()
    salary_amount = data.get("salary_amount")
    if not salary_amount:
        await callback.answer("Ошибка: не найдена сумма.", show_alert=True)
        await state.clear()
        return
    account_type = callback.data.split("_")[-1]  # card/cash
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
        piggy_amount = salary_amount * 0.1
        family_amount = salary_amount * 0.9
        # Создание операции зарплаты
        operation = Operation(
            user_id=user.id,
            type='salary',
            total_amount=salary_amount,
            account_type='card' if account_type=='card' else 'cash'
        )
        session.add(operation)
        session.flush()
        operation_item = OperationItem(
            operation_id=operation.id,
            name=f"Выдача зарплаты ({'Карта' if account_type=='card' else 'Наличные'})",
            amount=salary_amount
        )
        session.add(operation_item)
        # Обновление баланса бизнеса
        business_account.balance -= salary_amount
        # Пополнение семейного бюджета (90%)
        from database import FamilyBudget
        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(family_budget)
        if account_type == 'card':
            family_budget.card_balance = (family_budget.card_balance or 0.0) + family_amount
        else:
            family_budget.cash_balance = (family_budget.cash_balance or 0.0) + family_amount
        family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
        # Пополнение копилки "Шекель 10%" (10%)
        piggy_bank = session.query(PiggyBank).filter_by(is_auto=True).first()
        if piggy_bank:
            piggy_bank.balance += piggy_amount
        session.commit()
        # Формирование ответа
        response = "✅ Зарплата выдана!\n\n"
        response += f"💼 Бизнес: {business_account.name}\n"
        response += f"Баланс: {business_account.balance:,.2f} ₽ (-{salary_amount:,.2f} ₽)\n\n"
        response += f"👨‍👩‍👧 Семейный бюджет\n"
        response += f"{'Карта' if account_type=='card' else 'Наличные'}: +{family_amount:,.2f} ₽\n"
        response += f"Баланс: {family_budget.balance:,.2f} ₽\n\n"
        response += f"🔒 Копилка 'Шекель 10%'\n"
        if piggy_bank:
            response += f"Баланс: {piggy_bank.balance:,.2f} ₽ (+{piggy_amount:,.2f} ₽)"
        else:
            response += f"Создайте копилку 'Шекель 10%' для автоматических отчислений."
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton(text="⬅️ Назад в бизнес", callback_data="menu_business"),
             InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ]
        await callback.message.answer(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
    finally:
        session.close()
