"""
Обработчики для оплаты фиксированных платежей
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_session, FixedPayment, FixedPaymentDue, Operation, OperationItem, FamilyBudget, BusinessAccount

router = Router()


class PaymentStates(StatesGroup):
    selecting_due = State()
    entering_amount = State()
    selecting_account = State()


@router.message(F.text.in_(["Оплатить платеж", "Оплатить платёж", "Оплатить"]))
async def start_pay_flow(message: types.Message, state: FSMContext):
    """Показать список неоплаченных начислений текущего месяца"""
    await state.clear()
    session = get_session()
    try:
        from datetime import datetime
        now = datetime.now()
        dues = session.query(FixedPaymentDue).filter_by(year=now.year, month=now.month, is_paid=False, skipped=False).all()

        if not dues:
            await message.answer("✅ Нет неоплаченных платежей на этот месяц.")
            return

        text = "Выберите платёж для оплаты:\n\n"
        mapping = []
        for i, d in enumerate(dues, 1):
            p = session.query(FixedPayment).get(d.fixed_payment_id)
            remaining = max(0.0, d.due_amount - (d.paid_amount or 0.0))
            text += f"{i}. {p.name}: {remaining:,.0f} ₽ (до {p.payment_day} числа)\n"
            mapping.append(d.id)

        await state.update_data(due_mapping=mapping)
        await state.set_state(PaymentStates.selecting_due)
        await message.answer(text + "\nВведите номер платежа:")
    finally:
        session.close()


@router.message(PaymentStates.selecting_due)
async def select_due(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        index = int(message.text.strip()) - 1
    except ValueError:
        await message.answer("❌ Введите номер платежа (число):")
        return

    mapping = data.get('due_mapping') or []
    if index < 0 or index >= len(mapping):
        await message.answer("❌ Неверный номер. Попробуйте снова:")
        return

    due_id = mapping[index]
    await state.update_data(selected_due_id=due_id)
    session = get_session()
    try:
        d = session.query(FixedPaymentDue).get(due_id)
        p = session.query(FixedPayment).get(d.fixed_payment_id)
        remaining = max(0.0, d.due_amount - (d.paid_amount or 0.0))
        await state.set_state(PaymentStates.entering_amount)
        await message.answer(f"Вы выбрали: {p.name}. Остаток: {remaining:,.2f} ₽\nВведите сумму для оплаты или 'все' для полной оплаты:")
    finally:
        session.close()


@router.message(PaymentStates.entering_amount)
async def entering_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    due_id = data.get('selected_due_id')
    session = get_session()
    try:
        d = session.query(FixedPaymentDue).get(due_id)
        p = session.query(FixedPayment).get(d.fixed_payment_id)
        remaining = max(0.0, d.due_amount - (d.paid_amount or 0.0))

        text = message.text.strip().lower()
        if text in ['все', 'всё', 'all']:
            amount = remaining
        else:
            try:
                import re
                nums = re.findall(r'\d+(?:[\.,]\d+)?', message.text)
                if not nums:
                    await message.answer('❌ Не могу определить сумму. Введите число:')
                    return
                amount = float(nums[0].replace(',', '.'))
            except ValueError:
                await message.answer('❌ Неверный формат. Введите сумму:')
                return

        if amount <= 0:
            await message.answer('❌ Сумма должна быть больше нуля. Введите снова:')
            return
        if amount > remaining:
            await message.answer(f'❌ Сумма больше остатка ({remaining:,.2f}). Введите корректную сумму:')
            return

        # Предложим выбрать метод оплаты: карта или наличные
        opts = []
        fb = session.query(FamilyBudget).first()
        if not fb:
            fb = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(fb)
            session.flush()
        text = "Выберите способ оплаты:\n1. Картой\n2. Наличными"
        opts.append({'type': 'card'})
        opts.append({'type': 'cash'})
        await state.update_data(pay_opts=opts)
        await state.set_state(PaymentStates.selecting_account)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [[InlineKeyboardButton(text="Картой", callback_data="pay_card"), InlineKeyboardButton(text="Наличными", callback_data="pay_cash")]]
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.update_data(pay_opts=opts)
        await state.set_state(PaymentStates.selecting_account)
        await message.answer(text + "\nВведите номер счёта:")
    finally:
        session.close()


@router.message(PaymentStates.selecting_account)
async def selecting_account(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        idx = int(message.text.strip()) - 1
    except ValueError:
        await message.answer('❌ Введите номер счёта:')
    # Теперь используем callback_query для выбора метода оплаты
@router.callback_query(F.data.in_(["pay_card", "pay_cash"]))
async def process_payment_method(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    opts = data.get('pay_opts') or []
    pay_amount = data.get('pay_amount')
    due_id = data.get('selected_due_id')
    session = get_session()
    try:
        d = session.query(FixedPaymentDue).get(due_id)
        p = session.query(FixedPayment).get(d.fixed_payment_id)
        fb = session.query(FamilyBudget).first()
        if not fb:
            fb = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
            session.add(fb)
            session.flush()
        # Проверка баланса
        if callback.data == "pay_card":
            if (fb.card_balance or 0.0) < pay_amount:
                await callback.message.edit_text(
                    f"❌ Недостаточно средств на карте!\nДоступно: {fb.card_balance:,.2f} ₽\nТребуется: {pay_amount:,.2f} ₽"
                )
                await state.clear()
                return
            fb.card_balance -= pay_amount
        else:
            if (fb.cash_balance or 0.0) < pay_amount:
                await callback.message.edit_text(
                    f"❌ Недостаточно наличных!\nДоступно: {fb.cash_balance:,.2f} ₽\nТребуется: {pay_amount:,.2f} ₽"
                )
                await state.clear()
                return
            fb.cash_balance -= pay_amount
        fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)
        # Создаём операцию расхода
        user = session.query(BusinessAccount).first()
        user_id = user.user_id if user else 1
        operation = Operation(user_id=user_id, type='family_expense', total_amount=pay_amount)
        session.add(operation)
        session.flush()
        item = OperationItem(operation_id=operation.id, name=p.name, amount=pay_amount, category_id=getattr(p, 'category_id', None))
        session.add(item)
        # Обновляем запись начисления
        d.paid_amount = (d.paid_amount or 0.0) + pay_amount
        d.paid_account_id = None
        if d.paid_amount >= d.due_amount:
            d.is_paid = True
            from datetime import datetime
            d.paid_at = datetime.now()
        session.commit()
        await callback.message.edit_text(f"✅ Оплата {pay_amount:,.2f} ₽ принята. Спасибо!\nБаланс: {fb.balance:,.2f} ₽ (Карта: {fb.card_balance:,.2f} ₽, Наличные: {fb.cash_balance:,.2f} ₽)")
        await state.clear()
    finally:
        session.close()
