"""
Обработчики callback для инлайн-кнопок
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database import get_session, User, BusinessAccount, FixedPayment, FixedPaymentDue, PiggyBank, Operation, OperationItem, Category, FamilyBudget
from keyboards.main_menu import get_main_menu, get_business_menu, get_credits_menu, get_piggy_menu
from handlers.family_budget import get_dashboard

router = Router()


@router.callback_query(F.data == "menu_main")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        if not user:
            await callback.message.answer("Пожалуйста, используйте /start для регистрации")
            await callback.answer()
            return
        
        dashboard_text = await get_dashboard(session, user)
        
        await callback.message.edit_text(
            dashboard_text,
            reply_markup=get_main_menu()
        )
        await callback.answer()
        
    finally:
        session.close()


# ============= СЕМЕЙНЫЙ ДОХОД =============

@router.callback_query(F.data == "family_income")
async def callback_family_income(callback: CallbackQuery, state: FSMContext):
    """Начать добавление дохода в семейный бюджет"""
    from handlers.family_budget import FamilyBudgetStates
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    await state.set_state(FamilyBudgetStates.waiting_for_income)

    keyboard = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_main")]
    ]

    # Редактируем текущее сообщение, чтобы сохранить контекст меню
    try:
        await callback.message.edit_text(
            "💵 Введите доход в семейный бюджет:\n\n"
            "Например: '5000 доставка'\n"
            "или просто: '5000'",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception:
        # Фоллбек — если редактирование не удалось, отправим новое сообщение
        await callback.message.answer(
            "💵 Введите доход в семейный бюджет:\n\n"
            "Например: '5000 доставка'\n"
            "или просто: '5000'",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    await callback.answer()


# ============= БИЗНЕС ДЕЙСТВИЯ =============

@router.callback_query(F.data == "business_income")
async def callback_business_income(callback: CallbackQuery, state: FSMContext):
    """Начать добавление дохода в бизнес"""
    from handlers.business import BusinessStates
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    await state.set_state(BusinessStates.waiting_for_income)
    
    keyboard = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_business")]
    ]
    
    await callback.message.answer(
        "💰 Введите доход в бизнес:\n\n"
        "Например: '5000 продажа телефона'\n"
        "или просто: '5000'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data == "business_expense")
async def callback_business_expense(callback: CallbackQuery, state: FSMContext):
    """Начать добавление расхода в бизнес"""
    from handlers.business import BusinessStates
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    await state.set_state(BusinessStates.waiting_for_expense)
    
    keyboard = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_business")]
    ]
    
    await callback.message.answer(
        "💸 Введите расход бизнеса:\n\n"
        "Например: '2000 закупка товара'\n"
        "или просто: '2000'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data == "business_salary")
async def callback_business_salary(callback: CallbackQuery, state: FSMContext):
    """Начать выдачу зарплаты"""
    from handlers.business import BusinessStates
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    await state.set_state(BusinessStates.waiting_for_salary)
    
    keyboard = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_business")]
    ]
    
    await callback.message.answer(
        "💵 Введите сумму зарплаты:\n\n"
        "Например: '50000'\n\n"
        "10% автоматически пойдёт в копилку 'Шекель 10%'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


# ============= КРЕДИТЫ ДЕЙСТВИЯ =============

@router.callback_query(F.data == "credit_add")
async def callback_credit_add(callback: CallbackQuery, state: FSMContext):
    """Начать добавление кредита"""
    from handlers.credits import CreditStates
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    await state.set_state(CreditStates.waiting_for_name)
    
    keyboard = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_credits")]
    ]
    
    await callback.message.answer(
        "➕ Добавление кредита\n\n"
        "Введите название кредита:\n"
        "(например: 'Сбербанк', 'Квартира', 'Автокредит')",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data == "credit_edit")
async def callback_credit_edit(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование кредита"""
    session = get_session()
    try:
        credits = session.query(FixedPayment).filter_by(is_active=True).all()
        
        if not credits:
            await callback.message.answer("У вас нет кредитов для редактирования.")
            await callback.answer()
            return
        
        text = "✏️ Редактирование кредита\n\n"
        text += "Выберите кредит (введите номер):\n\n"
        
        for i, credit in enumerate(credits, 1):
            text += f"{i}. {credit.name} - {credit.amount:,.2f} ₽\n"
        
        from handlers.credits import CreditStates
        await state.set_state(CreditStates.selecting_credit_to_edit)
        await state.update_data(credits=[c.id for c in credits])
        await callback.message.answer(text)
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "credit_delete")
async def callback_credit_delete(callback: CallbackQuery, state: FSMContext):
    """Удаление кредита"""
    session = get_session()
    try:
        credits = session.query(FixedPayment).filter_by(is_active=True).all()
        
        if not credits:
            await callback.message.answer("У вас нет кредитов для удаления.")
            await callback.answer()
            return
        
        text = "🗑️ Удаление кредита\n\n"
        text += "Выберите кредит для удаления (введите номер):\n\n"
        
        for i, credit in enumerate(credits, 1):
            text += f"{i}. {credit.name} - {credit.amount:,.2f} ₽\n"
        
        await callback.message.answer(text)
        await callback.answer()
        
    finally:
        session.close()


# ============= КОПИЛКИ ДЕЙСТВИЯ =============

@router.callback_query(F.data == "piggy_create")
async def callback_piggy_create(callback: CallbackQuery, state: FSMContext):
    """Начать создание копилки"""
    from handlers.piggy_banks import PiggyStates
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    await state.set_state(PiggyStates.waiting_for_piggy_name)
    
    keyboard = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_piggy")]
    ]
    
    await callback.message.answer(
        "➕ Создание копилки\n\n"
        "Введите название копилки:\n"
        "(например: 'На море', 'На машину', 'На ремонт')",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data == "piggy_deposit")
