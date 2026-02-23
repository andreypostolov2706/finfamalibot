"""
Обработчик загрузки и анализа чеков (фото)
"""
import os
import io
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_session, User, BusinessAccount, Operation, OperationItem, Category, FamilyBudget
from services import DeepSeekService

router = Router()
deepseek = DeepSeekService()


class ReceiptStates(StatesGroup):
    """Состояния для обработки чека"""
    waiting_for_budget_choice = State()  # Выбор бюджета (семья/бизнес)
    waiting_for_account_choice = State()  # Для семейного бюджета: карта/наличные
    waiting_for_confirmation = State()   # Подтверждение позиций


def get_budget_choice_keyboard():
    """Клавиатура выбора бюджета"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨‍👩‍👧 Семейный бюджет", callback_data="receipt_family"),
            InlineKeyboardButton(text="💼 Бизнес", callback_data="receipt_business")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_main")]
    ])


@router.message(F.photo)
async def handle_receipt_photo(message: types.Message, state: FSMContext, bot: Bot):
    """Обработка фото чека"""
    # Сохраняем file_id фото
    photo = message.photo[-1]  # Берём наибольшее разрешение
    await state.update_data(photo_file_id=photo.file_id)
    # Если пользователь находится в режиме добавления расхода в бизнес — сразу записываем в бизнес
    try:
        from handlers.business import BusinessStates
        current_state = await state.get_state()
        if current_state == BusinessStates.waiting_for_expense:
            await message.answer("📸 Фото получено!\n\n🤖 Анализирую чек через ИИ... Это может занять несколько секунд.")
            await _analyze_receipt_and_ask(photo.file_id, 'business', message, state, bot)
            return
    except Exception:
        pass

    await state.set_state(ReceiptStates.waiting_for_budget_choice)

    await message.answer(
        "📸 Фото получено!\n\n"
        "Куда добавить расходы из чека?",
        reply_markup=get_budget_choice_keyboard()
    )


@router.message(F.document & F.document.mime_type.startswith("image/"))
async def handle_receipt_document(message: types.Message, state: FSMContext, bot: Bot):
    """Обработка документа-изображения чека"""
    await state.update_data(photo_file_id=message.document.file_id, is_document=True)
    # Если пользователь находится в режиме добавления расхода в бизнес — сразу записываем в бизнес
    try:
        from handlers.business import BusinessStates
        current_state = await state.get_state()
        if current_state == BusinessStates.waiting_for_expense:
            await message.answer("📄 Изображение получено!\n\n🤖 Анализирую чек через ИИ... Это может занять несколько секунд.")
            await _analyze_receipt_and_ask(message.document.file_id, 'business', message, state, bot)
            return
    except Exception:
        pass

    await state.set_state(ReceiptStates.waiting_for_budget_choice)

    await message.answer(
        "📄 Изображение получено!\n\n"
        "Куда добавить расходы из чека?",
        reply_markup=get_budget_choice_keyboard()
    )


@router.callback_query(F.data.in_({"receipt_family", "receipt_business"}))
async def process_budget_choice(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка выбора бюджета и анализ чека"""
    current_state = await state.get_state()
    if current_state != ReceiptStates.waiting_for_budget_choice:
        await callback.answer()
        return

    budget_type = "family" if callback.data == "receipt_family" else "business"
    data = await state.get_data()
    file_id = data.get("photo_file_id")

    if not file_id:
        await callback.message.edit_text("❌ Файл не найден. Попробуйте снова.")
        await state.clear()
        await callback.answer()
        return

    # If family budget selected, ask which account (card/cash)
    if budget_type == 'family':
        await state.set_state(ReceiptStates.waiting_for_account_choice)
        # Save file_id in state (already saved earlier, but ensure)
        await state.update_data(photo_file_id=file_id)

        account_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Карта", callback_data="receipt_account_card"),
                InlineKeyboardButton(text="💵 Наличные", callback_data="receipt_account_cash")
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_main")]
        ])

        try:
            await callback.message.edit_text("Выберите счёт для расхода:", reply_markup=account_kb)
        except Exception:
            await callback.message.answer("Выберите счёт для расхода:", reply_markup=account_kb)

        await callback.answer()
        return

    await callback.message.edit_text("🤖 Анализирую чек через ИИ...\n\nЭто может занять несколько секунд.")
    await callback.answer()

    await _analyze_receipt_and_ask(file_id, budget_type, callback.message, state, bot)


