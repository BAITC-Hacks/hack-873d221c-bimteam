"""Проверяемые ограничения и простое воспроизводимое ранжирование."""
from collections import Counter
from datetime import date
from pydantic import BaseModel, Field, field_validator

START = date(2026, 9, 23)
END = date(2026, 12, 31)


class Query(BaseModel):
    city: str = Field(min_length=1, max_length=80)
    date: date
    category: str = Field(min_length=1, max_length=100)
    event_format: str = Field(min_length=1, max_length=80)
    budget: int = Field(ge=0, le=1_000_000_000)
    duration_hours: float | None = Field(default=None, gt=0, le=100)
    language: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator('date')
    @classmethod
    def supported_date(cls, value):
        if not START <= value <= END:
            raise ValueError('Дата должна быть между 23.09.2026 и 31.12.2026: за пределами этого окна календарь неизвестен.')
        return value

    @field_validator('city', 'category', 'event_format', 'language')
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Поле не должно состоять из пробелов.')
        return value.strip() if value else value


REASONS = {'busy': 'заняты на дату', 'budget': 'цена выше бюджета',
           'format': 'не работают с этим форматом', 'duration': 'не хватает часов',
           'language': 'не указан нужный язык'}


def recommend(query, catalog):
    candidates = [r for r in catalog if r['city'] == query.city and query.category in r['categories']]
    rejected = Counter()
    eligible = []
    for row in candidates:
        failures = []
        if query.date.isoformat() in row['busy_dates']:
            failures.append('busy')
        if row['price_from_kzt'] > query.budget:
            failures.append('budget')
        if query.event_format not in row['event_formats']:
            failures.append('format')
        if query.duration_hours is not None and row['max_hours'] is not None and query.duration_hours > row['max_hours']:
            failures.append('duration')
        if query.language and query.language not in row['languages']:
            failures.append('language')
        if failures:
            rejected.update(failures)
        else:
            eligible.append(row)
    # Базовая прозрачная стратегия: меньшая начальная цена, затем стабильный ID.
    eligible.sort(key=lambda r: (r['price_from_kzt'], r['id']))
    results = []
    for row in eligible[:3]:
        facts = [f"свободен {query.date.strftime('%d.%m.%Y')}",
                 f"работает с форматом «{query.event_format}»",
                 f"цена от {row['price_from_kzt']:,} ₸ при бюджете {query.budget:,} ₸".replace(',', ' ')]
        if query.language:
            facts.append(f"язык — {query.language}")
        if query.duration_hours is not None:
            facts.append('длительность присутствия не применяется' if row['max_hours'] is None else f"может работать до {row['max_hours']:g} ч при запросе {query.duration_hours:g} ч")
        excerpt = row['description'].split('. ')[0][:280].strip()
        results.append({
            'id': row['id'], 'name': row['anon_name'], 'category': query.category,
            'city': row['city'], 'price_from_kzt': row['price_from_kzt'],
            'synthetic': row['synthetic'], 'city_imputed': row['city_imputed'],
            'price_imputed': row['price_imputed'],
            'explanation': '; '.join(facts).capitalize() + '.',
            'profile_excerpt': excerpt, 'explanation_source': 'rules',
        })
    status = 'ok' if results else ('no_matches' if candidates else 'no_category_in_city')
    message = (f'Найдено подходящих: {len(eligible)}. Показано: {len(results)}.' if results else
               'В этом городе такой категории нет.' if not candidates else
               'Подрядчики этой категории есть, но никто не проходит по всем условиям.')
    if rejected:
        message += ' Причины исключения: ' + '; '.join(f'{REASONS[k]} — {v}' for k, v in rejected.items()) + '. Один профиль может иметь несколько причин.'
    if 0 < len(results) < 3:
        message += ' Подходящих меньше трёх: ' + ('остальные не прошли условия.' if rejected else 'в этой категории и городе всего столько профилей.')
    return {'status': status, 'results': results, 'eligible_count': len(eligible),
            'candidate_count': len(candidates), 'rejection_summary': dict(rejected), 'message': message}