async def callback_piggy_deposit(callback: CallbackQuery, state: FSMContext):
    """Начать пополнение копилки"""
    session = get_session()
    try:
        piggy_banks = session.query(PiggyBank).all()
        
        if not piggy_banks:
            await callback.message.answer("У вас нет копилок. Создайте копилку сначала.")
            await callback.answer()
            return
        
        text = "💰 Пополнение копилки\n\n"
        text += "Выберите копилку (введите номер):\n\n"
        
        for i, piggy in enumerate(piggy_banks, 1):
            icon = "🔒" if piggy.is_auto else "💰"
            text += f"{i}. {icon} {piggy.name} ({piggy.balance:,.2f} ₽)\n"
        
        from handlers.piggy_banks import PiggyStates
        await state.set_state(PiggyStates.selecting_piggy_to_deposit)
        await state.update_data(piggy_banks=[p.id for p in piggy_banks])
        await callback.message.answer(text)
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "piggy_withdraw")
async def callback_piggy_withdraw(callback: CallbackQuery, state: FSMContext):
    """Начать снятие из копилки"""
    session = get_session()
    try:
        piggy_banks = session.query(PiggyBank).all()
        
        if not piggy_banks:
            await callback.message.answer("У вас нет копилок.")
            await callback.answer()
            return
        
        text = "💸 Снятие из копилки\n\n"
        text += "Выберите копилку (введите номер):\n\n"
        
        for i, piggy in enumerate(piggy_banks, 1):
            icon = "🔒" if piggy.is_auto else "💰"
            text += f"{i}. {icon} {piggy.name} ({piggy.balance:,.2f} ₽)\n"
        
        from handlers.piggy_banks import PiggyStates
        await state.set_state(PiggyStates.selecting_piggy_to_withdraw)
        await state.update_data(piggy_banks=[p.id for p in piggy_banks])
        await callback.message.answer(text)
        await callback.answer()
        
    finally:
        session.close()


# ============= СТАТИСТИКА =============