@router.callback_query(F.data.in_({"receipt_account_card", "receipt_account_cash"}))
async def process_account_choice(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка выбора счёта (карта/наличные) для семейного бюджета"""
    current_state = await state.get_state()
    if current_state != ReceiptStates.waiting_for_account_choice:
        await callback.answer()
        return

    account_type = 'card' if callback.data == 'receipt_account_card' else 'cash'
    await state.update_data(account_type=account_type)

    data = await state.get_data()
    file_id = data.get('photo_file_id')
    if not file_id:
        try:
            await callback.message.edit_text("❌ Файл не найден. Попробуйте снова.")
        except Exception:
            await callback.message.answer("❌ Файл не найден. Попробуйте снова.")
        await state.clear()
        await callback.answer()
        return

    try:
        await callback.message.edit_text("🤖 Анализирую чек через ИИ...\n\nЭто может занять несколько секунд.")
    except Exception:
        await callback.message.answer("🤖 Анализирую чек через ИИ...\n\nЭто может занять несколько секунд.")

    await callback.answer()
    await _analyze_receipt_and_ask(file_id, 'family', callback.message, state, bot)


async def _analyze_receipt_and_ask(file_id: str, budget_type: str, message_obj, state: FSMContext, bot: Bot):
    """Helper: download image, analyze via DeepSeek and ask user to confirm positions."""
    try:
        # Скачиваем файл
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_data = file_bytes.read()

        # Анализ через DeepSeek Vision
        session = get_session()
        try:
            # Получение категорий
            categories = session.query(Category).filter_by(parent_id=None).all()
            categories_data = []
            for cat in categories:
                subcats = session.query(Category).filter_by(parent_id=cat.id).all()
                categories_data.append({
                    "name": cat.name,
                    "emoji": cat.emoji or "",
                    "subcategories": [sc.name for sc in subcats]
                })

            # Формируем публичный URL файла из Telegram
            import config as cfg
            telegram_file_url = f"https://api.telegram.org/file/bot{cfg.BOT_TOKEN}/{file.file_path}"

            # Анализ изображения через DeepSeek (URL + байты как fallback)
            # If user chose account_type earlier, include it in state data for later processing
            data = await state.get_data()
            account_type = data.get('account_type')

            items = deepseek.analyze_receipt_image(image_data, categories_data, telegram_file_url)

            if not items:
                try:
                    await message_obj.edit_text(
                        "❌ Не удалось распознать чек.\n\n"
                        "Попробуйте:\n"
                        "• Сделать более чёткое фото\n"
                        "• Убедиться что чек хорошо освещён\n"
                        "• Отправить фото без сжатия (как документ)"
                    )
                except Exception:
                    await message_obj.answer(
                        "❌ Не удалось распознать чек.\n\n"
                        "Попробуйте:\n"
                        "• Сделать более чёткое фото\n"
                        "• Убедиться что чек хорошо освещён\n"
                        "• Отправить фото без сжатия (как документ)"
                    )
                await state.clear()
                return

            # Сохраняем данные для подтверждения
            await state.update_data(
                items=items,
                budget_type=budget_type,
                categories_data=categories_data,
                account_type=account_type
            )
            await state.set_state(ReceiptStates.waiting_for_confirmation)

            # Формируем текст с найденными позициями
            total = sum(item.get('amount', 0) for item in items)

            budget_name = "👨‍👩‍👧 Семейный бюджет" if budget_type == "family" else "💼 Бизнес"

            text = f"✅ Чек распознан!\n\n"
            text += f"Бюджет: {budget_name}\n\n"
            text += "📋 Найденные позиции:\n"
            text += "─────────────\n"

            for i, item in enumerate(items, 1):
                name = item.get('name', 'Без названия')
                amount = item.get('amount', 0)
                category = item.get('category', '')
                subcategory = item.get('subcategory', '')

                text += f"{i}. {name}\n"
                text += f"   💰 {amount:,.2f} ₽"
                if category:
                    text += f" | {category}"
                    if subcategory:
                        text += f" → {subcategory}"
                text += "\n"

            text += "─────────────\n"
            text += f"Итого: {total:,.2f} ₽\n\n"
            text += "Верна ли сумма? Если нет, напишите правильную сумму в ответ.\n\n"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, верно", callback_data="receipt_confirm"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="menu_main")
                ]
            ])

            try:
                await message_obj.edit_text(text, reply_markup=keyboard)
            except Exception:
                await message_obj.answer(text, reply_markup=keyboard)

        finally:
            session.close()

    except Exception as e:
        print(f"Ошибка при обработке чека: {e}")
        try:
            await message_obj.edit_text(
                f"❌ Ошибка при анализе чека: {str(e)[:100]}\n\n"
                "Попробуйте ещё раз."
            )
        except Exception:
            await message_obj.answer(f"❌ Ошибка при анализе чека: {str(e)[:100]}\n\nПопробуйте ещё раз.")
        await state.clear()
            
@router.message(ReceiptStates.waiting_for_confirmation)
async def handle_receipt_total_correction(message: types.Message, state: FSMContext):
    """Обработка ручного ввода итоговой суммы расхода по чеку"""
    import re
    numbers = re.findall(r'\d+(?:\.\d+)?', message.text)
    if not numbers:
        await message.answer("❌ Не могу определить сумму. Введите число:")
        return
    new_total = float(numbers[0])
    if new_total <= 0:
        await message.answer("❌ Сумма должна быть больше нуля. Введите снова:")
        return
    # Сохраняем новую сумму для расхода
    data = await state.get_data()
    await state.update_data(receipt_corrected_total=new_total)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Добавить расход", callback_data="receipt_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="menu_main")
        ]
    ])
    await message.answer(
        f"Новая сумма расхода: {new_total:,.2f} ₽\nДобавить расход?",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "receipt_confirm")
async def confirm_receipt(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение и сохранение позиций чека"""
    current_state = await state.get_state()
    if current_state != ReceiptStates.waiting_for_confirmation:
        await callback.answer()
        return
    
    data = await state.get_data()
    items = data.get('items', [])
    budget_type = data.get('budget_type', 'family')
    corrected_total = data.get('receipt_corrected_total')
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        # Если пользователь ввёл новую сумму — используем её
        if corrected_total:
            total_amount = corrected_total
        else:
            total_amount = sum(item.get('amount', 0) for item in items)

        # Подготовим список позиций для сохранения. Если пользователь указал свою итоговую сумму,
        # пропорционально масштабируем суммы позиций, сохраняя наименования и категории.
        adjusted_items = []
        if items:
            orig_sum = sum(float(item.get('amount', 0) or 0.0) for item in items)
            if corrected_total and orig_sum > 0:
                # Пользователь указал итог вручную — сохраняем распознанные цены по позициям
                # (итог операции будет равен corrected_total, но цены позиций остаются как распознаны)
                for it in items:
                    adjusted_items.append({**it, '_adjusted_amount': float(it.get('amount', 0) or 0.0)})
            elif corrected_total and orig_sum == 0:
                # Если распознанные суммы отсутствуют — равномерно распределим итог по позициям
                per = round(float(total_amount) / len(items), 2)
                running = 0.0
                for it in items:
                    adjusted_items.append({**it, '_adjusted_amount': per})
                    running += per
                diff = round(float(total_amount) - running, 2)
                if adjusted_items:
                    adjusted_items[-1]['_adjusted_amount'] = round(adjusted_items[-1]['_adjusted_amount'] + diff, 2)
            else:
                # Используем распознанные суммы как есть
                for it in items:
                    adjusted_items.append({**it, '_adjusted_amount': float(it.get('amount', 0) or 0.0)})
        else:
            adjusted_items = []
        
        if budget_type == "family":
            # Проверка баланса семейного бюджета (карта + наличные)
            # If account was not chosen yet, ask the user
            account_from_state = data.get('account_type')
            if not account_from_state:
                # Save current confirmation data and ask which account to use
                await state.update_data(items=items, receipt_corrected_total=corrected_total, budget_type=budget_type, categories_data=data.get('categories_data'))
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="💳 Картой", callback_data="receipt_confirm_account_card"),
                        InlineKeyboardButton(text="💵 Наличными", callback_data="receipt_confirm_account_cash")
                    ]
                ])
                await callback.message.edit_text("Выберите счёт для списания по чеку:", reply_markup=kb)
                await state.set_state(ReceiptStates.waiting_for_account_choice)
                await callback.answer()
                return
            family_budget = session.query(FamilyBudget).first()
            if not family_budget:
                family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
                session.add(family_budget)
                session.flush()

            family_total = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
            if family_total < total_amount:
                await callback.message.edit_text(
                    f"❌ Недостаточно средств в семейном бюджете!\n\n"
                    f"Доступно: {family_total:,.2f} ₽\n"
                    f"Требуется: {total_amount:,.2f} ₽"
                )
                await state.clear()
                await callback.answer()
                return
            
            # Создание операции
            # Определим, с какого счёта списаны средства (карта/наличные/смешанно)
            account_used = None
            # Если пользователь заранее выбрал счёт — используем его
            if account_from_state in ('card', 'cash'):
                account_used = account_from_state
            else:
                card_bal = (family_budget.card_balance or 0.0)
                cash_bal = (family_budget.cash_balance or 0.0)
                if card_bal >= total_amount:
                    account_used = 'card'
                elif cash_bal >= total_amount:
                    account_used = 'cash'
                else:
                    account_used = 'mixed'

            operation = Operation(
                user_id=user.id,
                type='family_expense',
                total_amount=total_amount,
                account_type=account_used
            )
            session.add(operation)
            session.flush()
            
            # Добавление позиций (используем скорректированные суммы, если они есть)
            for item_data in adjusted_items:
                category = None
                if item_data.get('category'):
                    category = session.query(Category).filter_by(
                        name=item_data['category'],
                        parent_id=None
                    ).first()
                # Используем скорректированную сумму, если она была рассчитана
                amount_to_use = item_data.get('_adjusted_amount', item_data.get('amount', 0))
                op_item = OperationItem(
                    operation_id=operation.id,
                    name=item_data.get('name', 'Без названия'),
                    amount=amount_to_use,
                    category_id=category.id if category else None,
                    subcategory=item_data.get('subcategory')
                )
                session.add(op_item)
            
            # Списание из семейного бюджета: используем определённый счёт
            remaining = total_amount
            if account_used == 'card':
                family_budget.card_balance -= remaining
            elif account_used == 'cash':
                family_budget.cash_balance -= remaining
            else:  # mixed
                if (family_budget.card_balance or 0.0) >= remaining:
                    family_budget.card_balance -= remaining
                else:
                    remaining -= (family_budget.card_balance or 0.0)
                    family_budget.card_balance = 0.0
                    if remaining > 0:
                        family_budget.cash_balance = (family_budget.cash_balance or 0.0) - remaining
            # Обновляем суммарное поле balance для совместимости
            family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
            session.commit()

            response = f"✅ Чек добавлен в семейный бюджет!\n\n"
            response += f"Позиций: {len(adjusted_items)}\n"
            response += f"Итого: -{total_amount:,.2f} ₽\n\n"
            response += f"👨‍👩‍👧 Семейный бюджет\n"
            response += f"Остаток: {family_budget.balance:,.2f} ₽ (Карта: {family_budget.card_balance:,.2f} ₽, Наличные: {family_budget.cash_balance:,.2f} ₽)"
            
        else:  # business
            business = session.query(BusinessAccount).filter_by(user_id=user.id).first()
            
            if not business:
                await callback.message.edit_text("❌ Бизнес-аккаунт не найден.")
                await state.clear()
                await callback.answer()
                return
            
            if business.balance < total_amount:
                await callback.message.edit_text(
                    f"❌ Недостаточно средств в бизнесе!\n\n"
                    f"Доступно: {business.balance:,.2f} ₽\n"
                    f"Требуется: {total_amount:,.2f} ₽"
                )
                await state.clear()
                await callback.answer()
                return
            
            # Создание операции
            operation = Operation(
                user_id=user.id,
                type='business_expense',
                total_amount=total_amount
            )
            session.add(operation)
            session.flush()
            
            # Добавление позиций (используем скорректированные суммы, если они есть)
            for item_data in adjusted_items:
                category = None
                if item_data.get('category'):
                    category = session.query(Category).filter_by(
                        name=item_data['category'],
                        parent_id=None
                    ).first()
                amount_to_use = item_data.get('_adjusted_amount', item_data.get('amount', 0))
                op_item = OperationItem(
                    operation_id=operation.id,
                    name=item_data.get('name', 'Без названия'),
                    amount=amount_to_use,
                    category_id=category.id if category else None,
                    subcategory=item_data.get('subcategory')
                )
                session.add(op_item)
            
            # Списание из бизнеса
            business.balance -= total_amount
            session.commit()
            
            response = f"✅ Чек добавлен в бизнес!\n\n"
            response += f"Позиций: {len(adjusted_items)}\n"
            response += f"Итого: -{total_amount:,.2f} ₽\n\n"
            response += f"💼 Бизнес: {business.name}\n"
            response += f"Остаток: {business.balance:,.2f} ₽"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ])
        
        await callback.message.edit_text(response, reply_markup=keyboard)
        await state.clear()
        await callback.answer()
        
    finally:
        session.close()



