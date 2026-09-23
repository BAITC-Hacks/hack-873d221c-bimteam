"""Объяснения из проверенных полей и точных фрагментов профиля."""
import re

# Прозрачные подсказки для выбора фрагмента, не для оценки качества человека.
TERMS = {
    'корпоратив': ('корпоратив', 'бизнес', 'делов', 'команд', 'форум'),
    'конференция': ('конференц', 'форум', 'делов', 'бизнес'),
    'свадьба': ('свад', 'церемон', 'романт'),
    'той': ('той', 'традиц', 'казах'),
    'юбилей': ('юбиле', 'семейн', 'поколен'),
    'день рождения': ('рождени', 'праздник', 'семейн'),
}


def excerpts(description, query):
    chunks = []
    for match in re.finditer(r'[^.!?\n•]+[.!?]?', description):
        text = match.group().strip()
        if len(text) > 260:
            text = text[:260].rsplit(' ', 1)[0]
        if text and text not in chunks:
            chunks.append(text)
    terms = TERMS.get(query.event_format, ())
    # Исходный индекс разрешает ничьи; результат не зависит от случайности.
    ranked = sorted(enumerate(chunks), key=lambda pair: (
        -sum(term in pair[1].lower() for term in terms), pair[0]))
    return [text for _, text in ranked[:6]]


def explanation(row, query, quote):
    money = lambda value: f'{value:,}'.replace(',', ' ')
    price = row['price_from_kzt']
    remaining = query.budget - price
    facts = [f"Свободен {query.date.strftime('%d.%m.%Y')} и работает с форматом «{query.event_format}»",
             f"цена от {money(price)} ₸"]
    facts.append(f"разница с бюджетом — {money(remaining)} ₸" if remaining else 'начальная цена равна бюджету')
    if query.language:
        facts.append(f'язык — {query.language}')
    if query.duration_hours is not None:
        facts.append('длительность присутствия не применяется' if row['max_hours'] is None else
                     f"доступно до {row['max_hours']:g} ч при запросе {query.duration_hours:g} ч")
    text = '; '.join(facts) + '.'
    if quote:
        text += f' В описании профиля: «{quote}».'
    return text