def _get_month_name(month: int) -> str:
    months = ["Январь","Февраль","Март","Апрель","Май","Июнь",
              "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
    return months[month - 1]


@router.callback_query(F.data == "menu_stats")
async def callback_stats_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню статистики"""
    await state.clear()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from datetime import datetime
    
    now = datetime.now()
    month_name = _get_month_name(now.month)
    
    keyboard = [
        [InlineKeyboardButton(text="👨‍👩‍👧 Семейный бюджет", callback_data="stats_family")],
        [InlineKeyboardButton(text="💼 Бизнес", callback_data="stats_business")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]
    ]
    
    await callback.message.edit_text(
        f"📊 Статистика\n\n"
        f"Текущий период: {month_name} {now.year}\n\n"
        f"Выберите раздел:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data == "stats_family")
async def callback_stats_family(callback: CallbackQuery, state: FSMContext):
    """Статистика семейного бюджета"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from sqlalchemy import func
    from datetime import datetime
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        now = datetime.now()
        month = now.month
        year = now.year
        month_name = _get_month_name(month)
        
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
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).group_by(Category.id).order_by(func.sum(OperationItem.amount).desc()).all()
        
        # Расходы без категории
        no_cat_expenses = session.query(
            func.sum(OperationItem.amount).label('total')
        ).join(
            Operation, OperationItem.operation_id == Operation.id
        ).filter(
            Operation.type == 'family_expense',
            OperationItem.category_id == None,
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).scalar() or 0
        
        # Доходы за месяц
        monthly_income = session.query(
            func.sum(Operation.total_amount)
        ).filter(
            Operation.user_id == user.id,
            Operation.type.in_(['family_income', 'salary']),
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).scalar() or 0
        
        # Расходы за прошлый месяц (для сравнения)
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        prev_expenses = session.query(
            func.sum(OperationItem.amount)
        ).join(
            Operation, OperationItem.operation_id == Operation.id
        ).filter(
            Operation.type == 'family_expense',
            func.strftime('%m', Operation.created_at) == f'{prev_month:02d}',
            func.strftime('%Y', Operation.created_at) == str(prev_year)
        ).scalar() or 0
        
        # Количество операций за месяц
        ops_count = session.query(func.count(Operation.id)).filter(
            Operation.user_id == user.id,
            Operation.type == 'family_expense',
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).scalar() or 0
        
        total_expenses = sum(t for _, _, t in monthly_expenses) + no_cat_expenses
        
        import calendar
        days_in_month = calendar.monthrange(year, month)[1]
        today = now.day
        avg_per_day = total_expenses / today if today > 0 else 0
        projected = avg_per_day * days_in_month
        
        text = f"👨‍👩‍👧 Семейный бюджет — {month_name} {year}\n\n"
        
        # Доходы
        text += "💵 ДОХОДЫ:\n"
        text += "─────────────\n"
        text += f"Итого: +{monthly_income:,.2f} ₽\n\n"
        
        # Расходы по категориям
        text += "💸 РАСХОДЫ ПО КАТЕГОРИЯМ:\n"
        text += "─────────────\n"
        
        if monthly_expenses:
            for cat_name, emoji, cat_amount in monthly_expenses:
                pct = (cat_amount / total_expenses * 100) if total_expenses > 0 else 0
                bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                emoji_str = f"{emoji} " if emoji else ""
                text += f"{emoji_str}{cat_name}\n"
                text += f"  {bar} {cat_amount:,.0f}₽ ({pct:.0f}%)\n"
                
                # Подкатегории
                subcats = session.query(
                    OperationItem.subcategory,
                    func.sum(OperationItem.amount).label('sub_total')
                ).join(
                    Operation, OperationItem.operation_id == Operation.id
                ).join(
                    Category, OperationItem.category_id == Category.id
                ).filter(
                    Operation.type == 'family_expense',
                    Category.name == cat_name,
                    OperationItem.subcategory != None,
                    func.strftime('%m', Operation.created_at) == f'{month:02d}',
                    func.strftime('%Y', Operation.created_at) == str(year)
                ).group_by(OperationItem.subcategory).order_by(func.sum(OperationItem.amount).desc()).all()
                
                for subcat_name, subcat_amount in subcats:
                    sub_pct = (subcat_amount / cat_amount * 100) if cat_amount > 0 else 0
                    text += f"    └ {subcat_name}: {subcat_amount:,.0f}₽ ({sub_pct:.0f}%)\n"
        
        if no_cat_expenses > 0:
            pct = (no_cat_expenses / total_expenses * 100) if total_expenses > 0 else 0
            text += f"📦 Без категории\n"
            text += f"  {no_cat_expenses:,.0f}₽ ({pct:.0f}%)\n"
        
        if not monthly_expenses and no_cat_expenses == 0:
            text += "Нет расходов за этот месяц\n"
        
        text += "─────────────\n"
        text += f"Итого расходов: {total_expenses:,.2f} ₽\n\n"
        
        # Аналитика
        text += "📈 АНАЛИТИКА:\n"
        text += "─────────────\n"
        text += f"Операций: {ops_count}\n"
        text += f"Средний расход/день: {avg_per_day:,.0f} ₽\n"
        text += f"Прогноз на месяц: {projected:,.0f} ₽\n"
        
        if prev_expenses > 0:
            diff = total_expenses - prev_expenses
            diff_pct = (diff / prev_expenses * 100)
            sign = "+" if diff >= 0 else ""
            text += f"Vs прошлый месяц: {sign}{diff:,.0f}₽ ({sign}{diff_pct:.0f}%)\n"
        
        if monthly_income > 0:
            balance = monthly_income - total_expenses
            text += f"Баланс месяца: {'+' if balance >= 0 else ''}{balance:,.0f} ₽\n"
        
        keyboard = []
        # Кнопки для детализации по каждой категории (используем ID категории)
        for cat_name, emoji, cat_amount in monthly_expenses:
            emoji_str = f"{emoji} " if emoji else ""
            cat_obj = session.query(Category).filter_by(name=cat_name, parent_id=None).first()
            if cat_obj:
                keyboard.append([InlineKeyboardButton(
                    text=f"{emoji_str}{cat_name} ({cat_amount:,.0f}₽) →",
                    callback_data=f"scat_{month}_{year}_{cat_obj.id}"
                )])
        
        keyboard.append([InlineKeyboardButton(text="📅 По месяцам", callback_data="stats_family_months")])
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_stats")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("scat_"))
async def callback_stats_category_detail(callback: CallbackQuery, state: FSMContext):
    """Детализация расходов по категории — список товаров (scat_MM_YYYY_catID)"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from sqlalchemy import func
    
    parts = callback.data.split("_")  # scat_MM_YYYY_catID
    month = int(parts[1])
    year = int(parts[2])
    cat_id = int(parts[3])
    
    session = get_session()
    try:
        category = session.query(Category).get(cat_id)
        
        if not category:
            await callback.answer("Категория не найдена", show_alert=True)
            return
        
        # Все товары в этой категории за месяц
        items = session.query(
            OperationItem.subcategory,
            OperationItem.name,
            func.sum(OperationItem.amount).label('total'),
            func.count(OperationItem.id).label('cnt')
        ).join(
            Operation, OperationItem.operation_id == Operation.id
        ).filter(
            Operation.type == 'family_expense',
            OperationItem.category_id == cat_id,
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).group_by(
            func.coalesce(OperationItem.subcategory, OperationItem.name)
        ).order_by(func.sum(OperationItem.amount).desc()).all()
        
        cat_total = sum(row[2] for row in items)
        emoji_str = f"{category.emoji} " if category.emoji else ""
        month_name = _get_month_name(month)
        
        text = f"{emoji_str}{category.name} — {month_name} {year}\n\n"
        text += "💸 ТОВАРЫ И УСЛУГИ:\n"
        text += "─────────────\n"
        
        if items:
            for subcat, name, total, cnt in items:
                display_name = subcat if subcat else name
                pct = (total / cat_total * 100) if cat_total > 0 else 0
                times = f" × {cnt}" if cnt > 1 else ""
                text += f"• {display_name}{times}: {total:,.0f}₽ ({pct:.0f}%)\n"
        else:
            text += "Нет данных\n"
        
        text += "─────────────\n"
        text += f"Итого: {cat_total:,.2f} ₽"
        
        keyboard = [
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_family")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "stats_family_months")
async def callback_stats_family_months(callback: CallbackQuery, state: FSMContext):
    """Статистика семейного бюджета по месяцам (последние 6)"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from sqlalchemy import func
    from datetime import datetime
    
    session = get_session()
    try:
        now = datetime.now()
        
        text = "👨‍👩‍👧 Семейный бюджет — по месяцам\n\n"
        text += "📊 РАСХОДЫ:\n"
        text += "─────────────\n"
        
        max_expense = 0
        months_data = []
        
        for i in range(5, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            
            total = session.query(
                func.sum(OperationItem.amount)
            ).join(
                Operation, OperationItem.operation_id == Operation.id
            ).filter(
                Operation.type == 'family_expense',
                func.strftime('%m', Operation.created_at) == f'{m:02d}',
                func.strftime('%Y', Operation.created_at) == str(y)
            ).scalar() or 0
            
            income = session.query(
                func.sum(Operation.total_amount)
            ).filter(
                Operation.type.in_(['family_income', 'salary']),
                func.strftime('%m', Operation.created_at) == f'{m:02d}',
                func.strftime('%Y', Operation.created_at) == str(y)
            ).scalar() or 0
            
            months_data.append((m, y, total, income))
            if total > max_expense:
                max_expense = total
        
        for m, y, total, income in months_data:
            bar_len = int((total / max_expense * 10)) if max_expense > 0 else 0
            bar = "█" * bar_len + "░" * (10 - bar_len)
            marker = " ◀ текущий" if m == now.month and y == now.year else ""
            text += f"{_get_month_name(m)[:3]} {y}: {bar} {total:,.0f}₽{marker}\n"
            if income > 0:
                balance = income - total
                text += f"  Доход: {income:,.0f}₽ | Баланс: {'+' if balance >= 0 else ''}{balance:,.0f}₽\n"
        
        keyboard = [
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_family")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "stats_business")
async def callback_stats_business(callback: CallbackQuery, state: FSMContext):
    """Статистика бизнеса"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from sqlalchemy import func
    from datetime import datetime
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
        
        now = datetime.now()
        month = now.month
        year = now.year
        month_name = _get_month_name(month)
        
        # Доходы бизнеса за месяц
        monthly_income = session.query(
            func.sum(Operation.total_amount)
        ).filter(
            Operation.user_id == user.id,
            Operation.type == 'business_income',
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).scalar() or 0
        
        # Расходы бизнеса за месяц
        monthly_expense = session.query(
            func.sum(Operation.total_amount)
        ).filter(
            Operation.user_id == user.id,
            Operation.type == 'business_expense',
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).scalar() or 0
        
        # Зарплаты за месяц
        monthly_salary = session.query(
            func.sum(Operation.total_amount)
        ).filter(
            Operation.user_id == user.id,
            Operation.type == 'salary',
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).scalar() or 0
        
        # Расходы по категориям бизнеса
        biz_cat_expenses = session.query(
            Category.name,
            Category.emoji,
            func.sum(OperationItem.amount).label('total')
        ).join(
            OperationItem, Category.id == OperationItem.category_id
        ).join(
            Operation, OperationItem.operation_id == Operation.id
        ).filter(
            Operation.user_id == user.id,
            Operation.type == 'business_expense',
            func.strftime('%m', Operation.created_at) == f'{month:02d}',
            func.strftime('%Y', Operation.created_at) == str(year)
        ).group_by(Category.id).order_by(func.sum(OperationItem.amount).desc()).all()
        
        # Прошлый месяц для сравнения
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        prev_income = session.query(func.sum(Operation.total_amount)).filter(
            Operation.user_id == user.id,
            Operation.type == 'business_income',
            func.strftime('%m', Operation.created_at) == f'{prev_month:02d}',
            func.strftime('%Y', Operation.created_at) == str(prev_year)
        ).scalar() or 0
        
        profit = monthly_income - monthly_expense - monthly_salary
        total_out = monthly_expense + monthly_salary
        
        biz_name = business_account.name if business_account else "Бизнес"
        biz_balance = business_account.balance if business_account else 0
        
        text = f"💼 {biz_name} — {month_name} {year}\n\n"
        
        text += "💰 ДОХОДЫ:\n"
        text += "─────────────\n"
        text += f"Выручка: +{monthly_income:,.2f} ₽\n"
        if prev_income > 0:
            diff = monthly_income - prev_income
            sign = "+" if diff >= 0 else ""
            text += f"Vs прошлый месяц: {sign}{diff:,.0f}₽\n"
        text += "\n"
        
        text += "💸 РАСХОДЫ:\n"
        text += "─────────────\n"
        if biz_cat_expenses:
            for cat_name, emoji, cat_amount in biz_cat_expenses:
                emoji_str = f"{emoji} " if emoji else ""
                text += f"{emoji_str}{cat_name}: {cat_amount:,.0f}₽\n"
                
                # Подкатегории бизнеса
                biz_subcats = session.query(
                    OperationItem.subcategory,
                    func.sum(OperationItem.amount).label('sub_total')
                ).join(
                    Operation, OperationItem.operation_id == Operation.id
                ).join(
                    Category, OperationItem.category_id == Category.id
                ).filter(
                    Operation.user_id == user.id,
                    Operation.type == 'business_expense',
                    Category.name == cat_name,
                    OperationItem.subcategory != None,
                    func.strftime('%m', Operation.created_at) == f'{month:02d}',
                    func.strftime('%Y', Operation.created_at) == str(year)
                ).group_by(OperationItem.subcategory).order_by(func.sum(OperationItem.amount).desc()).all()
                
                for subcat_name, subcat_amount in biz_subcats:
                    sub_pct = (subcat_amount / cat_amount * 100) if cat_amount > 0 else 0
                    text += f"    └ {subcat_name}: {subcat_amount:,.0f}₽ ({sub_pct:.0f}%)\n"
        text += f"Прочие расходы: {monthly_expense:,.0f}₽\n"
        if monthly_salary > 0:
            text += f"💵 Зарплаты: {monthly_salary:,.0f}₽\n"
        text += f"Итого расходов: {total_out:,.2f}₽\n\n"
        
        text += "📈 ИТОГ:\n"
        text += "─────────────\n"
        text += f"Прибыль: {'+' if profit >= 0 else ''}{profit:,.2f} ₽\n"
        text += f"Баланс счёта: {biz_balance:,.2f} ₽\n"
        
        if monthly_income > 0:
            margin = (profit / monthly_income * 100)
            text += f"Маржа: {margin:.1f}%\n"
        
        keyboard = [
            [InlineKeyboardButton(text="📅 По месяцам", callback_data="stats_business_months")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_stats")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "stats_business_months")
async def callback_stats_business_months(callback: CallbackQuery, state: FSMContext):
    """Статистика бизнеса по месяцам (последние 6)"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from sqlalchemy import func
    from datetime import datetime
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        now = datetime.now()
        
        text = "💼 Бизнес — по месяцам\n\n"
        text += "📊 ДОХОДЫ / РАСХОДЫ / ПРИБЫЛЬ:\n"
        text += "─────────────\n"
        
        max_income = 0
        months_data = []
        
        for i in range(5, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            
            income = session.query(func.sum(Operation.total_amount)).filter(
                Operation.user_id == user.id,
                Operation.type == 'business_income',
                func.strftime('%m', Operation.created_at) == f'{m:02d}',
                func.strftime('%Y', Operation.created_at) == str(y)
            ).scalar() or 0
            
            expense = session.query(func.sum(Operation.total_amount)).filter(
                Operation.user_id == user.id,
                Operation.type.in_(['business_expense', 'salary']),
                func.strftime('%m', Operation.created_at) == f'{m:02d}',
                func.strftime('%Y', Operation.created_at) == str(y)
            ).scalar() or 0
            
            months_data.append((m, y, income, expense))
            if income > max_income:
                max_income = income
        
        for m, y, income, expense in months_data:
            profit = income - expense
            bar_len = int((income / max_income * 8)) if max_income > 0 else 0
            bar = "█" * bar_len + "░" * (8 - bar_len)
            marker = " ◀" if m == now.month and y == now.year else ""
            text += f"{_get_month_name(m)[:3]} {y}:{marker}\n"
            text += f"  {bar} Доход: {income:,.0f}₽\n"
            text += f"  Расход: {expense:,.0f}₽ | Прибыль: {'+' if profit >= 0 else ''}{profit:,.0f}₽\n"
        
        keyboard = [
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_business")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


# ============= РЕДАКТИРОВАНИЕ ПЛАТЕЖЕЙ =============

@router.callback_query(F.data.startswith("cedit_amount_"))
async def cedit_amount(callback: CallbackQuery, state: FSMContext):
    """Изменить сумму платежа"""
    credit_id = int(callback.data.split("_")[2])
    
    from handlers.edit_operations import EditStates
    await state.set_state(EditStates.waiting_for_credit_amount)
    await state.update_data(credit_id=credit_id)
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data=f"credit_{credit_id}")]]
    
    await callback.message.answer(
        "Введите новую сумму платежа:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cedit_name_"))
