"""Только проверенные изменения одного условия, без обещаний от LLM."""
from datetime import timedelta

from app.config import DATE_MIN, DATE_MAX
from app.data import Contractor
from app.filters import filter_contractors, money
from app.models import RecommendRequest


def make_hints(req: RecommendRequest, rows: list[Contractor], current_count: int) -> list[str]:
    """До двух подсказок; каждую проверяем тем же фильтром, что основной запрос."""
    if current_count >= 3:
        return []
    hints = []
    for offset in range(1, 8):
        for sign in (1, -1):
            day = req.date + timedelta(days=sign * offset)
            if DATE_MIN <= day <= DATE_MAX:
                count = len(filter_contractors(req.model_copy(update={'date': day}), rows).eligible)
                if count > current_count:
                    hints.append(f'На ближайшую подходящую дату {day:%d.%m.%Y} подходят {count} профилей при тех же условиях.')
                    break
        if hints:
            break
    # Убираем только бюджет, оставляя дату, формат, язык и длительность.
    relaxed = filter_contractors(req.model_copy(update={'budget_kzt': 1_000_000_000}), rows).eligible
    prices = sorted({c.price_from_kzt for c in relaxed if c.price_from_kzt > req.budget_kzt})
    if prices:
        minimum = prices[0]
        count = sum(c.price_from_kzt <= minimum for c in relaxed)
        if count > current_count:
            hints.append(f'С бюджетом от {money(minimum)} на эту дату подходят {count} профилей; остальные условия сохранены.')
    for field, label in (('language', 'языку'), ('duration_hours', 'длительности')):
        if getattr(req, field) is not None:
            count = len(filter_contractors(req.model_copy(update={field: None}), rows).eligible)
            if count > current_count:
                hints.append(f'Без ограничения по {label} подходят {count} профилей вместо {current_count}.')
    return hints[:2]
