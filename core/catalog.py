"""Загрузка выданного организаторами каталога."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_catalog():
    with (ROOT / 'data/contractors.csv').open(encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        for field in ('categories', 'event_formats', 'languages', 'busy_dates'):
            row[field] = row[field].split('|') if row[field] else []
        row['price_from_kzt'] = int(row['price_from_kzt'])
        row['max_hours'] = float(row['max_hours']) if row['max_hours'] else None
        for field in ('synthetic', 'city_imputed', 'price_imputed'):
            row[field] = row[field].lower() == 'true'
    return rows