async def cedit_name(callback: CallbackQuery, state: FSMContext):
    """Изменить название платежа"""
    credit_id = int(callback.data.split("_")[2])
    
    from handlers.edit_operations import EditStates
    await state.set_state(EditStates.waiting_for_credit_name)
    await state.update_data(credit_id=credit_id)
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data=f"credit_{credit_id}")]]
    
    await callback.message.answer(
        "Введите новое название платежа:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cedit_day_"))
async def cedit_day(callback: CallbackQuery, state: FSMContext):
    """Изменить день оплаты"""
    credit_id = int(callback.data.split("_")[2])
    
    from handlers.edit_operations import EditStates
    await state.set_state(EditStates.waiting_for_credit_day)
    await state.update_data(credit_id=credit_id)
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data=f"credit_{credit_id}")]]
    
    await callback.message.answer(
        "Введите новый день оплаты (1-31):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cdel_"))
async def delete_credit(callback: CallbackQuery, state: FSMContext):
    """Удалить платёж"""
    credit_id = int(callback.data.split("_")[1])
    
    session = get_session()
    try:
        credit = session.query(FixedPayment).get(credit_id)
        
        if not credit:
            await callback.answer("Платёж не найден", show_alert=True)
            return
        
        credit.is_active = False
        session.commit()
        
        await callback.answer("✅ Платёж удалён", show_alert=True)
        await callback_credits_menu(callback, state)
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("edit_category_"))
async def edit_item_category(callback: CallbackQuery, state: FSMContext):
    """Начать изменение категории"""
    item_id = int(callback.data.split("_")[2])
    
    session = get_session()
    try:
        # Получить все категории
        categories = session.query(Category).filter_by(parent_id=None).all()
        
        if not categories:
            await callback.answer("Категории не найдены", show_alert=True)
            return
        
        text = "Выберите категорию:\n\n"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = []
        
        for cat in categories:
            btn_text = f"{cat.emoji} {cat.name}" if cat.emoji else cat.name
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"setcat_{item_id}_{cat.id}")])
        
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"edit_item_{item_id}")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("setcat_"))
async def set_category(callback: CallbackQuery, state: FSMContext):
    """Установить категорию"""
    parts = callback.data.split("_")
    item_id = int(parts[1])
    category_id = int(parts[2])
    
    session = get_session()
    try:
        item = session.query(OperationItem).get(item_id)
        category = session.query(Category).get(category_id)
        
        if not item or not category:
            await callback.answer("Ошибка", show_alert=True)
            return
        
        # Получить подкатегории
        subcategories = session.query(Category).filter_by(parent_id=category_id).all()
        
        if subcategories:
            # Показать подкатегории
            text = f"Категория: {category.emoji} {category.name}\n\n" if category.emoji else f"Категория: {category.name}\n\n"
            text += "Выберите подкатегорию:\n\n"
            
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = []
            
            # Кнопка "Без подкатегории"
            keyboard.append([InlineKeyboardButton(text="Без подкатегории", callback_data=f"savecat_{item_id}_{category_id}_none")])
            
            for subcat in subcategories:
                keyboard.append([InlineKeyboardButton(text=subcat.name, callback_data=f"savecat_{item_id}_{category_id}_{subcat.name}")])
            
            keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit_category_{item_id}")])
            
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
            await callback.answer()
        else:
            # Нет подкатегорий, сразу сохраняем
            item.category_id = category_id
            item.subcategory = None
            session.commit()
            
            await callback.answer("✅ Категория изменена", show_alert=True)
            await edit_operation_item(callback, state)
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("savecat_"))
async def save_category(callback: CallbackQuery, state: FSMContext):
    """Сохранить категорию и подкатегорию"""
    parts = callback.data.split("_")
    item_id = int(parts[1])
    category_id = int(parts[2])
    subcategory = parts[3] if parts[3] != "none" else None
    
    session = get_session()
    try:
        item = session.query(OperationItem).get(item_id)
        
        if not item:
            await callback.answer("Ошибка", show_alert=True)
            return
        
        item.category_id = category_id
        item.subcategory = subcategory
        session.commit()
        
        await callback.answer("✅ Категория изменена", show_alert=True)
        await edit_operation_item(callback, state)
        
    finally:
        session.close()


