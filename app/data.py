"""CSV без pandas; ошибки данных обнаруживаются при запуске сервера."""
import csv
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path

from app.config import DATE_MIN, DATE_MAX, Settings


@dataclass(frozen=True)
class Contractor:
    """Неизменяемая нормализованная запись выданного каталога."""
    id: str
    name: str
    categories: tuple[str, ...]
    city: str
    city_imputed: bool
    synthetic: bool
    price_from_kzt: int
    price_imputed: bool
    event_formats: tuple[str, ...]
    languages: tuple[str, ...]
    max_hours: float | None
    busy_dates: frozenset[date]
    description: str


def _flag(value: str) -> bool:
    if value.strip().lower() not in ('true', 'false'):
        raise ValueError('Флаг должен быть True или False')
    return value.strip().lower() == 'true'


def _items(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in value.split('|') if item.strip()))


def _read(path: Path, extra: bool) -> list[Contractor]:
    result = []
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        for line, row in enumerate(reader, 2):
            try:
                item = Contractor(
                    id=row['id'].strip(), name=row['anon_name'].strip(),
                    categories=_items(row['categories']), city=row['city'].strip(),
                    city_imputed=_flag(row['city_imputed']), synthetic=_flag(row['synthetic']),
                    price_from_kzt=int(row['price_from_kzt']), price_imputed=_flag(row['price_imputed']),
                    event_formats=_items(row['event_formats']), languages=_items(row['languages']),
                    max_hours=float(row['max_hours']) if row['max_hours'].strip() else None,
                    busy_dates=frozenset(date.fromisoformat(s) for s in _items(row['busy_dates'])),
                    description=row['description'].strip())
                if not all((item.id, item.name, item.city, item.categories, item.event_formats)):
                    raise ValueError('Пустые обязательные поля')
                if item.price_from_kzt <= 0:
                    raise ValueError('Цена должна быть положительной')
                if item.max_hours is not None and (not math.isfinite(item.max_hours) or item.max_hours <= 0):
                    raise ValueError('Неверная длительность')
                if any(not DATE_MIN <= day <= DATE_MAX for day in item.busy_dates):
                    raise ValueError('Дата занятости вне календаря')
                if extra and not item.synthetic:
                    raise ValueError('Дополнительный профиль должен быть synthetic=True')
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                raise ValueError(f'Ошибка каталога {path.name}, строка {line}: {exc}') from exc
            result.append(item)
    return result


def load_contractors(settings: Settings | None = None) -> list[Contractor]:
    """Загрузить основной и необязательный дополнительный CSV; проверить уникальность ID."""
    settings = settings or Settings()
    rows = _read(settings.data_path, extra=False)
    if settings.extra_data_path.exists():
        rows.extend(_read(settings.extra_data_path, extra=True))
    if len({row.id for row in rows}) != len(rows):
        raise ValueError('Повторяющиеся id подрядчиков')
    if not rows:
        raise ValueError('Каталог пуст')
    return sorted(rows, key=lambda row: row.id)


def catalog_options(rows: list[Contractor]) -> dict:
    """Значения из данных; старое имя event_formats сохранено для формы."""
    formats = sorted({v for row in rows for v in row.event_formats})
    return dict(cities=sorted({row.city for row in rows}),
                categories=sorted({v for row in rows for v in row.categories}),
                event_types=formats, event_formats=formats,
                languages=sorted({v for row in rows for v in row.languages}),
                date_min=DATE_MIN.isoformat(), date_max=DATE_MAX.isoformat())
