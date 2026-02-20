"""
Обработчики для редактирования операций и платежей
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, OperationItem, Operation, FixedPayment, FamilyBudget

router = Router()


class EditStates(StatesGroup):
    """Состояния для редактирования"""
    waiting_for_amount = State()
    waiting_for_name = State()
    # Редактирование платежей
    waiting_for_credit_amount = State()
    waiting_for_credit_name = State()
    waiting_for_credit_day = State()


# ============= РЕДАКТИРОВАНИЕ ОПЕРАЦИЙ =============

@router.message(EditStates.waiting_for_amount)
async def save_new_amount(message: types.Message, state: FSMContext):
    """Сохранение новой суммы"""
    import re
    try:
        numbers = re.findall(r'\d+(?:\.\d+)?', message.text)
        if not numbers:
            await message.answer("❌ Не могу определить сумму. Введите число:")
            return
        
        new_amount = float(numbers[0])
        
        if new_amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля. Введите снова:")
            return
        
        data = await state.get_data()
        item_id = data['item_id']
        
        session = get_session()
        try:
            item = session.query(OperationItem).get(item_id)
            
            if not item:
                await message.answer("❌ Позиция не найдена")
                await state.clear()
                return
            
            old_amount = item.amount
            item.amount = new_amount
            
            operation = item.operation
            amount_diff = new_amount - old_amount
            operation.total_amount = operation.total_amount + amount_diff
            
            from database import User, BusinessAccount, PiggyBank
            user = session.query(User).get(operation.user_id)
            family_budget = session.query(FamilyBudget).first()
            
            if operation.type == 'family_expense':
                if family_budget:
                    family_budget.balance += old_amount
                    family_budget.balance -= new_amount
            elif operation.type == 'family_income':
                if family_budget:
                    family_budget.balance -= old_amount
                    family_budget.balance += new_amount
            elif operation.type == 'business_income':
                business = session.query(BusinessAccount).filter_by(user_id=user.id).first()
                if business:
                    business.balance -= old_amount
                    business.balance += new_amount
            elif operation.type == 'business_expense':
                business = session.query(BusinessAccount).filter_by(user_id=user.id).first()
                if business:
                    business.balance += old_amount
                    business.balance -= new_amount
            elif operation.type == 'salary':
                business = session.query(BusinessAccount).filter_by(user_id=user.id).first()
                piggy = session.query(PiggyBank).filter_by(is_auto=True).first()
                
                business.balance += old_amount
                if family_budget:
                    family_budget.balance -= old_amount * 0.9
                if piggy:
                    piggy.balance -= old_amount * 0.1
                
                business.balance -= new_amount
                if family_budget:
                    family_budget.balance += new_amount * 0.9
                if piggy:
                    piggy.balance += new_amount * 0.1
            
            session.commit()
            
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = [
                [
                    InlineKeyboardButton(text="⬅️ К операции", callback_data=f"op_{operation.id}"),
                    InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")
                ]
            ]
            
            await message.answer(
                f"✅ Сумма изменена!\n\n"
                f"Было: {old_amount:,.2f} ₽\n"
                f"Стало: {new_amount:,.2f} ₽",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            await state.clear()
            
        finally:
            session.close()
        
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:")


@router.message(EditStates.waiting_for_name)
async def save_new_name(message: types.Message, state: FSMContext):
    """Сохранение нового названия с автоопределением категории"""
    new_name = message.text.strip()
    
    if not new_name:
        await message.answer("❌ Название не может быть пустым. Введите снова:")
        return
    
    data = await state.get_data()
    item_id = data['item_id']
    
    session = get_session()
    try:
        item = session.query(OperationItem).get(item_id)
        
        if not item:
            await message.answer("❌ Позиция не найдена")
            await state.clear()
            return
        
        old_name = item.name
        item.name = new_name
        
        from database import Category
        from services import DeepSeekService
        
        categories = session.query(Category).filter_by(parent_id=None).all()
        categories_data = []
        for cat in categories:
            subcats = session.query(Category).filter_by(parent_id=cat.id).all()
            categories_data.append({
                "name": cat.name,
                "emoji": cat.emoji or "",
                "subcategories": [sc.name for sc in subcats]
            })
        
        await message.answer("🤖 Определяю категорию...")
        
        deepseek = DeepSeekService()
        analysis = deepseek.analyze_expense(new_name, categories_data)
        
        if analysis.get('category'):
            category = session.query(Category).filter_by(
                name=analysis['category'],
                parent_id=None
            ).first()
            if category:
                item.category_id = category.id
                item.subcategory = analysis.get('subcategory')
        
        operation = item.operation
        session.commit()
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [
                InlineKeyboardButton(text="⬅️ К операции", callback_data=f"op_{operation.id}"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")
            ]
        ]
        
        response = f"✅ Название изменено!\n\nБыло: {old_name}\nСтало: {new_name}\n"
        
        if item.category:
            cat_text = f"{item.category.emoji} {item.category.name}" if item.category.emoji else item.category.name
            if item.subcategory:
                response += f"\n📂 Категория: {cat_text} → {item.subcategory}"
            else:
                response += f"\n📂 Категория: {cat_text}"
        
        await message.answer(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
        
    finally:
        session.close()


# ============= РЕДАКТИРОВАНИЕ ПЛАТЕЖЕЙ =============

@router.message(EditStates.waiting_for_credit_amount)
async def save_credit_amount(message: types.Message, state: FSMContext):
    """Сохранение новой суммы платежа"""
    import re
    numbers = re.findall(r'\d+(?:\.\d+)?', message.text)
    if not numbers:
        await message.answer("❌ Не могу определить сумму. Введите число:")
        return
    
    new_amount = float(numbers[0])
    if new_amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля. Введите снова:")
        return
    
    data = await state.get_data()
    credit_id = data['credit_id']
    
    session = get_session()
    try:
        credit = session.query(FixedPayment).get(credit_id)
        if not credit:
            await message.answer("❌ Платёж не найден")
            await state.clear()
            return
        
        old_amount = credit.amount
        credit.amount = new_amount
        session.commit()
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [
                InlineKeyboardButton(text="⬅️ К платежу", callback_data=f"credit_{credit_id}"),
                InlineKeyboardButton(text="💳 Платежи", callback_data="menu_credits")
            ]
        ]
        
        await message.answer(
            f"✅ Сумма платежа изменена!\n\n"
            f"Было: {old_amount:,.2f} ₽\n"
            f"Стало: {new_amount:,.2f} ₽",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.clear()
        
    finally:
        session.close()


@router.message(EditStates.waiting_for_credit_name)
async def save_credit_name(message: types.Message, state: FSMContext):
    """Сохранение нового названия платежа"""
    new_name = message.text.strip()
    if not new_name:
        await message.answer("❌ Название не может быть пустым. Введите снова:")
        return
    
    data = await state.get_data()
    credit_id = data['credit_id']
    
    session = get_session()
    try:
        credit = session.query(FixedPayment).get(credit_id)
        if not credit:
            await message.answer("❌ Платёж не найден")
            await state.clear()
            return
        
        old_name = credit.name
        credit.name = new_name
        session.commit()
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [
                InlineKeyboardButton(text="⬅️ К платежу", callback_data=f"credit_{credit_id}"),
                InlineKeyboardButton(text="💳 Платежи", callback_data="menu_credits")
            ]
        ]
        
        await message.answer(
            f"✅ Название платежа изменено!\n\n"
            f"Было: {old_name}\n"
            f"Стало: {new_name}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.clear()
        
    finally:
        session.close()


@router.message(EditStates.waiting_for_credit_day)
async def save_credit_day(message: types.Message, state: FSMContext):
    """Сохранение нового дня оплаты"""
    import re
    numbers = re.findall(r'\d+', message.text)
    if not numbers:
        await message.answer("❌ Введите число от 1 до 31:")
        return
    
    new_day = int(numbers[0])
    if not 1 <= new_day <= 31:
        await message.answer("❌ День должен быть от 1 до 31. Введите снова:")
        return
    
    data = await state.get_data()
    credit_id = data['credit_id']
    
    session = get_session()
    try:
        credit = session.query(FixedPayment).get(credit_id)
        if not credit:
            await message.answer("❌ Платёж не найден")
            await state.clear()
            return
        
        old_day = credit.payment_day
        credit.payment_day = new_day
        session.commit()
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [
                InlineKeyboardButton(text="⬅️ К платежу", callback_data=f"credit_{credit_id}"),
                InlineKeyboardButton(text="💳 Платежи", callback_data="menu_credits")
            ]
        ]
        
        await message.answer(
            f"✅ День оплаты изменён!\n\n"
            f"Было: {old_day} число\n"
            f"Стало: {new_day} число",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.clear()
        
    finally:
        session.close()
