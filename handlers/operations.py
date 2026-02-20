"""
Обработчики для просмотра и редактирования операций
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, User, Operation, OperationItem, Category
from keyboards.main_menu import get_main_menu
from datetime import datetime

router = Router()


class OperationStates(StatesGroup):
    """Состояния для работы с операциями"""
    viewing_operation = State()
    selecting_item_to_edit = State()
    editing_item_field = State()
    editing_item_value = State()


@router.message(F.text == "📋 Операции")
async def show_operations(message: types.Message, state: FSMContext):
    """Показать историю операций"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, используйте /start для регистрации")
            return
        
        # Получение последних 10 операций
        operations = session.query(Operation).filter_by(
            user_id=user.id
        ).order_by(Operation.created_at.desc()).limit(10).all()
        
        if not operations:
            await message.answer(
                "📋 История операций\n\n"
                "У вас пока нет операций.",
                reply_markup=get_main_menu()
            )
            return
        
        text = "📋 История операций\n\n"
        
        current_date = None
        for op in operations:
            op_date = op.created_at.strftime("%d.%m.%Y")
            
            # Группировка по датам
            if op_date != current_date:
                if current_date is not None:
                    text += "\n"
                text += f"{op_date}:\n"
                text += "━━━━━━━━━━━━━━━━━━━━\n"
                current_date = op_date
            
            # Иконка в зависимости от типа
            icons = {
                'family_expense': '🛒',
                'business_income': '💰',
                'business_expense': '💸',
                'salary': '💵',
                'piggy_deposit': '🏦',
                'piggy_withdraw': '💸'
            }
            icon = icons.get(op.type, '📝')
            
            # Название операции
            type_names = {
                'family_expense': 'Расход (семья)',
                'business_income': 'Доход (бизнес)',
                'business_expense': 'Расход (бизнес)',
                'salary': 'Зарплата',
                'piggy_deposit': 'Пополнение копилки',
                'piggy_withdraw': 'Снятие из копилки'
            }
            type_name = type_names.get(op.type, 'Операция')
            
            time_str = op.created_at.strftime("%H:%M")
            items_count = len(op.items)
            
            text += f"{icon} {type_name}\n"
            text += f"   {time_str} | {op.total_amount:,.2f} ₽\n"
            text += f"   {items_count} {'позиция' if items_count == 1 else 'позиций'}\n"
            text += f"   ID: {op.id}\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += "Для просмотра деталей введите ID операции"
        
        await message.answer(text)
        
    finally:
        session.close()


@router.message(F.text == "📋 Операции бизнеса")
async def show_business_operations(message: types.Message, state: FSMContext):
    """Показать операции бизнеса"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, используйте /start для регистрации")
            return
        
        # Получение операций бизнеса
        operations = session.query(Operation).filter(
            Operation.user_id == user.id,
            Operation.type.in_(['business_income', 'business_expense', 'salary'])
        ).order_by(Operation.created_at.desc()).limit(10).all()
        
        if not operations:
            await message.answer(
                "📋 Операции бизнеса\n\n"
                "У вас пока нет операций в бизнесе."
            )
            return
        
        text = "💼 Операции бизнеса\n\n"
        
        current_date = None
        for op in operations:
            op_date = op.created_at.strftime("%d.%m.%Y")
            
            if op_date != current_date:
                if current_date is not None:
                    text += "\n"
                text += f"{op_date}:\n"
                text += "━━━━━━━━━━━━━━━━━━━━\n"
                current_date = op_date
            
            icons = {
                'business_income': '💰',
                'business_expense': '💸',
                'salary': '💵'
            }
            icon = icons.get(op.type, '📝')
            
            type_names = {
                'business_income': 'Доход',
                'business_expense': 'Расход',
                'salary': 'Зарплата'
            }
            type_name = type_names.get(op.type, 'Операция')
            
            time_str = op.created_at.strftime("%H:%M")
            sign = '+' if op.type == 'business_income' else '-'
            
            text += f"{icon} {type_name}\n"
            text += f"   {time_str} | {sign}{op.total_amount:,.2f} ₽\n"
            text += f"   ID: {op.id}\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += "Для просмотра деталей введите ID операции"
        
        await message.answer(text)
        
    finally:
        session.close()


@router.message(F.text.regexp(r'^\d+$'))
async def view_operation_details(message: types.Message, state: FSMContext):
    """Просмотр деталей операции по ID"""
    operation_id = int(message.text)
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        operation = session.query(Operation).filter_by(
            id=operation_id,
            user_id=user.id
        ).first()
        
        if not operation:
            return  # Не наша операция или не существует
        
        # Формирование детального описания
        type_names = {
            'family_expense': '🛒 Расход (семья)',
            'business_income': '💰 Доход (бизнес)',
            'business_expense': '💸 Расход (бизнес)',
            'salary': '💵 Зарплата',
            'piggy_deposit': '🏦 Пополнение копилки',
            'piggy_withdraw': '💸 Снятие из копилки'
        }
        
        text = f"{type_names.get(operation.type, 'Операция')}\n"
        text += f"{operation.created_at.strftime('%d.%m.%Y, %H:%M')}\n\n"
        
        if operation.items:
            text += "Позиции:\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n"
            
            for i, item in enumerate(operation.items, 1):
                text += f"{i}. {item.name}\n"
                text += f"   {item.amount:,.2f} ₽"
                
                if item.category:
                    cat_text = f" | {item.category.emoji} {item.category.name}" if item.category.emoji else f" | {item.category.name}"
                    if item.subcategory:
                        cat_text += f" → {item.subcategory}"
                    text += cat_text
                
                text += "\n"
                text += f"   [ID позиции: {item.id}]\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += f"Общая сумма: {operation.total_amount:,.2f} ₽\n\n"
        text += "Для редактирования позиции введите её ID"
        
        await message.answer(text)
        
    finally:
        session.close()
