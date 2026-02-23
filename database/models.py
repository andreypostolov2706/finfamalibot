"""
Модели базы данных
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class FamilyBudget(Base):
    """Общий семейный бюджет (один на всю семью)"""
    __tablename__ = 'family_budget'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Старое поле `balance` сохраняем для совместимости, но вводим разделение:
    # `card_balance` — средства на карте, `cash_balance` — наличные
    balance = Column(Float, default=0.0)
    card_balance = Column(Float, default=0.0)
    cash_balance = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    """Пользователь Telegram"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    family_balance = Column(Float, default=0.0)  # Оставляем для совместимости, но не используем
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    business_account = relationship("BusinessAccount", back_populates="user", uselist=False)
    operations = relationship("Operation", back_populates="user")


class BusinessAccount(Base):
    """Бизнес-аккаунт пользователя"""
    __tablename__ = 'business_accounts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(255), nullable=False)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="business_account")
    piggy_banks = relationship("PiggyBank", back_populates="business_account")


class Operation(Base):
    """Операция (группировка позиций)"""
    __tablename__ = 'operations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    type = Column(String(50), nullable=False)  # family_expense, business_income, business_expense, salary, piggy_deposit, piggy_withdraw
    account_type = Column(String(20), nullable=True)  # 'card', 'cash', 'business', 'mixed' - for family ops
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="operations")
    items = relationship("OperationItem", back_populates="operation", cascade="all, delete-orphan")


class OperationItem(Base):
    """Позиция в операции"""
    __tablename__ = 'operation_items'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(Integer, ForeignKey('operations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    subcategory = Column(String(255), nullable=True)
    
    # Relationships
    operation = relationship("Operation", back_populates="items")
    category = relationship("Category")


class Category(Base):
    """Категория расходов/доходов"""
    __tablename__ = 'categories'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    emoji = Column(String(10), nullable=True)
    parent_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    parent = relationship("Category", remote_side=[id])


class PiggyBank(Base):
    """Копилка"""
    __tablename__ = 'piggy_banks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    business_account_id = Column(Integer, ForeignKey('business_accounts.id'), nullable=True)
    name = Column(String(255), nullable=False)
    balance = Column(Float, default=0.0)
    is_auto = Column(Boolean, default=False)  # Автоматическая копилка "Шекель 10%"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    business_account = relationship("BusinessAccount", back_populates="piggy_banks")


class FixedPayment(Base):
    """Фиксированный платеж (кредит)"""
    __tablename__ = 'fixed_payments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    payment_day = Column(Integer, nullable=False)  # День месяца (1-31)
    is_active = Column(Boolean, default=True)
    # Опционный счёт по умолчанию (BusinessAccount.id) и категория
    default_account_id = Column(Integer, ForeignKey('business_accounts.id'), nullable=True)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FixedPaymentDue(Base):
    """Начисление фиксированного платежа на конкретный месяц"""
    __tablename__ = 'fixed_payment_dues'

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixed_payment_id = Column(Integer, ForeignKey('fixed_payments.id'), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    due_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0.0)
    is_paid = Column(Boolean, default=False)
    skipped = Column(Boolean, default=False)
    paid_at = Column(DateTime, nullable=True)
    paid_account_id = Column(Integer, ForeignKey('business_accounts.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    fixed_payment = relationship('FixedPayment')


class Debt(Base):
    """Долг (кому должны или кто должен нам)"""
    __tablename__ = 'debts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    person_name = Column(String(255), nullable=False)   # Имя должника/кредитора
    amount = Column(Float, nullable=False)               # Сумма долга
    description = Column(Text, nullable=True)            # Описание
    debt_type = Column(String(20), nullable=False)       # 'owe_me' (мне должны) / 'i_owe' (я должен)
    is_paid = Column(Boolean, default=False)             # Погашен ли долг
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)            # Дата погашения
    
    # Relationships
    user = relationship("User")