@router.callback_query(F.data.in_({"receipt_confirm_account_card", "receipt_confirm_account_cash"}))
async def process_receipt_confirm_account(callback: types.CallbackQuery, state: FSMContext):
    """Finalize receipt confirmation when user selects account."""
    current_state = await state.get_state()
    if current_state != ReceiptStates.waiting_for_account_choice:
        await callback.answer()
        return

    data = await state.get_data()
    items = data.get('items', [])
    corrected_total = data.get('receipt_corrected_total')
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        total_amount = corrected_total if corrected_total else sum(item.get('amount', 0) for item in items)

        family_budget = session.query(FamilyBudget).first()
        if not family_budget:
            family_budget = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(family_budget)
            session.flush()

        # Prepare adjusted items same as in confirm_receipt
        adjusted_items = []
        if items:
            orig_sum = sum(float(item.get('amount', 0) or 0.0) for item in items)
            if corrected_total and orig_sum > 0:
                for it in items:
                    adjusted_items.append({**it, '_adjusted_amount': float(it.get('amount', 0) or 0.0)})
            elif corrected_total and orig_sum == 0:
                per = round(float(total_amount) / len(items), 2)
                running = 0.0
                for it in items:
                    adjusted_items.append({**it, '_adjusted_amount': per})
                    running += per
                diff = round(float(total_amount) - running, 2)
                if adjusted_items:
                    adjusted_items[-1]['_adjusted_amount'] = round(adjusted_items[-1]['_adjusted_amount'] + diff, 2)
            else:
                for it in items:
                    adjusted_items.append({**it, '_adjusted_amount': float(it.get('amount', 0) or 0.0)})

        # Determine selected account
        selected = 'card' if callback.data == 'receipt_confirm_account_card' else 'cash'

        # Check funds on selected account (require full amount on chosen account)
        if selected == 'card' and (family_budget.card_balance or 0.0) < total_amount:
            await callback.message.edit_text(f"❌ Недостаточно средств на карте!\n\nДоступно: {family_budget.card_balance:,.2f} ₽\nТребуется: {total_amount:,.2f} ₽")
            await state.clear()
            await callback.answer()
            return
        if selected == 'cash' and (family_budget.cash_balance or 0.0) < total_amount:
            await callback.message.edit_text(f"❌ Недостаточно наличных!\n\nДоступно: {family_budget.cash_balance:,.2f} ₽\nТребуется: {total_amount:,.2f} ₽")
            await state.clear()
            await callback.answer()
            return

        # Create operation
        operation = Operation(
            user_id=user.id,
            type='family_expense',
            total_amount=total_amount,
            account_type=selected
        )
        session.add(operation)
        session.flush()

        for item_data in adjusted_items:
            category = None
            if item_data.get('category'):
                category = session.query(Category).filter_by(name=item_data['category'], parent_id=None).first()
            amount_to_use = item_data.get('_adjusted_amount', item_data.get('amount', 0))
            op_item = OperationItem(
                operation_id=operation.id,
                name=item_data.get('name', item_data.get('description', 'Без названия')),
                amount=amount_to_use,
                category_id=category.id if category else None,
                subcategory=item_data.get('subcategory')
            )
            session.add(op_item)

        # Deduct from selected account
        if selected == 'card':
            family_budget.card_balance = (family_budget.card_balance or 0.0) - total_amount
        else:
            family_budget.cash_balance = (family_budget.cash_balance or 0.0) - total_amount
        family_budget.balance = (family_budget.card_balance or 0.0) + (family_budget.cash_balance or 0.0)
        session.commit()

        response = f"✅ Чек добавлен в семейный бюджет!\n\n"
        response += f"Позиций: {len(adjusted_items)}\n"
        response += f"Итого: -{total_amount:,.2f} ₽\n\n"
        response += f"👨‍👩‍👧 Семейный бюджет\n"
        response += f"Остаток: {family_budget.balance:,.2f} ₽ (Карта: {family_budget.card_balance:,.2f} ₽, Наличные: {family_budget.cash_balance:,.2f} ₽)"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]])
        await callback.message.edit_text(response, reply_markup=keyboard)
        await state.clear()
        await callback.answer()

    finally:
        session.close()
