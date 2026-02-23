# Test script: populate DB with sample salaries/income and print dashboard
from database import get_session, User, BusinessAccount, FamilyBudget, Operation, OperationItem
from handlers.family_budget import get_dashboard

session = get_session()
try:
    # Ensure test user exists
    user = session.query(User).filter_by(telegram_id=999999999).first()
    if not user:
        user = User(telegram_id=999999999, name='TestUser')
        session.add(user)
        session.flush()
    # Ensure family budget exists
    fb = session.query(FamilyBudget).first()
    if not fb:
        fb = FamilyBudget(balance=0.0, card_balance=0.0, cash_balance=0.0)
        session.add(fb)
        session.flush()
    # Clear recent test operations (simple cleanup)
    session.query(Operation).filter(Operation.user_id==user.id).delete()
    session.commit()
    # Add salary operations (account_type set)
    salaries = [
        ('Scrib', 1000.0, 'card'),
        ('Scrib', 5000.0, 'card'),
        ('Наталья', 3000.0, 'cash'),
        ('Наталья', 4000.0, 'card')
    ]
    for name, amt, acc in salaries:
        op = Operation(user_id=user.id, type='salary', total_amount=amt, account_type=acc)
        session.add(op)
        session.flush()
        item = OperationItem(operation_id=op.id, name=f"Зарплата {name}", amount=amt)
        session.add(item)
    # Add family income
    inc = Operation(user_id=user.id, type='family_income', total_amount=2610.0, account_type='card')
    session.add(inc)
    session.flush()
    session.commit()

    # Print dashboard
    text = get_dashboard(session, user)
    # get_dashboard is async; if it's coroutine, run it
    import asyncio
    if asyncio.iscoroutine(text):
        text = asyncio.get_event_loop().run_until_complete(text)
    print(text)
finally:
    session.close()
