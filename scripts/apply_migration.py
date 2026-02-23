"""Simple migration helper for adding new columns and table.

Usage:
    python scripts/apply_migration.py

This script will:
 - add columns `default_account_id` and `category_id` to `fixed_payments` if missing
 - run `Base.metadata.create_all()` to create the `fixed_payment_dues` table

It uses the same DB config as the app.
"""
from sqlalchemy import text
from database.database import engine
from database import Base


def column_exists(conn, table, column):
    res = conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
    cols = [r[1] for r in res]
    return column in cols


def main():
    with engine.connect() as conn:
        # Add columns to fixed_payments if missing
        if not column_exists(conn, 'fixed_payments', 'default_account_id'):
            print('Adding column default_account_id to fixed_payments...')
            conn.execute(text("ALTER TABLE fixed_payments ADD COLUMN default_account_id INTEGER;"))
        else:
            print('Column default_account_id already exists')

        if not column_exists(conn, 'fixed_payments', 'category_id'):
            print('Adding column category_id to fixed_payments...')
            conn.execute(text("ALTER TABLE fixed_payments ADD COLUMN category_id INTEGER;"))
        else:
            print('Column category_id already exists')

        # Create missing tables (FixedPaymentDue)
        print('Creating missing tables via Base.metadata.create_all...')
        Base.metadata.create_all(bind=conn.engine)

    print('Migration finished. Please restart the bot to pick up model changes.')


if __name__ == '__main__':
    main()
