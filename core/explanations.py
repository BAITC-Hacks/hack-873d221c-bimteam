"""Объяснения из проверяемых сравнений и точных фрагментов профиля."""
import re

FORMAT_TERMS = {
    'корпоратив': ('корпоратив', 'компан', 'бизнес', 'делов', 'команд'),
    'конференция': ('конференц', 'форум', 'делов', 'бизнес'),
    'свадьба': ('свад', 'невест', 'пар', 'молодож'),
    'той': ('той', 'тоев', 'тои', 'традиц', 'казах'),
    'юбилей': ('юбиле',),
    'день рождения': ('рождени', 'именин', 'детск'),
}


def profile_evidence(description, query):
    """Выбираем содержательный фрагмент, не пересказывая неподтверждённые факты."""
    chunks = [part.strip() for part in re.split(r'(?<=[.!?])\s+|[\n•]+', description) if part.strip()]
    terms = FORMAT_TERMS.get(query.event_format, (query.event_format,))

    def score(text):
        lowered = text.casefold()
        relevant = sum(term in lowered for term in terms)
        concrete = sum(term in lowered for term in ('опыт', 'лет', 'гост', 'человек', 'сценар', 'импров', 'репортаж', 'интерактив', 'джаз'))
        numeric = bool(re.search(r'\d', text))
        greeting = any(term in lowered for term in ('всем привет', 'приветствую всех', 'меня зовут'))
        return relevant * 5 + concrete * 2 + numeric - greeting * 8

    ranked = sorted(enumerate(chunks), key=lambda pair: (-score(pair[1]), pair[0]))
    if not ranked:
        return ''
    # Не обрезаем посередине: обрезка может превратить «не более 300» в иной факт.
    for _, chunk in ranked:
        if len(chunk) <= 280 and score(chunk) > 0:
            return chunk
    for _, chunk in ranked:
        if len(chunk) <= 280:
            return chunk
    return ''


def explanation(row, query, candidates, eligible, excerpt):
    free = [item for item in candidates if query.date.isoformat() not in item['busy_dates']]
    language_peers = [item for item in free if query.language in item['languages']] if query.language else []
    day = query.date.strftime('%d.%m.%Y')
    scope = f'в категории «{query.category}», {query.city}'
    if query.language and len(language_peers) == 1:
        lead = f'Единственный из {len(free)} свободных на {day} профилей ({scope}), у кого указан язык «{query.language}»'
    elif len(eligible) == 1:
        lead = f'Единственный из {len(candidates)} профилей ({scope}), который проходит все ваши условия на {day}'
    else:
        cheapest = min(item['price_from_kzt'] for item in eligible)
        tied = sum(item['price_from_kzt'] == cheapest for item in eligible)
        if row['price_from_kzt'] == cheapest:
            lead = f'{"Самая низкая начальная цена" if tied == 1 else "Одна из самых низких начальных цен"} среди {len(eligible)} подходящих профилей ({scope}); свободен на {day}'
        else:
            lead = f'Свободен на {day} и работает с форматом «{query.event_format}»'
    if query.language and len(language_peers) != 1:
        lead += f'; язык «{query.language}» указан в профиле'
    if query.duration_hours is not None:
        lead += ('; длительность присутствия для этой услуги не применяется' if row['max_hours'] is None else
                 f'; до {row["max_hours"]:g} ч на площадке при запросе {query.duration_hours:g} ч')
    fmt = lambda value: f'{value:,}'.replace(',', ' ')
    price = row['price_from_kzt']
    budget = f'Цена от {fmt(price)} ₸ при бюджете {fmt(query.budget)} ₸'
    if price < query.budget:
        budget += f' — начальная цена ниже лимита на {fmt(query.budget - price)} ₸'
    else:
        budget += ' — начальная цена равна лимиту'
    if row.get('price_imputed'):
        budget += ' (цена проставлена при подготовке датасета)'
    evidence = f'; в описании: «{excerpt.rstrip().rstrip(".")}»' if excerpt else '; в описании недостаточно конкретных сведений для дополнительного обоснования'
    return lead + '. ' + budget + evidence + '.'
