"""
Миграционный скрипт для добавления колонок card_balance и cash_balance
в таблицу family_budget и копирования старого значения balance в card_balance.
Запуск: .venv\Scripts\python.exe scripts\migrate_add_card_cash.py
"""
import sys
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from database.database import engine

SQL_ADD_CARD = "ALTER TABLE family_budget ADD COLUMN card_balance FLOAT DEFAULT 0.0"
SQL_ADD_CASH = "ALTER TABLE family_budget ADD COLUMN cash_balance FLOAT DEFAULT 0.0"
SQL_COPY = "UPDATE family_budget SET card_balance = COALESCE(balance, 0.0) WHERE card_balance IS NULL OR card_balance = 0.0"


def main():
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            try:
                conn.execute(text(SQL_ADD_CARD))
                print('Added column card_balance')
            except OperationalError as e:
                print('card_balance likely exists or error:', e)
            try:
                conn.execute(text(SQL_ADD_CASH))
                print('Added column cash_balance')
            except OperationalError as e:
                print('cash_balance likely exists or error:', e)

            # Копируем старый баланс в card_balance, если он пустой
            try:
                conn.execute(text(SQL_COPY))
                print('Copied balance -> card_balance')
            except Exception as e:
                print('Warning copying balance:', e)

            trans.commit()
        except Exception as e:
            trans.rollback()
            print('Migration failed:', e)
            sys.exit(1)

    print('Migration complete')


if __name__ == '__main__':
    main()
