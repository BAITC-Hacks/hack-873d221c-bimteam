"""Обзор площадок для сравнения цен, без обещания доступности на дату."""
import re

from app.data import Contractor

VENUE_CATEGORIES = frozenset({'Банкетный зал', 'Загородная площадка', 'Ресторан', 'Отель'})


def venue_name(row: Contractor) -> str:
    """Название дословно из описания; не восстанавливаем реальные бренды."""
    match = re.match(r'^([^\n–—]{2,80}?)\s+[–—]\s+', row.description.strip())
    return match.group(1).strip() if match else row.name


def venue_catalog(rows: list[Contractor], city: str | None = None) -> dict:
    """Один исходный каталог, стабильный порядок, без изменения фильтров подбора."""
    venues = []
    for row in rows:
        categories = [category for category in row.categories if category in VENUE_CATEGORIES]
        if not categories or (city is not None and row.city != city):
            continue
        venues.append({
            'id': row.id, 'name': venue_name(row), 'profile_name': row.name,
            'category': categories[0], 'categories': categories, 'city': row.city,
            'price_from_kzt': row.price_from_kzt, 'description': row.description,
            'price_imputed': row.price_imputed, 'city_imputed': row.city_imputed,
            'synthetic': row.synthetic,
        })
    venues.sort(key=lambda venue: (venue['price_from_kzt'], venue['id']))
    return {'venues': venues, 'availability_checked': False}
