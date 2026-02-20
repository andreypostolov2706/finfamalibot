"""
Обработчики для семейного бюджета
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, User, Operation, OperationItem, Category, FamilyBudget
from services import DeepSeekService
from keyboards.main_menu import get_main_menu

router = Router()
deepseek = DeepSeekService()


class FamilyBudgetStates(StatesGroup):
    """Состояния для работы с семейным бюджетом"""
    waiting_for_expense = State()
    waiting_for_income = State()


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
    from database import FixedPayment, PiggyBank, BusinessAccount, Debt
    from sqlalchemy import func
    from datetime import datetime
    
    # Получение фиксированных платежей
    fixed_payments = session.query(FixedPayment).filter_by(is_active=True).all()
    
    # Получение копилок
    business_account = session.query(BusinessAccount).filter_by(user_id=user.id).first()
    piggy_banks = session.query(PiggyBank).all() if business_account else []
    
    # Получение расходов за текущий месяц
    current_month = datetime.now().month
    current_year = datetime.now().year
    
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
    
    # Зарплата за месяц
    monthly_salary = session.query(
        func.sum(Operation.total_amount).label('total')
    ).filter(
        Operation.user_id == user.id,
        Operation.type == 'salary',
        func.strftime('%m', Operation.created_at) == f'{current_month:02d}',
        func.strftime('%Y', Operation.created_at) == str(current_year)
    ).scalar() or 0
    
    # Получение общего семейного бюджета
    family_budget = session.query(FamilyBudget).first()
    if not family_budget:
        family_budget = FamilyBudget(balance=0.0)
        session.add(family_budget)
        session.commit()
    
    # Вычисления для дашборда
    import calendar
    today = datetime.now().day
    days_in_month = calendar.monthrange(current_year, current_month)[1]
    
    total_payments = sum(p.amount for p in fixed_payments)
    total_expenses = sum(total for _, _, total in monthly_expenses)
    avg_per_day = total_expenses / today if today > 0 else 0
    
    # Остаток на день: (баланс - платежи) / оставшиеся дни
    days_left = days_in_month - today + 1
    daily_budget = (family_budget.balance - total_payments) / days_left if days_left > 0 else 0
    
    # Формирование текста дашборда
    text = "🏠 Главная\n\n"
    
    # Семейный бюджет
    text += "👨‍👩‍👧 СЕМЕЙНЫЙ БЮДЖЕТ:\n"
    text += "─────────────\n"
    text += f"Баланс: {family_budget.balance:,.2f} ₽\n"
    
    if monthly_salary > 0:
        text += f"Зарплата: +{monthly_salary:,.2f} ₽\n"
    if monthly_family_income > 0:
        text += f"Доход: +{monthly_family_income:,.2f} ₽\n"
    text += "\n"
    
    # Платежи
    if fixed_payments:
        text += "💳 ПЛАТЕЖИ:\n"
        text += "─────────────\n"
        for payment in fixed_payments:
            text += f"{payment.name}: {payment.amount:,.2f} ₽ (до {payment.payment_day} числа)\n"
        text += f"Общая сумма: {total_payments:,.2f} ₽\n\n"
    
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
        
        # Создание операции
        operation = Operation(
            user_id=user.id,
            type='family_income',
            total_amount=amount
        )
        session.add(operation)
        session.flush()
        
        operation_item = OperationItem(
            operation_id=operation.id,
            name=description,
            amount=amount
        )
        session.add(operation_item)
        
        # Пополнение общего семейного бюджета
        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            family_budget = FamilyBudget(balance=0.0)
            session.add(family_budget)
        family_budget.balance += amount
        session.commit()
        
        response = "✅ Доход добавлен в семейный бюджет!\n\n"
        response += f"💵 {description}: +{amount:,.2f} ₽\n\n"
        response += f"👨‍👩‍👧 Семейный бюджет\n"
        response += f"Баланс: {family_budget.balance:,.2f} ₽"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ]
        
        await message.answer(response, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
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
            family_budget = FamilyBudget(balance=0.0)
            session.add(family_budget)
            session.flush()
        
        total_amount = sum(item['amount'] for item in items_to_add)
        
        # Проверка баланса
        if family_budget.balance < total_amount:
            await message.answer(
                f"❌ Недостаточно средств в семейном бюджете!\n\n"
                f"Доступно: {family_budget.balance:,.2f} ₽\n"
                f"Требуется: {total_amount:,.2f} ₽\n\n"
                f"Выдайте зарплату из бизнеса для пополнения семейного бюджета."
            )
            return
        
        # Создание одной операции со всеми позициями
        operation = Operation(
            user_id=user.id,
            type='family_expense',
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
        
        # Списание из семейного бюджета
        family_budget.balance -= total_amount
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
        response += f"Остаток: {family_budget.balance:,.2f} ₽"
        
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
