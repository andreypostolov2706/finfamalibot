"""Миграция: добавить колонки card_balance и cash_balance в family_budget, если их нет."""
import sqlite3
import os
import config


def run():
    db_path = config.DATABASE_PATH
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info('family_budget')")
    cols = [row[1] for row in cur.fetchall()]

    changed = False
    if 'card_balance' not in cols:
        print('Adding column card_balance...')
        cur.execute("ALTER TABLE family_budget ADD COLUMN card_balance FLOAT DEFAULT 0.0")
        changed = True
    else:
        print('Column card_balance already exists')

    if 'cash_balance' not in cols:
        print('Adding column cash_balance...')
        cur.execute("ALTER TABLE family_budget ADD COLUMN cash_balance FLOAT DEFAULT 0.0")
        changed = True
    else:
        print('Column cash_balance already exists')

    if changed:
        conn.commit()
        print('Migration applied')
    else:
        print('No changes needed')

    conn.close()


if __name__ == '__main__':
    run()