# ============= РЕДАКТИРОВАНИЕ ОПЕРАЦИИ =============

@router.callback_query(F.data.startswith("edit_op_"))
async def edit_operation(callback: CallbackQuery, state: FSMContext):
    """Редактирование операции"""
    operation_id = int(callback.data.split("_")[2])
    
    session = get_session()
    try:
        operation = session.query(Operation).get(operation_id)
        
        if not operation:
            await callback.answer("Операция не найдена", show_alert=True)
            return
        
        # Показать позиции для редактирования
        text = "✏️ Редактирование операции\n\n"
        text += "Выберите позицию для редактирования:\n\n"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = []
        
        for item in operation.items:
            btn_text = f"{item.name} - {item.amount:,.0f}₽"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"edit_item_{item.id}")])
        
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"op_{operation.id}")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("edit_item_"))
async def edit_operation_item(callback: CallbackQuery, state: FSMContext):
    """Редактирование позиции операции"""
    item_id = int(callback.data.split("_")[2])
    
    session = get_session()
    try:
        item = session.query(OperationItem).get(item_id)
        
        if not item:
            await callback.answer("Позиция не найдена", show_alert=True)
            return
        
        text = f"✏️ Редактирование позиции\n\n"
        text += f"Название: {item.name}\n"
        text += f"Сумма: {item.amount:,.2f} ₽\n"
        
        if item.category:
            cat_text = f"{item.category.emoji} {item.category.name}" if item.category.emoji else item.category.name
            if item.subcategory:
                text += f"Категория: {cat_text} → {item.subcategory}\n"
            else:
                text += f"Категория: {cat_text}\n"
        
        text += "\nЧто хотите изменить?"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data=f"edit_amount_{item.id}")],
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{item.id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit_op_{item.operation_id}")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("edit_amount_"))
async def edit_item_amount(callback: CallbackQuery, state: FSMContext):
    """Начать изменение суммы"""
    item_id = int(callback.data.split("_")[2])
    
    from handlers.edit_operations import EditStates
    
    await state.set_state(EditStates.waiting_for_amount)
    await state.update_data(item_id=item_id)
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data=f"edit_item_{item_id}")]]
    
    await callback.message.answer(
        "Введите новую сумму:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_name_"))
