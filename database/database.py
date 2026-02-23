"""
Управление базой данных
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base, Category, FamilyBudget
import config


# Создание движка базы данных
engine = create_engine(f'sqlite:///{config.DATABASE_PATH}', echo=False)

# Создание фабрики сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Инициализация базы данных"""
    # Создание директории для базы данных
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    
    # Создание всех таблиц
    Base.metadata.create_all(bind=engine)
    
    # Добавление системных данных
    session = SessionLocal()
    try:
        # Создание общего семейного бюджета (если не существует)
        if session.query(FamilyBudget).count() == 0:
            # Инициализация с разделением на карту и наличные
            family_budget = FamilyBudget(card_balance=0.0, cash_balance=0.0, balance=0.0)
            session.add(family_budget)
            session.commit()
        
        # Проверка, есть ли уже категории
        if session.query(Category).count() == 0:
            create_default_categories(session)
            session.commit()
    finally:
        session.close()


def create_default_categories(session: Session):
    """Создание категорий по умолчанию"""
    
    # Категории для семейного бюджета
    family_categories = [
        {"name": "Жильё", "emoji": "🏠", "subcategories": ["Аренда", "Ипотека", "Коммунальные", "Ремонт"]},
        {"name": "Продукты", "emoji": "🛒", "subcategories": ["Молочные продукты", "Хлебобулочные", "Овощи", "Фрукты", "Мясо", "Рыба", "Напитки", "Шоколад", "Конфеты"]},
        {"name": "Транспорт", "emoji": "🚗", "subcategories": ["Бензин", "Запчасти", "Ремонт", "Страховка"]},
        {"name": "Развлечения", "emoji": "🎮", "subcategories": ["Кино", "Рестораны", "Игры", "Детские товары"]},
        {"name": "Одежда", "emoji": "👕", "subcategories": ["Взрослая", "Детская", "Обувь"]},
        {"name": "Здоровье", "emoji": "💊", "subcategories": ["Лекарства", "Врачи", "Анализы"]},
        {"name": "Связь", "emoji": "📱", "subcategories": ["Интернет", "Мобильная связь"]},
        {"name": "Образование", "emoji": "🎓", "subcategories": ["Курсы", "Книги", "Школа"]},
    ]
    
    # Категории для бизнеса
    business_categories = [
        {"name": "Продажи", "emoji": "💰", "subcategories": ["Электроника", "Одежда", "Продукты", "Услуги"]},
        {"name": "Закупки", "emoji": "📦", "subcategories": ["Товары", "Материалы", "Оборудование"]},
        {"name": "Операционные расходы", "emoji": "💼", "subcategories": ["Аренда", "Зарплата сотрудникам", "Реклама", "Налоги"]},
    ]
    
    # Добавление категорий
    for cat_data in family_categories + business_categories:
        category = Category(
            name=cat_data["name"],
            emoji=cat_data.get("emoji"),
            is_system=True
        )
        session.add(category)
        session.flush()  # Получить ID категории
        
        # Добавление подкатегорий
        for subcat_name in cat_data.get("subcategories", []):
            subcategory = Category(
                name=subcat_name,
                parent_id=category.id,
                is_system=True
            )
            session.add(subcategory)


def get_session() -> Session:
    """Получение сессии базы данных"""
    return SessionLocal()
