"""Тестовый сценарий: создание операций и проверка отката при удалении.

Запускается локально в проекте. Выводит балансы до и после удаления операций.
"""
from database import get_session, User, FamilyBudget, BusinessAccount, Operation, OperationItem, FixedPayment, FixedPaymentDue, PiggyBank
from datetime import datetime


def print_balances(session, note=""):
    fb = session.query(FamilyBudget).first()
    ba = session.query(BusinessAccount).first()
    pig = session.query(PiggyBank).first()
    print(f"--- {note} ---")
    if fb:
        print(f"Family: total={fb.balance:.2f}, card={fb.card_balance:.2f}, cash={fb.cash_balance:.2f}")
    else:
        print("Family: None")
    if ba:
        print(f"Business: {ba.name} balance={ba.balance:.2f}")
    else:
        print("Business: None")
    if pig:
        print(f"Piggy: balance={pig.balance:.2f}")
    else:
        print("Piggy: None")


def ensure_entities(session):
    user = session.query(User).filter_by(telegram_id=999999999).first()
    if not user:
        user = User(telegram_id=999999999, name='Tester')
        session.add(user)
        session.flush()

    ba = session.query(BusinessAccount).filter_by(user_id=user.id).first()
    if not ba:
        ba = BusinessAccount(user_id=user.id, name='TestBiz', balance=10000.0)
        session.add(ba)

    fb = session.query(FamilyBudget).first()
    if not fb:
        fb = FamilyBudget(balance=0.0, card_balance=1000.0, cash_balance=500.0)
        session.add(fb)

    pig = session.query(PiggyBank).filter_by(is_auto=True).first()
    if not pig:
        pig = PiggyBank(name="Шекель 10%", balance=100.0, is_auto=True)
        session.add(pig)

    session.commit()
    return user, fb, ba, pig


def rollback_and_delete(session, operation):
    # copy of rollback logic from callbacks.py
    try:
        total = operation.total_amount or sum((it.amount or 0.0) for it in operation.items)
    except Exception:
        total = 0.0

    fb = session.query(FamilyBudget).first()

    if operation.type == 'family_expense':
        acct = (operation.account_type or '').lower()
        if fb:
            if acct == 'cash':
                fb.cash_balance = (fb.cash_balance or 0.0) + total
            else:
                fb.card_balance = (fb.card_balance or 0.0) + total
            fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)

        if len(operation.items) == 1:
            item = operation.items[0]
            fp = session.query(FixedPayment).filter_by(name=item.name).first()
            if fp:
                op_date = operation.created_at
                due = session.query(FixedPaymentDue).filter_by(fixed_payment_id=fp.id, year=op_date.year, month=op_date.month).first()
                if due and due.is_paid:
                    due.paid_amount = max(0.0, (due.paid_amount or 0.0) - (item.amount or 0.0))
                    if (due.paid_amount or 0.0) < due.due_amount:
                        due.is_paid = False
                        due.paid_at = None

    elif operation.type == 'family_income':
        acct = (operation.account_type or '').lower()
        if fb:
            if acct == 'cash':
                fb.cash_balance = (fb.cash_balance or 0.0) - total
            else:
                fb.card_balance = (fb.card_balance or 0.0) - total
            fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)

    elif operation.type == 'salary':
        business_account = session.query(BusinessAccount).filter_by(user_id=operation.user_id).first()
        if business_account:
            business_account.balance = (business_account.balance or 0.0) + total

        family_amount = (total or 0.0) * 0.9
        piggy_amount = (total or 0.0) * 0.1
        acct = (operation.account_type or '').lower()
        if fb:
            if acct == 'cash':
                fb.cash_balance = (fb.cash_balance or 0.0) - family_amount
            else:
                fb.card_balance = (fb.card_balance or 0.0) - family_amount
            fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)

        piggy = session.query(PiggyBank).filter_by(is_auto=True).first()
        if piggy:
            piggy.balance = (piggy.balance or 0.0) - piggy_amount

    elif operation.type == 'business_income':
        ba = session.query(BusinessAccount).filter_by(user_id=operation.user_id).first()
        if ba:
            ba.balance = (ba.balance or 0.0) - total

    elif operation.type == 'business_expense':
        ba = session.query(BusinessAccount).filter_by(user_id=operation.user_id).first()
        if ba:
            ba.balance = (ba.balance or 0.0) + total

    elif operation.type == 'piggy_deposit':
        piggy = session.query(PiggyBank).first()
        if piggy:
            piggy.balance = (piggy.balance or 0.0) - total

    elif operation.type == 'piggy_withdraw':
        piggy = session.query(PiggyBank).first()
        if piggy:
            piggy.balance = (piggy.balance or 0.0) + total

    if fb:
        fb.card_balance = max(0.0, fb.card_balance or 0.0)
        fb.cash_balance = max(0.0, fb.cash_balance or 0.0)
        fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)

    # Finally delete
    session.delete(operation)
    session.commit()


def run():
    session = get_session()
    try:
        user, fb, ba, pig = ensure_entities(session)

        print_balances(session, 'Initial')

        # 1) family_expense
        op = Operation(user_id=user.id, type='family_expense', total_amount=500.0, account_type='cash', created_at=datetime.now())
        session.add(op)
        session.flush()
        item = OperationItem(operation_id=op.id, name='Test Expense', amount=500.0)
        session.add(item)
        session.commit()

        print_balances(session, 'After creating family_expense')
        rollback_and_delete(session, op)
        print_balances(session, 'After deleting family_expense')

        # 2) family_income
        op2 = Operation(user_id=user.id, type='family_income', total_amount=300.0, account_type='card', created_at=datetime.now())
        session.add(op2)
        session.flush()
        item2 = OperationItem(operation_id=op2.id, name='Test Income', amount=300.0)
        session.add(item2)
        # apply income to family budget (simulate original commit behavior)
        fb.card_balance = (fb.card_balance or 0.0) + 300.0
        fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)
        session.commit()

        print_balances(session, 'After creating family_income')
        rollback_and_delete(session, op2)
        print_balances(session, 'After deleting family_income')

        # 3) salary
        op3 = Operation(user_id=user.id, type='salary', total_amount=1000.0, account_type='card', created_at=datetime.now())
        session.add(op3)
        session.flush()
        item3 = OperationItem(operation_id=op3.id, name='Salary pay', amount=1000.0)
        session.add(item3)
        # Simulate original salary effects: business -1000, family +900 card, piggy +100
        ba.balance = (ba.balance or 0.0) - 1000.0
        fb.card_balance = (fb.card_balance or 0.0) + 900.0
        pig.balance = (pig.balance or 0.0) + 100.0
        fb.balance = (fb.card_balance or 0.0) + (fb.cash_balance or 0.0)
        session.commit()

        print_balances(session, 'After creating salary')
        rollback_and_delete(session, op3)
        print_balances(session, 'After deleting salary')

    finally:
        session.close()


if __name__ == '__main__':
    run()
