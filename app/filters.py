"""Жёсткие ограничения и честные последовательные причины отсева."""
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Literal

from app.data import Contractor
from app.models import Funnel, RecommendRequest


def money(value: int) -> str:
    """Тенге с обычным пробелом-разделителем, удобно для UI и проверки чисел."""
    return f'{value:,}'.replace(',', ' ') + ' ₸'


@dataclass(frozen=True)
class FilterResult:
    """Группа после фильтров и вся трасса принятия решения."""
    eligible: list[Contractor]
    category_city: list[Contractor]
    funnel: list[Funnel]

    @property
    def status(self) -> Literal['found', 'no_category', 'all_filtered']:
        """Отсутствие категории отличается от несовпадения условий."""
        return 'found' if self.eligible else 'all_filtered' if self.category_city else 'no_category'


def filter_contractors(req: RecommendRequest, rows: list[Contractor]) -> FilterResult:
    """Каждый профиль выбывает ровно на первом не пройденном шаге."""
    steps: list[tuple[str, str, Callable[[Contractor], bool]]] = [
        ('category_city', f'{req.category} · {req.city}',
         lambda c: c.city == req.city and req.category in c.categories),
        ('event_format', f'Формат: {req.event_type}', lambda c: req.event_type in c.event_formats),
        ('date', f'Свободны {req.date:%d.%m.%Y}', lambda c: req.date not in c.busy_dates),
        ('budget', f'Цена от ≤ {money(req.budget_kzt)}', lambda c: c.price_from_kzt <= req.budget_kzt),
    ]
    if req.language is not None:
        steps.append(('language', f'Язык: {req.language}', lambda c: req.language in c.languages))
    if req.duration_hours is not None:
        steps.append(('duration', f'Длительность: {req.duration_hours:g} ч',
                      lambda c: c.max_hours is None or c.max_hours >= req.duration_hours))
    remaining = sorted(rows, key=lambda c: c.id)
    group: list[Contractor] = []
    funnel = []
    for step, label, passes in steps:
        kept = [c for c in remaining if passes(c)]
        ids = {c.id for c in kept}
        funnel.append(Funnel(step=step, label=label, before=len(remaining), after=len(kept),
                             rejected_ids=[c.id for c in remaining if c.id not in ids]))
        remaining = kept
        if step == 'category_city':
            group = kept
    return FilterResult(remaining, group, funnel)


def rejection_text(result: FilterResult, req: RecommendRequest) -> str:
    """Назвать причины в порядке количества исключённых, без двойного счёта."""
    labels = dict(event_format=f'не берут формат «{req.event_type}»',
                  date=f'заняты {req.date:%d.%m.%Y}', budget=f'дороже {money(req.budget_kzt)}',
                  language=f'не указан язык «{req.language}»', duration='не хватает часов')
    losses = [(i, step) for i, step in enumerate(result.funnel[1:]) if step.rejected_ids]
    losses.sort(key=lambda pair: (-len(pair[1].rejected_ids), pair[0]))
    return '; '.join(f'{len(step.rejected_ids)} — {labels[step.step]}' for _, step in losses)


def result_message(result: FilterResult, req: RecommendRequest, rows: list[Contractor]) -> tuple[str, str | None]:
    """Сформировать итог и причину короткой выдачи только по данным воронки."""
    n, count = len(result.category_city), len(result.eligible)
    if result.status == 'no_category':
        cities = Counter(c.city for c in rows if req.category in c.categories)
        locations = ', '.join(f'{city}: {cities[city]}' for city in sorted(cities))
        message = f'Категории «{req.category}» в городе {req.city} нет.'
        if locations:
            message += f' Профили этой категории есть в других городах: {locations}.'
        return message, message
    rejected = rejection_text(result, req)
    if not count:
        message = f'Из {n} профилей «{req.category}» в городе {req.city} не подошёл ни один: {rejected}.'
        return message, message
    shortfall = None
    if count < 3:
        shortfall = (f'В каталоге для «{req.category}» и города {req.city} всего {n} профилей.'
                     if not rejected else f'Из {n} профилей прошли {count}: {rejected}.')
    message = f'Подходят {count} профилей; показаны {min(3, count)}.'
    return message + (' ' + shortfall if shortfall else ''), shortfall