async def edit_item_name(callback: CallbackQuery, state: FSMContext):
    """Начать изменение названия"""
    item_id = int(callback.data.split("_")[2])
    
    from handlers.edit_operations import EditStates
    
    await state.set_state(EditStates.waiting_for_name)
    await state.update_data(item_id=item_id)
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data=f"edit_item_{item_id}")]]
    
    await callback.message.answer(
        "Введите новое название:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


# ============= ПРОСМОТР ОПЕРАЦИИ =============

@router.callback_query(F.data.startswith("op_"))
async def view_operation(callback: CallbackQuery, state: FSMContext):
    """Просмотр деталей операции"""
    operation_id = int(callback.data.split("_")[1])
    
    session = get_session()
    try:
        operation = session.query(Operation).get(operation_id)
        
        if not operation:
            await callback.answer("Операция не найдена", show_alert=True)
            return
        
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
            text += "─────────────\n"
            
            for i, item in enumerate(operation.items, 1):
                text += f"{i}. {item.name}\n"
                text += f"   {item.amount:,.2f} ₽"
                
                if item.category:
                    cat_text = f" | {item.category.emoji} {item.category.name}" if item.category.emoji else f" | {item.category.name}"
                    if item.subcategory:
                        cat_text += f" → {item.subcategory}"
                    text += cat_text
                
                text += "\n\n"
        
        text += "─────────────\n"
        text += f"Общая сумма: {operation.total_amount:,.2f} ₽"
        
        # Кнопки действий
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_op_{operation.id}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"del_op_{operation.id}")
            ],
            [InlineKeyboardButton(text="⬅️ Назад к операциям", callback_data="menu_operations")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("del_op_"))
async def delete_operation(callback: CallbackQuery, state: FSMContext):
    """Удаление операции"""
    operation_id = int(callback.data.split("_")[2])
    
    session = get_session()
    try:
        operation = session.query(Operation).get(operation_id)
        if not operation:
            await callback.answer("Операция не найдена", show_alert=True)
            return

        # --- PATCH: Rollback balances and payment status if this is a payment operation ---
        # Check if this operation is a payment for FixedPaymentDue
        # Heuristic: operation.type == 'family_expense' and only one item, and item name matches FixedPayment
        if operation.type == 'family_expense' and len(operation.items) == 1:
            item = operation.items[0]
            # Try to find a FixedPayment with this name
            fp = session.query(FixedPayment).filter_by(name=item.name).first()
            if fp:
                # Find the due for this payment in the same month/year as operation
                op_date = operation.created_at
                due = session.query(FixedPaymentDue).filter_by(fixed_payment_id=fp.id, year=op_date.year, month=op_date.month).first()
                if due and due.is_paid:
                    # Rollback paid_amount and status
                    due.paid_amount = max(0.0, (due.paid_amount or 0.0) - item.amount)
                    if due.paid_amount < due.due_amount:
                        due.is_paid = False
                        due.paid_at = None

                # Rollback FamilyBudget balance (card/cash)
                fb = session.query(FamilyBudget).first()
                if fb:
                    # Heuristic: if paid_account_id is None, it was card/cash, otherwise business
                    # Try to guess from operation created_at and due.paid_account_id
                    # For now, return to card_balance by default
                    fb.card_balance = (fb.card_balance or 0.0) + item.amount
                    fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)

        # --- END PATCH ---

        # Удаление операции (каскадно удалятся и items)
        session.delete(operation)
        session.commit()

        await callback.answer("✅ Операция удалена", show_alert=True)

        # Возврат к списку операций
        await callback_operations_menu(callback, state)

    finally:
        session.close()


