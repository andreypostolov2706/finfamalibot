"""
Обработчики для управления копилками
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, User, BusinessAccount, PiggyBank, FamilyBudget
from keyboards.main_menu import get_piggy_menu, get_main_menu

router = Router()


class PiggyStates(StatesGroup):
    """Состояния для работы с копилками"""
    waiting_for_piggy_name = State()
    selecting_piggy_to_deposit = State()
    waiting_for_deposit_amount = State()
    selecting_piggy_to_withdraw = State()
    waiting_for_withdraw_amount = State()


@router.message(F.text == "💰 Копилки")
async def show_piggy_menu(message: types.Message, state: FSMContext):
    """Показать меню копилок"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, используйте /start для регистрации")
            return
        
        # Получение всех копилок
        piggy_banks = session.query(PiggyBank).all()
        
        text = "💰 Копилки\n\n"
        
        if piggy_banks:
            for piggy in piggy_banks:
                icon = "🔒" if piggy.is_auto else "💰"
                text += f"{icon} {piggy.name}\n"
                text += f"   Баланс: {piggy.balance:,.2f} ₽\n"
                if piggy.is_auto:
                    text += "   (автоматическая)\n"
                text += "\n"
            
            total = sum(p.balance for p in piggy_banks)
            text += "━━━━━━━━━━━━━━━━━━━━\n"
            text += f"Всего накоплено: {total:,.2f} ₽\n\n"
        else:
            text += "У вас пока нет копилок.\n\n"
        
        text += "Выберите действие:"
        
        await message.answer(text, reply_markup=get_piggy_menu())
        
    finally:
        session.close()


@router.message(F.text == "➕ Создать копилку")
async def create_piggy_start(message: types.Message, state: FSMContext):
    """Начать создание копилки"""
    await state.set_state(PiggyStates.waiting_for_piggy_name)
    await message.answer(
        "➕ Создание копилки\n\n"
        "Введите название копилки:\n"
        "(например: 'На море', 'На машину', 'На ремонт')"
    )


