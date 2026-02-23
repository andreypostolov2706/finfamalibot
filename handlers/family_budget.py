from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, User, Operation, OperationItem, Category, FamilyBudget
from services import DeepSeekService
from keyboards.main_menu import get_main_menu

router = Router()
deepseek = DeepSeekService()


class FamilyBudgetStates(StatesGroup):
    waiting_for_expense = State()
    waiting_for_income = State()
    waiting_for_income_account = State()
    waiting_for_expense_account = State()
    waiting_for_transfer = State()

@router.message(F.text == "Перевести между счетами")
async def transfer_between_accounts(message: types.Message, state: FSMContext):
    """Запрос суммы и направления перевода между картой и наличными"""
    await state.clear()
    session = get_session()
    try:
        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(family_budget)
            session.flush()
        text = (
            f"Перевести между счетами\n"
            f"Баланс: {family_budget.balance:,.2f} ₽\n"
            f"Карта: {family_budget.card_balance:,.2f} ₽\n"
            f"Наличные: {family_budget.cash_balance:,.2f} ₽\n\n"
            f"Введите сумму и направление (например: '100 карта->наличные' или '200 нал->карта')"
        )
        await state.set_state(FamilyBudgetStates.waiting_for_transfer)
        await message.answer(text)
    finally:
        session.close()

@router.message(FamilyBudgetStates.waiting_for_transfer)
async def process_transfer(message: types.Message, state: FSMContext):
    """Обработка перевода между картой и наличными"""
    import re
    session = get_session()
    try:
        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            await message.answer("❌ Бюджет не найден.")
            await state.clear()
            return
        # Парсим сумму и направление
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(карта|нал|наличные)\s*->\s*(карта|нал|наличные)', message.text.lower())
        if not m:
            await message.answer("❌ Формат: '100 карта->наличные' или '200 нал->карта'")
            return
        amount = float(m.group(1).replace(',', '.'))
        from_acc = m.group(2)
        to_acc = m.group(3)
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля.")
            return
        if from_acc.startswith('карта'):
            if (family_budget.card_balance or 0.0) < amount:
                await message.answer(f"❌ Недостаточно средств на карте!\nДоступно: {family_budget.card_balance:,.2f} ₽")
                return
            family_budget.card_balance -= amount
            family_budget.cash_balance = (family_budget.cash_balance or 0.0) + amount
        else:
            if (family_budget.cash_balance or 0.0) < amount:
                await message.answer(f"❌ Недостаточно наличных!\nДоступно: {family_budget.cash_balance:,.2f} ₽")
                return
            family_budget.cash_balance -= amount
            family_budget.card_balance = (family_budget.card_balance or 0.0) + amount
        family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
        session.commit()
        await message.answer(
            f"✅ Перевод выполнен!\n"
            f"Карта: {family_budget.card_balance:,.2f} ₽\n"
            f"Наличные: {family_budget.cash_balance:,.2f} ₽"
        )
        await state.clear()
    finally:
        session.close()
