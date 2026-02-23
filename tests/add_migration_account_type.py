# Simple migration: add account_type column to operations table if missing
from database.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE operations ADD COLUMN account_type VARCHAR(20)"))
        print('Column account_type added to operations')
    except Exception as e:
        print('Migration skipped or failed:', e)
