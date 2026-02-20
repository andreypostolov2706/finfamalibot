"""
Обработчики для управления долгами
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_session, User, Debt
from datetime import datetime

router = Router()


class DebtStates(StatesGroup):
    """Состояния для работы с долгами"""
    waiting_for_debt_type = State()
    waiting_for_person_name = State()
    waiting_for_amount = State()
    waiting_for_description = State()
    waiting_for_delete_id = State()


def get_debts_menu() -> InlineKeyboardMarkup:
    """Меню долгов"""
    keyboard = [
        [
            InlineKeyboardButton(text="➕ Добавить долг", callback_data="debt_add")
        ],
        [
            InlineKeyboardButton(text="✅ Погасить долг", callback_data="debt_pay"),
            InlineKeyboardButton(text="🗑️ Удалить долг", callback_data="debt_delete")
        ],
        [
            InlineKeyboardButton(text="📋 Все долги", callback_data="debt_list")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_debt_type_keyboard() -> InlineKeyboardMarkup:
    """Выбор типа долга"""
    keyboard = [
        [
            InlineKeyboardButton(text="🤝 Мне должны", callback_data="debt_type_owe_me")
        ],
        [
            InlineKeyboardButton(text="💸 Я должен", callback_data="debt_type_i_owe")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="menu_debts")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data == "menu_debts")
async def show_debts_menu(callback: types.CallbackQuery, state: FSMContext):
    """Показать меню долгов"""
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        if not user:
            await callback.answer("Пожалуйста, используйте /start")
            return
        
        # Получаем активные долги
        debts = session.query(Debt).filter_by(user_id=user.id, is_paid=False).all()
        
        owe_me = [d for d in debts if d.debt_type == 'owe_me']
        i_owe = [d for d in debts if d.debt_type == 'i_owe']
        
        total_owe_me = sum(d.amount for d in owe_me)
        total_i_owe = sum(d.amount for d in i_owe)
        
        text = "💰 ДОЛГИ\n\n"
        
        if owe_me:
            text += f"🤝 МНЕ ДОЛЖНЫ ({len(owe_me)} чел.):\n"
            text += "─────────────\n"
            for d in owe_me:
                text += f"• {d.person_name}: {d.amount:,.2f} ₽"
                if d.description:
                    text += f" ({d.description})"
                text += f" [ID:{d.id}]\n"
            text += f"Итого: {total_owe_me:,.2f} ₽\n\n"
        else:
            text += "🤝 Мне никто не должен\n\n"
        
        if i_owe:
            text += f"💸 Я ДОЛЖЕН ({len(i_owe)} чел.):\n"
            text += "─────────────\n"
            for d in i_owe:
                text += f"• {d.person_name}: {d.amount:,.2f} ₽"
                if d.description:
                    text += f" ({d.description})"
                text += f" [ID:{d.id}]\n"
            text += f"Итого: {total_i_owe:,.2f} ₽\n\n"
        else:
            text += "💸 Я никому не должен\n\n"
        
        net = total_owe_me - total_i_owe
        if net > 0:
            text += f"📊 Баланс долгов: +{net:,.2f} ₽ (в вашу пользу)"
        elif net < 0:
            text += f"📊 Баланс долгов: {net:,.2f} ₽ (не в вашу пользу)"
        else:
            text += "📊 Баланс долгов: 0 ₽"
        
        await callback.message.edit_text(text, reply_markup=get_debts_menu())
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "debt_add")
async def debt_add_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления долга"""
    await state.set_state(DebtStates.waiting_for_debt_type)
    await callback.message.edit_text(
        "💰 Добавление долга\n\n"
        "Выберите тип долга:",
        reply_markup=get_debt_type_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.in_(["debt_type_owe_me", "debt_type_i_owe"]))
