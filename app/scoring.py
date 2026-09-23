"""Прозрачный скоринг и сравнения: эвристика порядка не выдаётся за качество."""
import re

from app.data import Contractor
from app.filters import money
from app.models import Card, Fact, RecommendRequest

WEIGHTS = dict(budget_fit=0.30, format_focus=0.25, language_bonus=0.10,
               duration_margin=0.10, semantic=0.25, synthetic_penalty=-0.03,
               imputed_penalty=-0.02)


def score(c: Contractor, req: RecommendRequest, similarity: float = 0) -> float:
    """Числа эвристические; языки/часы уже проверены жёсткими фильтрами."""
    values = dict(
        budget_fit=max(0.4, c.price_from_kzt / max(req.budget_kzt, 1)),
        format_focus=0.5 * (c.event_formats[0] == req.event_type) + 0.5 / len(c.event_formats),
        language_bonus=(0.8 if req.language and req.language in c.languages else 0) +
                       (0.2 if len(c.languages) > 1 else 0),
        duration_margin=(min(1, (c.max_hours - req.duration_hours) / req.duration_hours)
                         if req.duration_hours and c.max_hours is not None else 0),
        semantic=max(0, min(1, similarity)), synthetic_penalty=float(c.synthetic),
        imputed_penalty=float(c.price_imputed))
    return sum(WEIGHTS[key] * value for key, value in values.items())


def rank_contractors(rows: list[Contractor], req: RecommendRequest,
                     similarities: dict[str, float] | None = None) -> list[Contractor]:
    """Одинаковые баллы разрешаются ID, а не исходным порядком строк CSV."""
    similarities = similarities or {}
    return sorted(rows, key=lambda c: (-round(score(c, req, similarities.get(c.id, 0)), 6), c.id))


def profile_quote(description: str, req: RecommendRequest) -> str:
    """Непрерывный фрагмент ≤12 слов/100 символов, приоритет словам запроса и числам."""
    terms = [w[:5] for w in re.findall(r'[а-яёa-z]{4,}', (req.event_type + ' ' + (req.wishes or '')).lower())]
    chunks = []
    for part in re.split(r'[.!?\n;•]+', description):
        tokens = list(re.finditer(r'\S+', part))
        if not tokens:
            continue
        # Короткое непрерывное окно, а не склеенные слова из разных мест.
        for start in range(0, len(tokens), 8):
            end = min(start + 12, len(tokens))
            text = part[tokens[start].start():tokens[end - 1].end()].strip()
            while len(text) > 100 and end > start + 1:
                end -= 1
                text = part[tokens[start].start():tokens[end - 1].end()].strip()
            if text and len(text) <= 100:
                chunks.append(text)
    return min(enumerate(chunks), key=lambda p: (
        -sum(term in p[1].lower() for term in terms), -bool(re.search(r'\d', p[1])), p[0]))[1] if chunks else ''


def build_cards(selected: list[Contractor], eligible: list[Contractor], group: list[Contractor],
                req: RecommendRequest) -> list[Card]:
    """Сравнить со ВСЕМИ прошедшими, а часы — с другими выбранными карточками."""
    cards = []
    busy = sum(req.date in c.busy_dates for c in group)
    for index, c in enumerate(selected):
        peers = [other for other in eligible if other.id != c.id]
        chosen_peers = [other for other in selected if other.id != c.id]
        facts: list[Fact] = []
        if peers and c.price_from_kzt < min(p.price_from_kzt for p in peers):
            low, high = min(p.price_from_kzt for p in peers), max(p.price_from_kzt for p in peers)
            prices = money(low) if low == high else f'{money(low)}–{money(high)}'
            facts.append(Fact(type='cheapest', text=f'Самая низкая цена от среди подходящих: {money(c.price_from_kzt)}; у остальных {prices}'))
        if peers and 'казахский' in c.languages and all('казахский' not in p.languages for p in peers):
            facts.append(Fact(type='unique_language', text='Единственный среди подходящих, у кого указан казахский язык'))
        if (chosen_peers and c.max_hours is not None and all(p.max_hours is not None for p in chosen_peers)
                and c.max_hours > max(p.max_hours for p in chosen_peers)):
            facts.append(Fact(type='hours_comparison', text=f'Доступно до {c.max_hours:g} ч; у других карточек — до {max(p.max_hours for p in chosen_peers):g} ч'))
        if index == 0 and busy:
            facts.append(Fact(type='busy', text=f'Свободен {req.date:%d.%m}; в группе «{req.category} · {req.city}» заняты {busy} из {len(group)}'))
        if len(c.event_formats) <= 2:
            facts.append(Fact(type='focus', text='В каталоге указаны только форматы: ' + ', '.join(c.event_formats)))
        quote = profile_quote(c.description, req)
        if quote:
            facts.append(Fact(type='quote', text=f'В описании: «{quote}»'))
        facts.extend([
            Fact(type='budget', text=f'Цена от {money(c.price_from_kzt)} при бюджете {money(req.budget_kzt)}'),
            Fact(type='date', text=f'Свободен {req.date:%d.%m.%Y}'),
            Fact(type='format', text=f'Работает с форматом «{req.event_type}»'),
        ])
        if req.language:
            facts.append(Fact(type='language', text=f'Указан язык: {req.language}'))
        if req.duration_hours is not None:
            facts.append(Fact(type='duration', text=('Длительность присутствия не применяется'
                if c.max_hours is None else f'До {c.max_hours:g} ч при запросе {req.duration_hours:g} ч')))
        cards.append(Card(rank=index+1, id=c.id, name=c.name, category=req.category,
                          categories=list(c.categories), city=c.city, price_from_kzt=c.price_from_kzt,
                          price_imputed=c.price_imputed, city_imputed=c.city_imputed, synthetic=c.synthetic,
                          languages=list(c.languages), max_hours=c.max_hours, facts=facts, profile_excerpt=quote))
    return cards
