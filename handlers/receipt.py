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
    
    await callback.message.edit_text("🤖 Анализирую чек через ИИ...\n\nЭто может занять несколько секунд.")
    await callback.answer()
    
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
            telegram_file_url = f"https://api.telegram.org/file/bot{(await bot.get_me()).id}/{file.file_path}"
            # Используем токен бота для доступа к файлу
            import config as cfg
            telegram_file_url = f"https://api.telegram.org/file/bot{cfg.BOT_TOKEN}/{file.file_path}"
            
            # Анализ изображения через DeepSeek (URL + байты как fallback)
            items = deepseek.analyze_receipt_image(image_data, categories_data, telegram_file_url)
            
            if not items:
                await callback.message.edit_text(
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
                categories_data=categories_data
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
            text += "Добавить все позиции?"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Добавить всё", callback_data="receipt_confirm"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="menu_main")
                ]
            ])
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            
        finally:
            session.close()
            
    except Exception as e:
        print(f"Ошибка при обработке чека: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка при анализе чека: {str(e)[:100]}\n\n"
            "Попробуйте ещё раз."
        )
        await state.clear()


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
    
    if not items:
        await callback.message.edit_text("❌ Нет позиций для добавления.")
        await state.clear()
        await callback.answer()
        return
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        
        total_amount = sum(item.get('amount', 0) for item in items)
        
        if budget_type == "family":
            # Проверка баланса семейного бюджета
            family_budget = session.query(FamilyBudget).first()
            if not family_budget:
                family_budget = FamilyBudget(balance=0.0)
                session.add(family_budget)
                session.flush()
            
            if family_budget.balance < total_amount:
                await callback.message.edit_text(
                    f"❌ Недостаточно средств в семейном бюджете!\n\n"
                    f"Доступно: {family_budget.balance:,.2f} ₽\n"
                    f"Требуется: {total_amount:,.2f} ₽"
                )
                await state.clear()
                await callback.answer()
                return
            
            # Создание операции
            operation = Operation(
                user_id=user.id,
                type='family_expense',
                total_amount=total_amount
            )
            session.add(operation)
            session.flush()
            
            # Добавление позиций
            for item_data in items:
                category = None
                if item_data.get('category'):
                    category = session.query(Category).filter_by(
                        name=item_data['category'],
                        parent_id=None
                    ).first()
                
                op_item = OperationItem(
                    operation_id=operation.id,
                    name=item_data.get('name', 'Без названия'),
                    amount=item_data.get('amount', 0),
                    category_id=category.id if category else None,
                    subcategory=item_data.get('subcategory')
                )
                session.add(op_item)
            
            # Списание из семейного бюджета
            family_budget.balance -= total_amount
            session.commit()
            
            response = f"✅ Чек добавлен в семейный бюджет!\n\n"
            response += f"Позиций: {len(items)}\n"
            response += f"Итого: -{total_amount:,.2f} ₽\n\n"
            response += f"👨‍👩‍👧 Семейный бюджет\n"
            response += f"Остаток: {family_budget.balance:,.2f} ₽"
            
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
            
            # Добавление позиций
            for item_data in items:
                category = None
                if item_data.get('category'):
                    category = session.query(Category).filter_by(
                        name=item_data['category'],
                        parent_id=None
                    ).first()
                
                op_item = OperationItem(
                    operation_id=operation.id,
                    name=item_data.get('name', 'Без названия'),
                    amount=item_data.get('amount', 0),
                    category_id=category.id if category else None,
                    subcategory=item_data.get('subcategory')
                )
                session.add(op_item)
            
            # Списание из бизнеса
            business.balance -= total_amount
            session.commit()
            
            response = f"✅ Чек добавлен в бизнес!\n\n"
            response += f"Позиций: {len(items)}\n"
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
