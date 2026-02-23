from database import get_session


def main():
    session = get_session()
    try:
        from sqlalchemy import text
        rows = session.execute(text("SELECT fp.id, fp.name, fp.amount, fp.payment_day, fpd.id as due_id, fpd.year, fpd.month, fpd.due_amount, fpd.paid_amount, fpd.is_paid, fpd.skipped FROM fixed_payments fp LEFT JOIN fixed_payment_dues fpd ON fp.id=fpd.fixed_payment_id ORDER BY fpd.year DESC, fpd.month DESC")).fetchall()
        if not rows:
            print('No fixed payments or dues found')
            return

        for r in rows:
            # r is a Row; convert to mapping for friendly print
            print(dict(r._mapping))
    finally:
        session.close()


if __name__ == '__main__':
    main()