async def debt_type_selected(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа долга"""
    debt_type = "owe_me" if callback.data == "debt_type_owe_me" else "i_owe"
    await state.update_data(debt_type=debt_type)
    await state.set_state(DebtStates.waiting_for_person_name)
    
    if debt_type == "owe_me":
        prompt = "Кто вам должен? Введите имя:"
    else:
        prompt = "Кому вы должны? Введите имя:"
    
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_debts")]]
    await callback.message.edit_text(
        f"💰 Добавление долга\n\n{prompt}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.message(DebtStates.waiting_for_person_name)
async def debt_person_name(message: types.Message, state: FSMContext):
    """Получение имени"""
    await state.update_data(person_name=message.text.strip())
    await state.set_state(DebtStates.waiting_for_amount)
    
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_debts")]]
    await message.answer(
        "💰 Введите сумму долга (в рублях):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@router.message(DebtStates.waiting_for_amount)
async def debt_amount(message: types.Message, state: FSMContext):
    """Получение суммы"""
    import re
    match = re.search(r'(\d+(?:[.,]\d+)?)', message.text)
    if not match:
        await message.answer("❌ Введите корректную сумму (например: 1500 или 1500.50)")
        return
    
    amount = float(match.group(1).replace(',', '.'))
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(DebtStates.waiting_for_description)
    
    keyboard = [
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="debt_skip_description")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_debts")]
    ]
    await message.answer(
        f"💰 Сумма: {amount:,.2f} ₽\n\n"
        "Добавьте описание (за что долг) или пропустите:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@router.callback_query(F.data == "debt_skip_description")
async def debt_skip_description(callback: types.CallbackQuery, state: FSMContext):
    """Пропустить описание"""
    await _save_debt(callback.message, state, description=None, edit=True)
    await callback.answer()


@router.message(DebtStates.waiting_for_description)
async def debt_description(message: types.Message, state: FSMContext):
    """Получение описания"""
    await _save_debt(message, state, description=message.text.strip(), edit=False)


async def _save_debt(message: types.Message, state: FSMContext, description, edit: bool):
    """Сохранение долга в БД"""
    data = await state.get_data()
    await state.clear()
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.chat.id).first()
        if not user:
            return
        
        debt = Debt(
            user_id=user.id,
            person_name=data['person_name'],
            amount=data['amount'],
            description=description,
            debt_type=data['debt_type'],
            is_paid=False
        )
        session.add(debt)
        session.commit()
        
        if data['debt_type'] == 'owe_me':
            type_text = f"🤝 {data['person_name']} должен вам"
        else:
            type_text = f"💸 Вы должны {data['person_name']}"
        
        response = f"✅ Долг добавлен!\n\n"
        response += f"{type_text}\n"
        response += f"Сумма: {data['amount']:,.2f} ₽\n"
        if description:
            response += f"Описание: {description}\n"
        response += f"ID: {debt.id}"
        
        keyboard = [
            [InlineKeyboardButton(text="💰 К долгам", callback_data="menu_debts")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        if edit:
            await message.edit_text(response, reply_markup=markup)
        else:
            await message.answer(response, reply_markup=markup)
            
    finally:
        session.close()


@router.callback_query(F.data == "debt_list")
async def debt_list(callback: types.CallbackQuery, state: FSMContext):
    """Список всех долгов (включая погашенные)"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        if not user:
            await callback.answer("Пожалуйста, используйте /start")
            return
        
        debts = session.query(Debt).filter_by(user_id=user.id).order_by(Debt.created_at.desc()).all()
        
        if not debts:
            await callback.answer("Долгов нет", show_alert=True)
            return
        
        text = "📋 ВСЕ ДОЛГИ\n\n"
        
        active = [d for d in debts if not d.is_paid]
        paid = [d for d in debts if d.is_paid]
        
        if active:
            text += "🔴 АКТИВНЫЕ:\n"
            for d in active:
                icon = "🤝" if d.debt_type == "owe_me" else "💸"
                text += f"{icon} [{d.id}] {d.person_name}: {d.amount:,.2f} ₽"
                if d.description:
                    text += f" — {d.description}"
                text += f"\n   {d.created_at.strftime('%d.%m.%Y')}\n"
        
        if paid:
            text += "\n✅ ПОГАШЕННЫЕ:\n"
            for d in paid[:5]:  # Последние 5
                icon = "🤝" if d.debt_type == "owe_me" else "💸"
                text += f"{icon} {d.person_name}: {d.amount:,.2f} ₽"
                if d.paid_at:
                    text += f" ({d.paid_at.strftime('%d.%m.%Y')})"
                text += "\n"
        
        keyboard = [[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_debts")]]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "debt_pay")
async def debt_pay_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало погашения долга"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        debts = session.query(Debt).filter_by(user_id=user.id, is_paid=False).all()
        
        if not debts:
            await callback.answer("Нет активных долгов", show_alert=True)
            return
        
        text = "✅ Погашение долга\n\nВыберите долг:\n\n"
        keyboard = []
        
        for d in debts:
            icon = "🤝" if d.debt_type == "owe_me" else "💸"
            btn_text = f"{icon} [{d.id}] {d.person_name}: {d.amount:,.2f} ₽"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"debt_pay_{d.id}")])
        
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_debts")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("debt_pay_"))
async def debt_pay_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Погашение конкретного долга"""
    debt_id = int(callback.data.split("_")[2])
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        debt = session.query(Debt).filter_by(id=debt_id, user_id=user.id).first()
        
        if not debt:
            await callback.answer("Долг не найден", show_alert=True)
            return
        
        debt.is_paid = True
        debt.paid_at = datetime.utcnow()
        session.commit()
        
        if debt.debt_type == "owe_me":
            text = f"✅ {debt.person_name} вернул вам {debt.amount:,.2f} ₽"
        else:
            text = f"✅ Вы вернули {debt.person_name} {debt.amount:,.2f} ₽"
        
        keyboard = [
            [InlineKeyboardButton(text="💰 К долгам", callback_data="menu_debts")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data == "debt_delete")
async def debt_delete_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало удаления долга"""
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        debts = session.query(Debt).filter_by(user_id=user.id, is_paid=False).all()
        
        if not debts:
            await callback.answer("Нет активных долгов для удаления", show_alert=True)
            return
        
        text = "🗑️ Удаление долга\n\nВыберите долг для удаления:\n\n"
        keyboard = []
        
        for d in debts:
            icon = "🤝" if d.debt_type == "owe_me" else "💸"
            btn_text = f"{icon} [{d.id}] {d.person_name}: {d.amount:,.2f} ₽"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"debt_del_{d.id}")])
        
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_debts")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        
    finally:
        session.close()


@router.callback_query(F.data.startswith("debt_del_"))
async def debt_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Удаление конкретного долга"""
    debt_id = int(callback.data.split("_")[2])
    
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        debt = session.query(Debt).filter_by(id=debt_id, user_id=user.id).first()
        
        if not debt:
            await callback.answer("Долг не найден", show_alert=True)
            return
        
        name = debt.person_name
        amount = debt.amount
        session.delete(debt)
        session.commit()
        
        keyboard = [
            [InlineKeyboardButton(text="💰 К долгам", callback_data="menu_debts")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ]
        await callback.message.edit_text(
            f"🗑️ Долг удалён!\n\n{name}: {amount:,.2f} ₽",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer()
        
    finally:
        session.close()