@router.callback_query(F.data == "menu_business")
async def callback_business_menu(callback: CallbackQuery, state: FSMContext):
    """Меню бизнеса"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
        
        if not business_account:
            await callback.message.edit_text("❌ Бизнес-аккаунт не найден")
            await callback.answer()
            return
        
        # Расчёты по месяцу
        from sqlalchemy import func
        from datetime import datetime
        current_month = datetime.now().month
        current_year = datetime.now().year

        # Сумма доходов и расходов бизнеса за текущий месяц
        monthly_income = session.query(func.sum(Operation.total_amount)).filter(
            Operation.user_id == user.id,
            Operation.type == 'business_income',
            func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
            func.strftime('%Y', Operation.created_at) == str(current_year)
        ).scalar() or 0.0

        monthly_expense = session.query(func.sum(Operation.total_amount)).filter(
            Operation.user_id == user.id,
            Operation.type == 'business_expense',
            func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
            func.strftime('%Y', Operation.created_at) == str(current_year)
        ).scalar() or 0.0

        # Распределение по категориям (топ 5)
        cat_breakdown = session.query(
            Category.name,
            func.sum(OperationItem.amount).label('total')
        ).join(OperationItem, Category.id == OperationItem.category_id).join(
            Operation, OperationItem.operation_id == Operation.id
        ).filter(
            Operation.user_id == user.id,
            Operation.type.in_(['business_income', 'business_expense']),
            func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
            func.strftime('%Y', Operation.created_at) == str(current_year)
        ).group_by(Category.id).order_by(func.sum(OperationItem.amount).desc()).limit(5).all()

        text = f"💼 Ваш бизнес: {business_account.name}\n\n"
        text += f"💵 Баланс: {business_account.balance:,.2f} ₽\n\n"
        text += "─────────────\n"
        text += f"Доход: +{monthly_income:,.2f} ₽\n"
        text += f"Расход: -{monthly_expense:,.2f} ₽\n\n"
        if cat_breakdown:
            text += "📊 Топ категорий (за месяц):\n"
            for name, total in cat_breakdown:
                text += f"• {name}: {total:,.2f} ₽\n"
            text += "\n"
        text += "Выберите действие:"
        
        await callback.message.edit_text(text, reply_markup=get_business_menu())
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "menu_credits")
async def callback_credits_menu(callback: CallbackQuery, state: FSMContext):
    """Меню платежей"""
    await state.clear()
    
    session = get_session()
    try:
        credits = session.query(FixedPayment).filter_by(is_active=True).all()
        
        text = "💳 Платежи\n\n"
        
        if credits:
            text += "Нажмите на платёж для редактирования:\n\n"
        else:
            text += "У вас пока нет платежей.\n\n"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = []
        
        for credit in credits:
            btn_text = f"{credit.name} - {credit.amount:,.0f}₽ (до {credit.payment_day} числа)"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"credit_{credit.id}")])
        
        keyboard.append([InlineKeyboardButton(text="➕ Добавить платёж", callback_data="credit_add")])
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.regexp(r'^credit_\d+$'))
async def view_credit(callback: CallbackQuery, state: FSMContext):
    """Просмотр и редактирование платежа"""
    try:
        credit_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    
    session = get_session()
    try:
        credit = session.query(FixedPayment).get(credit_id)
        
        if not credit:
            await callback.answer("Платёж не найден", show_alert=True)
            return
        
        text = f"💳 {credit.name}\n\n"
        text += f"Сумма: {credit.amount:,.2f} ₽\n"
        text += f"День оплаты: {credit.payment_day} число\n\n"
        text += "Что хотите сделать?"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data=f"cedit_amount_{credit.id}")],
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"cedit_name_{credit.id}")],
            [InlineKeyboardButton(text="✏️ Изменить день оплаты", callback_data=f"cedit_day_{credit.id}")],
            [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"cdel_{credit.id}")],
            [InlineKeyboardButton(text="💸 Оплатить", callback_data=f"pay_fp_{credit.id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_credits"), InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()



@router.callback_query(F.data.regexp(r'^pay_fp_\d+$'))
async def callback_pay_fixed_payment(callback: CallbackQuery, state: FSMContext):
    """Начало потока оплаты: выбор способа (карта/наличные)"""
    try:
        fp_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer()
        return

    session = get_session()
    try:
        fp = session.query(FixedPayment).get(fp_id)
        if not fp:
            await callback.answer("Платёж не найден", show_alert=True)
            return

        # Найдём или создадим начисление для текущего месяца
        from datetime import datetime
        now = datetime.now()
        due = session.query(FixedPaymentDue).filter_by(fixed_payment_id=fp.id, year=now.year, month=now.month).first()
        if not due:
            due = FixedPaymentDue(
                fixed_payment_id=fp.id,
                year=now.year,
                month=now.month,
                due_amount=fp.amount,
                paid_amount=0.0,
                is_paid=False,
                skipped=False
            )
            session.add(due)
            session.commit()

        remaining = max(0.0, due.due_amount - (due.paid_amount or 0.0))

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Картой", callback_data=f"pay_method_card_{due.id}")],
            [InlineKeyboardButton(text="Наличными", callback_data=f"pay_method_cash_{due.id}")],
            [InlineKeyboardButton(text="Отмена", callback_data="menu_credits")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ])

        await callback.message.edit_text(
            f"Оплата: {fp.name}\nСумма к оплате: {remaining:,.2f} ₽\nВыберите способ оплаты:",
            reply_markup=kb
        )
        await callback.answer()
    finally:
        session.close()


@router.callback_query(F.data.regexp(r'^pay_method_(card|cash)_\d+$'))
async def callback_pay_method_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора способа оплаты — отмечаем начисление как оплаченное (полностью)"""
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer()
        return
    method = parts[2]
    try:
        due_id = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer()
        return

    session = get_session()
    try:
        due = session.query(FixedPaymentDue).get(due_id)
        if not due:
            await callback.answer("Начисление не найдено", show_alert=True)
            return
        fp = session.query(FixedPayment).get(due.fixed_payment_id)

        # Полная оплата
        amount = max(0.0, due.due_amount - (due.paid_amount or 0.0))
        if amount <= 0:
            await callback.answer("Уже оплачено", show_alert=True)
            return

        # Создадим операцию расхода
        # Для user_id используем первый доступный user (или 1)
        from sqlalchemy import text
        user_row = session.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
        user_id = user_row[0] if user_row else 1

        operation = Operation(user_id=user_id, type='family_expense', total_amount=amount)
        session.add(operation)
        session.flush()

        item = OperationItem(operation_id=operation.id, name=fp.name, amount=amount, category_id=getattr(fp, 'category_id', None))
        session.add(item)

        paid_account_id = None
        if method == 'card':
            # если есть default_account_id у платежа — используем его
            if getattr(fp, 'default_account_id', None):
                acc = session.query(BusinessAccount).get(fp.default_account_id)
                if acc:
                    acc.balance -= amount
                    paid_account_id = acc.id
            else:
                # иначе списываем с семейного баланса
                fb = session.query(FamilyBudget).first()
                if fb:
                    fb.balance -= amount
        else:
            # наличные — ничего не меняем
            paid_account_id = None

        due.paid_amount = (due.paid_amount or 0.0) + amount
        due.paid_account_id = paid_account_id
        due.is_paid = True
        from datetime import datetime
        due.paid_at = datetime.now()

        session.commit()

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        nav_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_credits"), InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ])

        await callback.message.edit_text(f"✅ Платёж {fp.name} оплачен на {amount:,.2f} ₽ ({'картой' if method=='card' else 'наличными'})", reply_markup=nav_kb)
        await callback.answer()
    finally:
        session.close()