@router.message(PiggyStates.waiting_for_piggy_name)
async def create_piggy_save(message: types.Message, state: FSMContext):
    """Сохранение новой копилки"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
        
        # Создание копилки
        piggy = PiggyBank(
            business_account_id=business_account.id if business_account else None,
            name=message.text,
            is_auto=False
        )
        session.add(piggy)
        session.commit()
        
        await message.answer(
            f"✅ Копилка '{message.text}' создана!\n\n"
            "Баланс: 0.00 ₽",
            reply_markup=get_piggy_menu()
        )
        await state.clear()
        
    finally:
        session.close()


@router.message(F.text == "💰 Пополнить копилку")
async def deposit_piggy_start(message: types.Message, state: FSMContext):
    """Начать пополнение копилки"""
    session = get_session()
    try:
        piggy_banks = session.query(PiggyBank).all()
        
        if not piggy_banks:
            await message.answer("У вас нет копилок. Создайте копилку сначала.")
            return
        
        text = "💰 Пополнение копилки\n\n"
        text += "Выберите копилку (введите номер):\n\n"
        
        for i, piggy in enumerate(piggy_banks, 1):
            icon = "🔒" if piggy.is_auto else "💰"
            text += f"{i}. {icon} {piggy.name} ({piggy.balance:,.2f} ₽)\n"
        
        await state.set_state(PiggyStates.selecting_piggy_to_deposit)
        await state.update_data(piggy_banks=[p.id for p in piggy_banks])
        await message.answer(text)
        
    finally:
        session.close()


@router.message(PiggyStates.selecting_piggy_to_deposit)
async def deposit_piggy_select(message: types.Message, state: FSMContext):
    """Выбор копилки для пополнения"""
    try:
        index = int(message.text) - 1
        data = await state.get_data()
        piggy_ids = data['piggy_banks']
        
        if index < 0 or index >= len(piggy_ids):
            await message.answer("❌ Неверный номер. Попробуйте снова:")
            return
        
        piggy_id = piggy_ids[index]
        
        session = get_session()
        try:
            piggy = session.query(PiggyBank).get(piggy_id)
            
            await state.update_data(piggy_id=piggy_id)
            await state.set_state(PiggyStates.waiting_for_deposit_amount)
            await message.answer(
                f"Копилка: {piggy.name}\n"
                f"Текущий баланс: {piggy.balance:,.2f} ₽\n\n"
                "Введите сумму для пополнения:"
            )
            
        finally:
            session.close()
        
    except ValueError:
        await message.answer("❌ Введите номер копилки:")


@router.message(PiggyStates.waiting_for_deposit_amount)
async def deposit_piggy_save(message: types.Message, state: FSMContext):
    """Сохранение пополнения"""
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
        
        data = await state.get_data()
        piggy_id = data['piggy_id']
        
        session = get_session()
        try:
            user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
            piggy = session.query(PiggyBank).get(piggy_id)
            
            # Получение общего семейного бюджета
            family_budget = session.query(FamilyBudget).first()
            if not family_budget:
                family_budget = FamilyBudget(balance=0.0)
                session.add(family_budget)
            
            # Проверка баланса семейного бюджета
            if family_budget.balance < amount:
                await message.answer(
                    f"❌ Недостаточно средств в семейном бюджете!\n\n"
                    f"Доступно: {family_budget.balance:,.2f} ₽\n"
                    f"Требуется: {amount:,.2f} ₽\n\n"
                    f"Выдайте зарплату из бизнеса для пополнения семейного бюджета."
                )
                await state.clear()
                return
            
            # Списание из общего семейного бюджета
            family_budget.balance -= amount
            
            # Пополнение копилки
            piggy.balance += amount
            session.commit()
            
            await message.answer(
                f"✅ Копилка пополнена!\n\n"
                f"Копилка: {piggy.name}\n"
                f"Пополнение: +{amount:,.2f} ₽\n"
                f"Баланс копилки: {piggy.balance:,.2f} ₽\n\n"
                f"👨‍👩‍👧 Семейный бюджет\n"
                f"Остаток: {family_budget.balance:,.2f} ₽",
                reply_markup=get_piggy_menu()
            )
            await state.clear()
            
        finally:
            session.close()
        
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:")


@router.message(F.text == "💸 Снять из копилки")
async def withdraw_piggy_start(message: types.Message, state: FSMContext):
    """Начать снятие из копилки"""
    session = get_session()
    try:
        # Получение копилок, кроме автоматической
        piggy_banks = session.query(PiggyBank).all()
        
        if not piggy_banks:
            await message.answer("У вас нет копилок.")
            return
        
        text = "💸 Снятие из копилки\n\n"
        text += "Выберите копилку (введите номер):\n\n"
        
        for i, piggy in enumerate(piggy_banks, 1):
            icon = "🔒" if piggy.is_auto else "💰"
            text += f"{i}. {icon} {piggy.name} ({piggy.balance:,.2f} ₽)\n"
        
        await state.set_state(PiggyStates.selecting_piggy_to_withdraw)
        await state.update_data(piggy_banks=[p.id for p in piggy_banks])
        await message.answer(text)
        
    finally:
        session.close()


@router.message(PiggyStates.selecting_piggy_to_withdraw)
async def withdraw_piggy_select(message: types.Message, state: FSMContext):
    """Выбор копилки для снятия"""
    try:
        index = int(message.text) - 1
        data = await state.get_data()
        piggy_ids = data['piggy_banks']
        
        if index < 0 or index >= len(piggy_ids):
            await message.answer("❌ Неверный номер. Попробуйте снова:")
            return
        
        piggy_id = piggy_ids[index]
        
        session = get_session()
        try:
            piggy = session.query(PiggyBank).get(piggy_id)
            
            await state.update_data(piggy_id=piggy_id)
            await state.set_state(PiggyStates.waiting_for_withdraw_amount)
            await message.answer(
                f"Копилка: {piggy.name}\n"
                f"Доступно: {piggy.balance:,.2f} ₽\n\n"
                "Введите сумму для снятия:"
            )
            
        finally:
            session.close()
        
    except ValueError:
        await message.answer("❌ Введите номер копилки:")


@router.message(PiggyStates.waiting_for_withdraw_amount)
async def withdraw_piggy_save(message: types.Message, state: FSMContext):
    """Сохранение снятия"""
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
        
        data = await state.get_data()
        piggy_id = data['piggy_id']
        
        session = get_session()
        try:
            user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
            piggy = session.query(PiggyBank).get(piggy_id)
            
            if piggy.balance < amount:
                await message.answer(
                    f"❌ Недостаточно средств!\n\n"
                    f"Доступно: {piggy.balance:,.2f} ₽\n"
                    f"Требуется: {amount:,.2f} ₽"
                )
                await state.clear()
                return
            
            # Снятие из копилки
            piggy.balance -= amount
            
            # Возврат в общий семейный бюджет
            family_budget = session.query(FamilyBudget).first()
            if not family_budget:
                family_budget = FamilyBudget(balance=0.0)
                session.add(family_budget)
            family_budget.balance += amount
            session.commit()
            
            await message.answer(
                f"✅ Средства сняты!\n\n"
                f"Копилка: {piggy.name}\n"
                f"Снято: -{amount:,.2f} ₽\n"
                f"Остаток копилки: {piggy.balance:,.2f} ₽\n\n"
                f"👨‍👩‍👧 Семейный бюджет\n"
                f"Баланс: {family_budget.balance:,.2f} ₽ (+{amount:,.2f} ₽)",
                reply_markup=get_piggy_menu()
            )
            await state.clear()
            
        finally:
            session.close()
        
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:")
