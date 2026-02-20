"""
Обработчики для управления кредитами
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, FixedPayment
from keyboards.main_menu import get_credits_menu, get_main_menu

router = Router()


class CreditStates(StatesGroup):
    """Состояния для работы с кредитами"""
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_day = State()
    selecting_credit_to_edit = State()
    editing_credit = State()
    editing_field = State()


@router.message(F.text == "💳 Кредиты")
async def show_credits_menu(message: types.Message, state: FSMContext):
    """Показать меню кредитов"""
    await state.clear()
    
    session = get_session()
    try:
        # Получение всех активных кредитов
        credits = session.query(FixedPayment).filter_by(is_active=True).all()
        
        text = "💳 Кредиты\n\n"
        
        if credits:
            text += "Активные кредиты:\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n"
            for i, credit in enumerate(credits, 1):
                text += f"{i}. {credit.name}\n"
                text += f"   Сумма: {credit.amount:,.2f} ₽\n"
                text += f"   День оплаты: {credit.payment_day} число\n\n"
        else:
            text += "У вас пока нет кредитов.\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += "Выберите действие:"
        
        await message.answer(text, reply_markup=get_credits_menu())
        
    finally:
        session.close()


@router.message(F.text == "➕ Добавить кредит")
async def add_credit_start(message: types.Message, state: FSMContext):
    """Начать добавление кредита"""
    await state.set_state(CreditStates.waiting_for_name)
    await message.answer(
        "➕ Добавление кредита\n\n"
        "Введите название кредита:\n"
        "(например: 'Сбербанк', 'Квартира', 'Автокредит')"
    )


@router.message(CreditStates.waiting_for_name)
async def add_credit_name(message: types.Message, state: FSMContext):
    """Получение названия кредита"""
    await state.update_data(name=message.text)
    await state.set_state(CreditStates.waiting_for_amount)
    await message.answer(
        f"Название: {message.text}\n\n"
        "Введите сумму ежемесячного платежа:"
    )


@router.message(CreditStates.waiting_for_amount)
async def add_credit_amount(message: types.Message, state: FSMContext):
    """Получение суммы кредита"""
    try:
        import re
        numbers = re.findall(r'\d+(?:\.\d+)?', message.text)
        if not numbers:
            await message.answer("❌ Не могу определить сумму. Введите число:")
            return
        
        amount = float(numbers[0])
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля. Введите снова:")
            return
        
        await state.update_data(amount=amount)
        await state.set_state(CreditStates.waiting_for_day)
        await message.answer(
            f"Сумма: {amount:,.2f} ₽\n\n"
            "Введите день месяца для оплаты (1-31):"
        )
        
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:")


@router.message(CreditStates.waiting_for_day)
async def add_credit_day(message: types.Message, state: FSMContext):
    """Получение дня оплаты"""
    try:
        day = int(message.text)
        if day < 1 or day > 31:
            await message.answer("❌ День должен быть от 1 до 31. Введите снова:")
            return
        
        # Получение данных из состояния
        data = await state.get_data()
        
        # Сохранение в базу
        session = get_session()
        try:
            credit = FixedPayment(
                name=data['name'],
                amount=data['amount'],
                payment_day=day
            )
            session.add(credit)
            session.commit()
            
            await message.answer(
                "✅ Кредит добавлен!\n\n"
                f"Название: {data['name']}\n"
                f"Сумма: {data['amount']:,.2f} ₽\n"
                f"День оплаты: {day} число",
                reply_markup=get_credits_menu()
            )
            await state.clear()
            
        finally:
            session.close()
        
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число от 1 до 31:")


@router.message(F.text == "✏️ Редактировать кредит")
async def edit_credit_start(message: types.Message, state: FSMContext):
    """Начать редактирование кредита"""
    session = get_session()
    try:
        credits = session.query(FixedPayment).filter_by(is_active=True).all()
        
        if not credits:
            await message.answer("У вас нет кредитов для редактирования.")
            return
        
        text = "✏️ Редактирование кредита\n\n"
        text += "Выберите кредит (введите номер):\n\n"
        
        for i, credit in enumerate(credits, 1):
            text += f"{i}. {credit.name} - {credit.amount:,.2f} ₽\n"
        
        await state.set_state(CreditStates.selecting_credit_to_edit)
        await state.update_data(credits=[c.id for c in credits])
        await message.answer(text)
        
    finally:
        session.close()


@router.message(CreditStates.selecting_credit_to_edit)
async def edit_credit_select(message: types.Message, state: FSMContext):
    """Выбор кредита для редактирования"""
    try:
        index = int(message.text) - 1
        data = await state.get_data()
        credit_ids = data['credits']
        
        if index < 0 or index >= len(credit_ids):
            await message.answer("❌ Неверный номер. Попробуйте снова:")
            return
        
        credit_id = credit_ids[index]
        
        session = get_session()
        try:
            credit = session.query(FixedPayment).get(credit_id)
            
            text = f"Кредит: {credit.name}\n\n"
            text += "Что изменить?\n\n"
            text += "1. Название\n"
            text += "2. Сумму\n"
            text += "3. День оплаты\n\n"
            text += "Введите номер:"
            
            await state.update_data(editing_credit_id=credit_id)
            await state.set_state(CreditStates.editing_credit)
            await message.answer(text)
            
        finally:
            session.close()
        
    except ValueError:
        await message.answer("❌ Введите номер кредита:")


@router.message(CreditStates.editing_credit)
async def edit_credit_field_select(message: types.Message, state: FSMContext):
    """Выбор поля для редактирования"""
    field_map = {
        "1": "name",
        "2": "amount",
        "3": "payment_day"
    }
    
    field = field_map.get(message.text)
    if not field:
        await message.answer("❌ Неверный выбор. Введите 1, 2 или 3:")
        return
    
    await state.update_data(editing_field=field)
    await state.set_state(CreditStates.editing_field)
    
    prompts = {
        "name": "Введите новое название:",
        "amount": "Введите новую сумму:",
        "payment_day": "Введите новый день оплаты (1-31):"
    }
    
    await message.answer(prompts[field])


@router.message(CreditStates.editing_field)
async def edit_credit_save(message: types.Message, state: FSMContext):
    """Сохранение изменений"""
    data = await state.get_data()
    field = data['editing_field']
    credit_id = data['editing_credit_id']
    
    session = get_session()
    try:
        credit = session.query(FixedPayment).get(credit_id)
        
        if field == "name":
            credit.name = message.text
        elif field == "amount":
            try:
                import re
                numbers = re.findall(r'\d+(?:\.\d+)?', message.text)
                if not numbers:
                    await message.answer("❌ Не могу определить сумму. Попробуйте снова:")
                    return
                credit.amount = float(numbers[0])
            except ValueError:
                await message.answer("❌ Неверный формат. Попробуйте снова:")
                return
        elif field == "payment_day":
            try:
                day = int(message.text)
                if day < 1 or day > 31:
                    await message.answer("❌ День должен быть от 1 до 31. Попробуйте снова:")
                    return
                credit.payment_day = day
            except ValueError:
                await message.answer("❌ Неверный формат. Введите число:")
                return
        
        session.commit()
        
        await message.answer(
            "✅ Кредит обновлён!\n\n"
            f"Название: {credit.name}\n"
            f"Сумма: {credit.amount:,.2f} ₽\n"
            f"День оплаты: {credit.payment_day} число",
            reply_markup=get_credits_menu()
        )
        await state.clear()
        
    finally:
        session.close()


@router.message(F.text == "🗑️ Удалить кредит")
async def delete_credit(message: types.Message):
    """Удаление кредита"""
    session = get_session()
    try:
        credits = session.query(FixedPayment).filter_by(is_active=True).all()
        
        if not credits:
            await message.answer("У вас нет кредитов для удаления.")
            return
        
        text = "🗑️ Удаление кредита\n\n"
        text += "Выберите кредит для удаления (введите номер):\n\n"
        
        for i, credit in enumerate(credits, 1):
            text += f"{i}. {credit.name} - {credit.amount:,.2f} ₽\n"
        
        await message.answer(text)
        
    finally:
        session.close()