@router.callback_query(F.data == "menu_piggy")
async def callback_piggy_menu(callback: CallbackQuery, state: FSMContext):
    """Меню копилок"""
    await state.clear()
    
    session = get_session()
    try:
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
            text += "─────────────\n"
            text += f"Всего накоплено: {total:,.2f} ₽\n\n"
        else:
            text += "У вас пока нет копилок.\n\n"
        
        text += "Выберите действие:"
        
        await callback.message.edit_text(text, reply_markup=get_piggy_menu())
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "menu_operations")
async def callback_operations_menu(callback: CallbackQuery, state: FSMContext):
    """История операций семейного бюджета"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        
        # Семейные операции (расходы и доходы)
        operations = session.query(Operation).filter(
            Operation.user_id == user.id,
            Operation.type.in_(['family_expense', 'family_income'])
        ).order_by(Operation.created_at.desc()).limit(10).all()
        
        if not operations:
            await callback.message.edit_text(
                "📋 История операций\n\n"
                "У вас пока нет операций.",
                reply_markup=get_main_menu()
            )
            await callback.answer()
            return
        
        text = "📋 История операций\n\n"
        text += "Нажмите на операцию для просмотра деталей:\n\n"
        
        # Создание кнопок для каждой операции
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = []
        
        for op in operations:
            icons = {
                'family_expense': '🛒',
                'family_income': '💵',
                'business_income': '💰',
                'business_expense': '💸',
                'salary': '💵'
            }
            icon = icons.get(op.type, '📝')
            sign = '+' if op.type == 'family_income' else '-'
            
            # Формат кнопки: "ДД.ММ, ЧЧ:ММ - Сумма"
            btn_text = f"{icon} {op.created_at.strftime('%d.%m, %H:%M')} {sign}{op.total_amount:,.0f}₽"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"op_{op.id}")])
        
        # Кнопка назад
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "business_operations")
async def callback_business_operations(callback: CallbackQuery, state: FSMContext):
    """Операции бизнеса"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        
        operations = session.query(Operation).filter(
            Operation.user_id == user.id,
            Operation.type.in_(['business_income', 'business_expense', 'salary'])
        ).order_by(Operation.created_at.desc()).limit(10).all()
        
        if not operations:
            await callback.message.edit_text(
                "📋 Операции бизнеса\n\n"
                "У вас пока нет операций в бизнесе.",
                reply_markup=get_business_menu()
            )
            await callback.answer()
            return
        
        text = "💼 Операции бизнеса\n\n"
        text += "Нажмите на операцию для просмотра деталей:\n\n"
        
        # Создание кнопок для каждой операции
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = []
        
        for op in operations:
            icons = {
                'business_income': '💰',
                'business_expense': '💸',
                'salary': '💵'
            }
            icon = icons.get(op.type, '📝')
            
            sign = '+' if op.type == 'business_income' else '-'
            
            # Формат кнопки: "ДД.ММ, ЧЧ:ММ - Сумма"
            btn_text = f"{icon} {op.created_at.strftime('%d.%m, %H:%M')} {sign}{op.total_amount:,.0f}₽"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"op_{op.id}")])
        
        # Кнопка назад
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_business")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()