@router.callback_query(F.data.in_(["expense_card", "expense_cash"]))
async def process_expense_account(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора счёта для расхода"""
    session = get_session()
    try:
        data = await state.get_data()
        # Support both single-expense flow (expense_amount/expense_description)
        # and batch flow saved as 'expense_items' + 'expense_total'
        amount = data.get('expense_amount')
        description = data.get('expense_description')
        batch_items = data.get('expense_items')
        batch_total = data.get('expense_total')
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(family_budget)
        if batch_items:
            # Batch flow: user provided multiple lines — enforce chosen account has enough funds
            total = float(batch_total or 0.0)
            if callback.data == "expense_card":
                if (family_budget.card_balance or 0.0) < total:
                    await callback.message.edit_text(
                        f"❌ Недостаточно средств на карте!\n\n"
                        f"Доступно: {family_budget.card_balance:,.2f} ₽\n"
                        f"Требуется: {total:,.2f} ₽"
                    )
                    await state.clear()
                    return
                family_budget.card_balance -= total
                account_used = 'card'
            else:
                if (family_budget.cash_balance or 0.0) < total:
                    await callback.message.edit_text(
                        f"❌ Недостаточно наличных!\n\n"
                        f"Доступно: {family_budget.cash_balance:,.2f} ₽\n"
                        f"Требуется: {total:,.2f} ₽"
                    )
                    await state.clear()
                    return
                family_budget.cash_balance -= total
                account_used = 'cash'

            operation = Operation(
                user_id=user.id,
                type='family_expense',
                total_amount=total,
                account_type=account_used
            )
            session.add(operation)
            session.flush()
            for item in batch_items:
                op_item = OperationItem(
                    operation_id=operation.id,
                    name=item.get('description') or 'Без описания',
                    amount=item.get('amount')
                )
                session.add(op_item)
            family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
            session.commit()
            response = f"✅ Добавлено {len(batch_items)} позиций в семейный бюджет!\n\n"
            response += f"Итого: -{total:,.2f} ₽\n\n"
            response += f"👨‍👩‍👧 Семейный бюджет\n"
            response += f"Баланс: {family_budget.balance:,.2f} ₽ (Карта: {family_budget.card_balance:,.2f} ₽, Наличные: {family_budget.cash_balance:,.2f} ₽)"
            keyboard = [[types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]]
            await callback.message.edit_text(response, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
            await state.clear()
            return

        # Single-item flow (existing behavior)
        # Проверка баланса выбранного счёта
        if amount is None or description is None:
            await callback.answer()
            await state.clear()
            return
        if callback.data == "expense_card":
            if (family_budget.card_balance or 0.0) < amount:
                await callback.message.edit_text(
                    f"❌ Недостаточно средств на карте!\n\n"
                    f"Доступно: {family_budget.card_balance:,.2f} ₽\n"
                    f"Требуется: {amount:,.2f} ₽"
                )
                await state.clear()
                return
            family_budget.card_balance -= amount
            account_used = 'card'
        else:
            if (family_budget.cash_balance or 0.0) < amount:
                await callback.message.edit_text(
                    f"❌ Недостаточно наличных!\n\n"
                    f"Доступно: {family_budget.cash_balance:,.2f} ₽\n"
                    f"Требуется: {amount:,.2f} ₽"
                )
                await state.clear()
                return
            family_budget.cash_balance -= amount
            account_used = 'cash'
        family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
        # Создание операции
        operation = Operation(
            user_id=user.id,
            type='family_expense',
            total_amount=amount,
            account_type=account_used
        )
        session.add(operation)
        session.flush()
        operation_item = OperationItem(
            operation_id=operation.id,
            name=description,
            amount=amount
        )
        session.add(operation_item)
        session.commit()
        response = f"✅ Расход добавлен в семейный бюджет!\n\n"
        response += f"💰 {description}: -{amount:,.2f} ₽\n\n"
        response += f"👨‍👩‍👧 Семейный бюджет\n"
        response += f"Баланс: {family_budget.balance:,.2f} ₽ (Карта: {family_budget.card_balance:,.2f} ₽, Наличные: {family_budget.cash_balance:,.2f} ₽)"
        keyboard = [[types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]]
        await callback.message.edit_text(response, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
    finally:
        session.close()
@router.callback_query(F.data.in_(["income_card", "income_cash"]))
async def process_income_account(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора счёта для дохода"""
    session = get_session()
    try:
        data = await state.get_data()
        amount = data.get('income_amount')
        description = data.get('income_description')
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(family_budget)
        # Создание операции
        operation = Operation(
            user_id=user.id,
            type='family_income',
            total_amount=amount,
            account_type='card' if callback.data == 'income_card' else 'cash'
        )
        session.add(operation)
        session.flush()
        operation_item = OperationItem(
            operation_id=operation.id,
            name=description,
            amount=amount
        )
        session.add(operation_item)
        # Пополнение выбранного счёта
        if callback.data == "income_card":
            family_budget.card_balance = (family_budget.card_balance or 0.0) + amount
        else:
            family_budget.cash_balance = (family_budget.cash_balance or 0.0) + amount
        family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
        session.commit()
        response = f"✅ Доход добавлен в семейный бюджет!\n\n"
        response += f"💵 {description}: +{amount:,.2f} ₽\n\n"
        response += f"👨‍👩‍👧 Семейный бюджет\n"
        response += f"Баланс: {family_budget.balance:,.2f} ₽ (Карта: {family_budget.card_balance:,.2f} ₽, Наличные: {family_budget.cash_balance:,.2f} ₽)"
        keyboard = [[types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]]
        await callback.message.edit_text(response, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
    finally:
        session.close()



@router.message(F.text.in_(["⬅️ Назад", "/menu"]))
async def back_to_main_menu(message: types.Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, используйте /start для регистрации")
            return
        
        # Получение статистики для дашборда
        dashboard_text = await get_dashboard(session, user)
        
        await message.answer(
            dashboard_text,
            reply_markup=get_main_menu()
        )
    finally:
        session.close()


async def get_dashboard(session, user: User) -> str:
    """Формирование дашборда"""
    from database import FixedPayment, FixedPaymentDue, PiggyBank, BusinessAccount, Debt
    from sqlalchemy import func
    from datetime import datetime
    
    # Получение фиксированных платежей
    fixed_payments = session.query(FixedPayment).filter_by(is_active=True).all()

    # Текущий год/месяц — нужны для создания начислений
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Убедимся, что для каждого активного платежа есть запись начисления на текущий месяц
    for p in fixed_payments:
        due = session.query(FixedPaymentDue).filter_by(fixed_payment_id=p.id, year=current_year, month=current_month).first()
        if not due:
            # Создаём начисление (если пропущено настройкой skipped - по умолчанию False)
            due = FixedPaymentDue(
                fixed_payment_id=p.id,
                year=current_year,
                month=current_month,
                due_amount=p.amount,
                paid_amount=0.0,
                is_paid=False,
                skipped=False
            )
            session.add(due)
    session.commit()
    
    # Получение копилок
    business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
    piggy_banks = session.query(PiggyBank).all() if business_account else []

    # Получение расходов за текущий месяц (переменные уже определены выше)
    
    # Расходы по категориям за месяц
    monthly_expenses = session.query(
        Category.name,
        Category.emoji,
        func.sum(OperationItem.amount).label('total')
    ).join(
        OperationItem, Category.id == OperationItem.category_id
    ).join(
        Operation, OperationItem.operation_id == Operation.id
    ).filter(
        Operation.type == 'family_expense',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).group_by(Category.id).all()
    
    # Последние доходы семьи за месяц
    monthly_family_income = session.query(
        func.sum(Operation.total_amount).label('total')
    ).filter(
        Operation.user_id == user.id,
        Operation.type == 'family_income',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).scalar() or 0

    # Суммы доходов по счетам (карта/наличные) за месяц (включая зарплаты и семейные доходы)
    monthly_card_income = session.query(func.sum(Operation.total_amount)).filter(
        Operation.type.in_(['salary', 'family_income']),
        Operation.account_type == 'card',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).scalar() or 0.0

    monthly_cash_income = session.query(func.sum(Operation.total_amount)).filter(
        Operation.type.in_(['salary', 'family_income']),
        Operation.account_type == 'cash',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).scalar() or 0.0

    # Расходы по счетам (карта/наличные) за месяц
    monthly_card_expenses = session.query(func.sum(OperationItem.amount)).join(
        Operation, Operation.id == OperationItem.operation_id
    ).filter(
        Operation.type == 'family_expense',
        Operation.account_type == 'card',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).scalar() or 0.0

    monthly_cash_expenses = session.query(func.sum(OperationItem.amount)).join(
        Operation, Operation.id == OperationItem.operation_id
    ).filter(
        Operation.type == 'family_expense',
        Operation.account_type == 'cash',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).scalar() or 0.0

    # Общий доход (зарплаты + семейные доходы) за месяц
    monthly_total_income = session.query(func.sum(Operation.total_amount)).filter(
        Operation.type.in_(['salary', 'family_income']),
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).scalar() or 0.0
    
    # Зарплаты за месяц (детально)
    salary_ops = session.query(Operation).filter(
        Operation.type == 'salary',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).all()
    monthly_salary = sum(op.total_amount for op in salary_ops)
    
    # Получение общего семейного бюджета
    family_budget = session.query(FamilyBudget).first()
    if not family_budget:
        family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
        session.add(family_budget)
        session.commit()
    
    # Вычисления для дашборда
    import calendar
    today = datetime.now().day
    days_in_month = calendar.monthrange(current_year, current_month)[1]
    
    # Сумма неоплаченных начислений текущего месяца (с учётом частичных оплат)
    dues = session.query(FixedPaymentDue).filter_by(year=current_year, month=current_month).all()
    unpaid_dues = [d for d in dues if not d.is_paid and not d.skipped]
    total_payments = sum(max(0.0, d.due_amount - (d.paid_amount or 0.0)) for d in unpaid_dues)
    total_expenses = sum(total for _, _, total in monthly_expenses)
    avg_per_day = total_expenses / today if today > 0 else 0
    
    # Остаток на день: (баланс - платежи) / оставшиеся дни
    days_left = days_in_month - today + 1
    family_total = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
    daily_budget = (family_total - total_payments) / days_left if days_left > 0 else 0
    
    # Формирование текста дашборда
    text = "🏠 Главная\n\n"
    
    # Семейный бюджет
    text += "👨‍👩‍👧 СЕМЕЙНЫЙ БЮДЖЕТ:\n"
    text += "─────────────\n"
    text += f"Баланс: {family_total:,.2f} ₽ (сумма карта и наличные)\n"
    # Показываем текущие балансы и суммы доходов по счетам за месяц
    text += f"  💳 Карта: {family_budget.card_balance:,.2f} ₽\n"
    text += f"   - доходы: +{monthly_card_income:,.2f} ₽\n"
    text += f"   - расходы: -{monthly_card_expenses:,.2f} ₽\n"
    text += f"  💵 Наличные: {family_budget.cash_balance:,.2f} ₽\n"
    text += f"   - доходы: +{monthly_cash_income:,.2f} ₽\n"
    text += f"   - расходы: -{monthly_cash_expenses:,.2f} ₽\n"
    
    if monthly_salary > 0:
        text += f"Зачисления:\n"
        text += f"Зарплата: +{monthly_salary:,.2f} ₽\n"
        # Детализация по выдаче
        for op in salary_ops:
            op_user = session.query(User).get(op.user_id)
            # Используем явное поле `account_type`, если есть
            account_type = ''
            if op.account_type:
                if op.account_type == 'card':
                    account_type = 'Карта'
                elif op.account_type == 'cash':
                    account_type = 'Наличные'
                elif op.account_type == 'mixed':
                    account_type = 'Смешано'
            name = op_user.name if op_user else f'ID {op.user_id}'
            text += f"  • {name} → {account_type}: {op.total_amount:,.2f} ₽\n"
    if monthly_total_income > 0:
        text += f"Доход: +{monthly_total_income:,.2f} ₽\n"
    text += "\n"
    
    # Платежи — показываем все фиксированные платежи с иконкой статуса для текущего месяца
    if fixed_payments:
        text += "💳 ПЛАТЕЖИ:\n"
        text += "─────────────\n"
        for p in fixed_payments:
            due = session.query(FixedPaymentDue).filter_by(fixed_payment_id=p.id, year=current_year, month=current_month).first()
            if not due:
                status_icon = '❌'
                remaining = p.amount
            else:
                if due.skipped:
                    status_icon = '⏭️'
                    remaining = 0.0
                elif due.is_paid:
                    status_icon = '✅'
                    remaining = 0.0
                else:
                    status_icon = '❌'
                    remaining = max(0.0, due.due_amount - (due.paid_amount or 0.0))

            # Определяем способ оплаты по начислению
            due = session.query(FixedPaymentDue).filter_by(fixed_payment_id=p.id, year=current_year, month=current_month).first()
            pay_method = ""
            if due and due.paid_account_id is None:
                # Если оплачен через FamilyBudget
                if due.paid_amount > 0:
                    if due.paid_at:
                        pay_method = " (Карта)" if (due.paid_at and due.paid_amount and due.paid_account_id is None and (family_budget.card_balance or 0.0) >= due.paid_amount) else " (Наличные)"
            elif due and due.paid_account_id:
                acc = session.query(BusinessAccount).get(due.paid_account_id)
                if acc:
                    pay_method = f" ({acc.name})"
            else:
                pay_method = ""
            text += f"{status_icon} {p.name}: {remaining:,.0f} ₽ (до {p.payment_day} числа){pay_method}\n"

        text += f"Осталось оплатить: {total_payments:,.0f} ₽\n\n"
    
    # Расходы за месяц
    if monthly_expenses:
        text += "📊 РАСХОДЫ ЗА МЕСЯЦ:\n"
        text += "─────────────\n"
        for cat_name, emoji, total in monthly_expenses[:5]:  # Топ 5 категорий
            text += f"{emoji} {cat_name}: {total:,.2f} ₽\n"
        text += f"Общая сумма: {total_expenses:,.2f} ₽\n"
        text += f"Средняя в день: {avg_per_day:,.2f} ₽\n"
        text += "─────────────\n"
        text += f"Остаток на день: {daily_budget:,.2f} ₽\n"
        text += "\n"
    elif fixed_payments:
        # Если нет расходов, но есть платежи - всё равно показываем остаток на день
        text += f"💡 Остаток на день: {daily_budget:,.2f} ₽\n\n"
    
    # Копилки
    if piggy_banks:
        text += "🏦 КОПИЛКИ:\n"
        text += "─────────────\n"
        for piggy in piggy_banks:
            icon = "🔒" if piggy.is_auto else "💰"
            text += f"{icon} {piggy.name}: {piggy.balance:,.2f} ₽\n"
        text += "\n"
    
    # Долги
    active_debts = session.query(Debt).filter_by(user_id=user.id, is_paid=False).all()
    if active_debts:
        owe_me = [d for d in active_debts if d.debt_type == 'owe_me']
        i_owe = [d for d in active_debts if d.debt_type == 'i_owe']
        total_owe_me = sum(d.amount for d in owe_me)
        total_i_owe = sum(d.amount for d in i_owe)
        
        text += "🤝 ДОЛГИ:\n"
        text += "─────────────\n"
        if owe_me:
            text += f"Мне должны: +{total_owe_me:,.2f} ₽ ({len(owe_me)} чел.)\n"
        if i_owe:
            text += f"Я должен: -{total_i_owe:,.2f} ₽ ({len(i_owe)} чел.)\n"
        net = total_owe_me - total_i_owe
        if net > 0:
            text += f"Баланс: +{net:,.2f} ₽\n"
        elif net < 0:
            text += f"Баланс: {net:,.2f} ₽\n"
        text += "\n"
    
    text += "─────────────\n"
    text += "Выберите действие:"
    
    return text


@router.message(FamilyBudgetStates.waiting_for_income)
async def process_family_income(message: types.Message, state: FSMContext):
    """Обработка дохода в семейный бюджет"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        
        # Анализ через DeepSeek
        await message.answer("🤖 Анализирую...")
        
        analysis = deepseek.analyze_expense(message.text, [])
        
        if not analysis.get('amount') or analysis['amount'] <= 0:
            await message.answer(
                "❌ Не могу определить сумму.\n"
                "Попробуйте: '5000 доставка' или просто '5000'"
            )
            return
        
        amount = analysis['amount']
        description = analysis.get('description') or 'Доход'
        
        # Сохраняем сумму и описание во временное состояние
        await state.update_data(income_amount=amount, income_description=description)
        # Запрос выбора счёта
        keyboard = [[
            types.InlineKeyboardButton(text="Карта", callback_data="income_card"),
            types.InlineKeyboardButton(text="Наличные", callback_data="income_cash")
        ]]
        await message.answer(
            f"Выберите счёт для пополнения:\n1. Картой\n2. Наличными",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.set_state(FamilyBudgetStates.waiting_for_income_account)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()
    finally:
        session.close()


@router.message(F.text)
async def handle_text_message(message: types.Message, state: FSMContext):
    """Обработка текстовых сообщений (автоматический анализ расходов)"""
    # Проверка, не является ли это командой меню
    menu_buttons = ["💼 Бизнес", "📋 Операции", "💳 Кредиты", "💰 Копилки", "📊 Статистика"]
    if message.text in menu_buttons:
        return
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, используйте /start для регистрации")
            return
        
        # Получение категорий для анализа
        categories = session.query(Category).filter_by(parent_id=None).all()
        categories_data = []
        for cat in categories:
            subcats = session.query(Category).filter_by(parent_id=cat.id).all()
            categories_data.append({
                "name": cat.name,
                "emoji": cat.emoji or "",
                "subcategories": [sc.name for sc in subcats]
            })
        
        # Разбиваем на строки — поддержка многострочного ввода
        lines = [line.strip() for line in message.text.strip().splitlines() if line.strip()]
        
        # Если одна строка — стандартный анализ через DeepSeek
        # Если несколько строк — парсим каждую строку как "сумма описание"
        if len(lines) == 1:
            items_to_add = await _parse_single_line(lines[0], categories_data)
        else:
            items_to_add = _parse_multiline(lines, categories_data)
        
        if not items_to_add:
            await message.answer(
                "❌ Не могу определить суммы.\n\n"
                "Форматы ввода:\n"
                "• Одна строка: `100 хлеб`\n"
                "• Несколько строк:\n"
                "  `100 хлеб`\n"
                "  `200 молоко`\n"
                "  `50 чай`"
            )
            return
        
        # Получение общего семейного бюджета
        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(family_budget)
            session.flush()

        total_amount = sum(item['amount'] for item in items_to_add)

        # Проверка баланса (карта + наличные)
        family_total = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
        if family_total < total_amount:
            await message.answer(
                f"❌ Недостаточно средств в семейном бюджете!\n\n"
                f"Доступно: {family_total:,.2f} ₽\n"
                f"Требуется: {total_amount:,.2f} ₽\n\n"
                f"Выдайте зарплату из бизнеса для пополнения семейного бюджета."
            )
            return
        
        # Определяем подсказку по счёту (если пользователь указал 'нал'/'карта' в тексте)
        account_hint = _detect_account_type(message.text)
        # Если подсказки по счёту нет — спросим у пользователя (карта/наличные)
        if account_hint is None:
            # Сохраняем подготовленные позиции и сумму в состояние и запрашиваем счёт
            await state.update_data(expense_items=items_to_add, expense_total=total_amount)
            keyboard = [[
                types.InlineKeyboardButton(text="Карта", callback_data="expense_card"),
                types.InlineKeyboardButton(text="Наличные", callback_data="expense_cash")
            ]]
            await message.answer(
                "Выберите счёт для списания:",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            await state.set_state(FamilyBudgetStates.waiting_for_expense_account)
            return

        # Создание одной операции со всеми позициями (есть подсказка по счёту)
        operation = Operation(
            user_id=user.id,
            type='family_expense',
            account_type=account_hint,
            total_amount=total_amount
        )
        session.add(operation)
        session.flush()
        
        for item_data in items_to_add:
            # Поиск категории
            category = None
            if item_data.get('category'):
                category = session.query(Category).filter_by(
                    name=item_data['category'],
                    parent_id=None
                ).first()
            
            op_item = OperationItem(
                operation_id=operation.id,
                name=item_data.get('description') or 'Без описания',
                amount=item_data['amount'],
                category_id=category.id if category else None,
                subcategory=item_data.get('subcategory')
            )
            session.add(op_item)
        
        # Списание из семейного бюджета: порядок списания зависит от подсказки по счёту
        remaining = total_amount
        if account_hint == 'cash':
            # Сначала наличные, затем карта
            if (family_budget.cash_balance or 0.0) >= remaining:
                family_budget.cash_balance -= remaining
                remaining = 0.0
            else:
                remaining -= (family_budget.cash_balance or 0.0)
                family_budget.cash_balance = 0.0
            if remaining > 0:
                family_budget.card_balance = (family_budget.card_balance or 0.0) - remaining
                remaining = 0.0
        else:
            # По умолчанию: сначала карта, затем наличные
            if (family_budget.card_balance or 0.0) >= remaining:
                family_budget.card_balance -= remaining
                remaining = 0.0
            else:
                remaining -= (family_budget.card_balance or 0.0)
                family_budget.card_balance = 0.0
            if remaining > 0:
                family_budget.cash_balance = (family_budget.cash_balance or 0.0) - remaining
                remaining = 0.0
        family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
        session.commit()
        
        # Формирование ответа
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        if len(items_to_add) == 1:
            item = items_to_add[0]
            response = "✅ Расход добавлен в семейный бюджет!\n\n"
            response += f"💰 {item.get('description', 'Без описания')}: {item['amount']:,.2f} ₽\n"
            if item.get('category'):
                response += f"📂 {item['category']}"
                if item.get('subcategory'):
                    response += f" → {item['subcategory']}"
                response += "\n"
        else:
            response = f"✅ Добавлено {len(items_to_add)} позиций в семейный бюджет!\n\n"
            response += "📋 Позиции:\n"
            response += "─────────────\n"
            for item in items_to_add:
                response += f"• {item.get('description', 'Без описания')}: {item['amount']:,.2f} ₽\n"
            response += "─────────────\n"
            response += f"Итого: -{total_amount:,.2f} ₽\n"
        
        response += f"\n👨‍👩‍👧 Семейный бюджет\n"
        response += f"Остаток: {family_budget.balance:,.2f} ₽ (Карта: {family_budget.card_balance:,.2f} ₽, Наличные: {family_budget.cash_balance:,.2f} ₽)"
        
        keyboard = [[InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]]
        await message.answer(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        
    finally:
        session.close()


async def _parse_single_line(line: str, categories_data: list) -> list:
    """Парсинг одной строки через DeepSeek"""
    analysis = deepseek.analyze_expense(line, categories_data)
    if analysis.get('amount') and analysis['amount'] > 0:
        return [analysis]
    return []


def _parse_multiline(lines: list, categories_data: list) -> list:
    """
    Быстрый парсинг нескольких строк без ИИ.
    Формат каждой строки: "сумма описание" или "описание сумма"
    Примеры: "100 хлеб", "молоко 200", "150.50 масло"
    Название товара сохраняется как subcategory для статистики.
    """
    import re
    items = []
    
    for line in lines:
        # Ищем число в строке (сумма)
        match = re.search(r'(\d+(?:[.,]\d+)?)', line)
        if not match:
            continue
        
        amount_str = match.group(1).replace(',', '.')
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        
        if amount <= 0:
            continue
        
        # Описание — всё кроме числа и знаков препинания
        description = re.sub(r'\d+(?:[.,]\d+)?', '', line).strip()
        description = re.sub(r'[,;]', '', description).strip()
        description = re.sub(r'\s+', ' ', description).strip()
        if not description:
            description = f"Расход {amount:.0f}₽"
        
        # Пытаемся определить категорию по ключевым словам
        category_name = _guess_category(description.lower(), categories_data)
        
        items.append({
            "amount": amount,
            "description": description,
            "category": category_name,
            "subcategory": description  # Название товара = подкатегория
        })
    
    return items


def _guess_category(item_name: str, categories_data: list) -> str | None:
    """
    Угадывает категорию по названию товара на основе ключевых слов.
    """
    # Словарь ключевых слов для категорий
    keywords = {
        "Продукты": ["молоко", "хлеб", "картошка", "картофель", "мясо", "рыба", "яйца", "масло",
                     "сыр", "творог", "кефир", "йогурт", "сметана", "колбаса", "сосиски",
                     "макароны", "крупа", "рис", "гречка", "овощи", "фрукты", "сахар", "соль",
                     "мука", "чай", "кофе", "сок", "вода", "пиво", "вино", "курица", "говядина",
                     "свинина", "лук", "морковь", "капуста", "огурец", "помидор", "яблоко",
                     "банан", "апельсин", "шоколад", "конфеты", "печенье", "торт"],
        "Авто": ["бензин", "дизель", "газ", "заправка", "мойка", "запчасти", "масло моторное",
                 "шины", "резина", "аккумулятор", "страховка", "осаго", "каско", "парковка",
                 "штраф", "техосмотр", "ремонт авто", "автосервис"],
        "Одежда": ["куртка", "пальто", "пуховик", "джинсы", "брюки", "рубашка", "футболка",
                   "платье", "юбка", "носки", "нижнее бельё", "бельё", "обувь", "кроссовки",
                   "ботинки", "туфли", "сапоги", "шапка", "шарф", "перчатки", "свитер",
                   "кофта", "пижама", "костюм"],
        "Здоровье": ["лекарства", "таблетки", "витамины", "аптека", "врач", "анализы",
                     "стоматолог", "зубной", "больница", "клиника", "медицина", "маска",
                     "бинт", "пластырь", "мазь", "капли"],
        "Транспорт": ["такси", "метро", "автобус", "трамвай", "троллейбус", "маршрутка",
                      "электричка", "поезд", "самолёт", "билет", "проездной", "uber", "яндекс такси"],
        "Развлечения": ["кино", "театр", "концерт", "ресторан", "кафе", "бар", "клуб",
                        "боулинг", "каток", "аквапарк", "зоопарк", "музей", "выставка"],
        "Коммунальные": ["электричество", "газ", "вода", "интернет", "телефон", "квартплата",
                         "жкх", "отопление", "свет"],
        "Образование": ["учёба", "курсы", "книги", "учебники", "репетитор", "школа", "университет"],
    }
    
    for cat_name, words in keywords.items():
        for word in words:
            if word in item_name:
                # Проверяем что такая категория есть в БД
                for cat in categories_data:
                    if cat['name'].lower() == cat_name.lower():
                        return cat['name']
                return cat_name  # Возвращаем даже если нет в БД
    
    return None


def _detect_account_type(text: str) -> str | None:
    """
    Detects explicit account hint in the user's text.
    Returns 'cash' or 'card' or None.
    """
    if not text:
        return None
    t = text.lower()
    # cash tokens
    cash_tokens = ['нал', 'наличка', 'наличные', 'нал.']
    for tok in cash_tokens:
        if tok in t:
            return 'cash'
    # card tokens
    card_tokens = ['карта', 'карточка', 'visa', 'mastercard']
    for tok in card_tokens:
        if tok in t:
            return 'card'
    return None
