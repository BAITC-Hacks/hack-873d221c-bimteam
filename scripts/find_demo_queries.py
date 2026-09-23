"""Найти пять настоящих сценариев и получить примеры ответов через пайплайн."""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DATE_MIN, DATE_MAX, Settings
from app.data import Contractor, catalog_options, load_contractors
from app.filters import filter_contractors
from app.models import RecommendRequest
from app.pipeline import RecommendationService
from app.scoring import rank_contractors


def find_cases(rows: list[Contractor]) -> list[dict]:
    """Перебор отсортированных реальных значений, без случайности и модели."""
    days = [DATE_MIN + timedelta(days=i) for i in range((DATE_MAX - DATE_MIN).days + 1)]
    autumn = [day for day in days if day.weekday() == 5 and day.month in (10, 11)]
    dense = second = None
    for category in ('Ведущий', 'Фотограф'):
        group = [c for c in rows if c.city == 'Алматы' and category in c.categories]
        for event in sorted({v for c in group for v in c.event_formats}):
            for budget in sorted({c.price_from_kzt for c in group}):
                for day in autumn:
                    req = RecommendRequest(city='Алматы', category=category, event_type=event,
                                           date=day, budget_kzt=budget)
                    passed = filter_contractors(req, rows)
                    if len(passed.eligible) < 4:
                        continue
                    ids = {c.id for c in rank_contractors(passed.eligible, req)[:3]}
                    for other_day in autumn:
                        if other_day == day:
                            continue
                        other = req.model_copy(update={'date': other_day})
                        other_passed = filter_contractors(other, rows)
                        other_ids = {c.id for c in rank_contractors(other_passed.eligible, other)[:3]}
                        if len(other_ids) == 3 and other_ids != ids:
                            dense, second = req, other
                            break
                    if dense:
                        break
                if dense:
                    break
            if dense:
                break
        if dense:
            break
    if dense is None or second is None:
        raise ValueError('Не найден плотный сценарий со сменой состава на другую дату')
    options = catalog_options(rows)
    rare = absent = empty = None
    for category in ('Флорист', 'Декоратор', 'Подарки и сувениры', 'Ведущий церемонии',
                     'Фото и видеобудки', 'Отель', 'Инструменталист'):
        for city in ('Астана', 'Алматы'):
            for event in options['event_types']:
                req = dense.model_copy(update={'city': city, 'category': category, 'event_type': event,
                                               'budget_kzt': max((c.price_from_kzt for c in rows if c.city == city and category in c.categories), default=1)})
                if 1 <= len(filter_contractors(req, rows).eligible) <= 2:
                    rare = req
                    break
            if rare:
                break
        if rare:
            break
    for category in ['Декоратор', 'Лайв-бэнд'] + options['categories']:
        if category not in options['categories']:
            continue
        req = dense.model_copy(update={'city': 'Астана', 'category': category})
        if filter_contractors(req, rows).status == 'no_category':
            absent = req
            break
    minimum = min(c.price_from_kzt for c in rows if c.city == dense.city and dense.category in c.categories)
    for day in days:
        if day.month == 12 and day.weekday() == 5:
            req = dense.model_copy(update={'date': day, 'budget_kzt': max(1, minimum // 2)})
            filtered = filter_contractors(req, rows)
            if filtered.status == 'all_filtered' and filtered.funnel[3].rejected_ids:
                empty = req
                break
    if any(case is None for case in (rare, absent, empty)):
        raise ValueError('Не удалось найти все сценарии на текущих данных')
    return [{'title': title, 'expect_status': status, 'request': req.model_dump(mode='json', exclude_none=True)}
            for title, status, req in [
                ('Плотная категория осенью', 'found', dense),
                ('Те же условия на другую дату', 'found', second),
                ('Редкая категория', 'found', rare),
                ('Нет категории в городе', 'no_category', absent),
                ('Все отфильтрованы', 'all_filtered', empty)]]


async def generate() -> None:
    """Сохранить запросы curl и реальные ответы; elapsed_ms исключён из снимков."""
    settings = Settings(_env_file=None, llm_provider='none', embedding_provider='none')
    service = RecommendationService(settings, load_contractors(settings))
    cases = find_cases(service.rows)
    request_dir = ROOT / 'data/demo_requests'
    request_dir.mkdir(parents=True, exist_ok=True)
    try:
        for index, case in enumerate(cases, 1):
            result = await service.recommend(RecommendRequest(**case['request']))
            assert result.status == case['expect_status']
            case['expected_ids'] = [c.id for c in result.cards]
            case['eligible_count'] = result.funnel[-1].after
            case['response'] = result.model_dump(mode='json', exclude={'elapsed_ms'})
            (request_dir / f'{index}.json').write_text(json.dumps(case['request'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'{index}. {case["title"]}: {result.status}, подходят {case["eligible_count"]}, id={case["expected_ids"]}')
        settings.demo_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    finally:
        await service.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(generate())
