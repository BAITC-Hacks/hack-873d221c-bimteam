"""Обзор площадок для сравнения цен, без обещания доступности на дату."""
import re

VENUE_CATEGORIES = {'Банкетный зал', 'Загородная площадка', 'Ресторан', 'Отель'}


def venue_name(row):
    # Берём название дословно из описания, не пытаясь восстановить реальные бренды.
    match = re.match(r'^([^\n–—]{2,80}?)\s+[–—]\s+', row['description'].strip())
    return match.group(1).strip() if match else row['anon_name']


def venue_catalog(catalog, city=None):
    venues = []
    for row in catalog:
        categories = [c for c in row['categories'] if c in VENUE_CATEGORIES]
        if not categories or (city is not None and row['city'] != city):
            continue
        venues.append({
            'id': row['id'], 'name': venue_name(row), 'profile_name': row['anon_name'],
            'category': categories[0], 'categories': categories, 'city': row['city'],
            'price_from_kzt': row['price_from_kzt'], 'description': row['description'],
            'price_imputed': row['price_imputed'], 'city_imputed': row['city_imputed'],
            'synthetic': row['synthetic'],
        })
    venues.sort(key=lambda v: (v['price_from_kzt'], v['id']))
    return {'venues': venues, 'availability_checked': False}
