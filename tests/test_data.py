"""Проверки исходного каталога и явных ошибок входных CSV."""
import csv
from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from app.config import DATE_MAX, DATE_MIN, Settings
from app.data import catalog_options, load_contractors


def settings(**kwargs):
    return Settings(_env_file=None, llm_provider='none', **kwargs)


def source_row():
    with settings().data_path.open(encoding='utf-8-sig', newline='') as source:
        return next(csv.DictReader(source))


def write_csv(path, row):
    with path.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def test_real_catalog_counts_types_and_immutability():
    rows = load_contractors(settings())
    assert len(rows) == len({row.id for row in rows}) == 66
    assert sum(row.synthetic for row in rows) == 13
    assert sum(row.price_imputed for row in rows) == 18
    assert sum(row.city_imputed for row in rows) == 8
    assert any(row.max_hours is None for row in rows)
    assert any(row.busy_dates for row in rows)
    assert all(isinstance(day, date) and DATE_MIN <= day <= DATE_MAX
               for row in rows for day in row.busy_dates)
    with pytest.raises(FrozenInstanceError):
        rows[0].city = 'Изменённый город'


def test_extra_duplicate_id_is_rejected(tmp_path):
    extra = tmp_path / 'extra.csv'
    write_csv(extra, source_row() | {'synthetic': 'True'})
    with pytest.raises(ValueError, match='Повторяющиеся id'):
        load_contractors(settings(extra_data_path=extra))


def test_extra_must_be_synthetic(tmp_path):
    extra = tmp_path / 'extra.csv'
    write_csv(extra, source_row() | {'id': 'EXTRA-TEST', 'synthetic': 'False'})
    with pytest.raises(ValueError, match='synthetic=True'):
        load_contractors(settings(extra_data_path=extra))


def test_extra_synthetic_is_loaded(tmp_path):
    extra = tmp_path / 'extra.csv'
    write_csv(extra, source_row() | {'id': 'EXTRA-TEST', 'synthetic': 'True'})
    rows = load_contractors(settings(extra_data_path=extra))
    assert len(rows) == 67
    assert next(row for row in rows if row.id == 'EXTRA-TEST').synthetic


@pytest.mark.parametrize('field', ['synthetic', 'city_imputed', 'price_imputed'])
def test_invalid_flag_is_not_silently_false(tmp_path, field):
    path = tmp_path / 'invalid.csv'
    write_csv(path, source_row() | {field: 'maybe'})
    with pytest.raises(ValueError, match='Флаг'):
        load_contractors(settings(data_path=path, extra_data_path=tmp_path / 'absent.csv'))


@pytest.mark.parametrize('changes', [
    {'max_hours': 'NaN'}, {'max_hours': 'inf'}, {'max_hours': '-1'},
    {'price_from_kzt': '0'}, {'busy_dates': '2027-01-01'}, {'busy_dates': 'not-a-date'},
])
def test_invalid_numeric_or_calendar_data_fails_early(tmp_path, changes):
    path = tmp_path / 'invalid.csv'
    write_csv(path, source_row() | changes)
    with pytest.raises(ValueError, match='Ошибка каталога'):
        load_contractors(settings(data_path=path, extra_data_path=tmp_path / 'absent.csv'))


def test_list_normalization_and_blank_hours(tmp_path):
    path = tmp_path / 'normalized.csv'
    write_csv(path, source_row() | {
        'categories': ' Ведущий | Ресторан |Ведущий||', 'max_hours': ' ',
        'busy_dates': '2026-10-10|2026-10-10', 'synthetic': ' true ',
    })
    row = load_contractors(settings(data_path=path, extra_data_path=tmp_path / 'absent.csv'))[0]
    assert row.categories == ('Ведущий', 'Ресторан')
    assert row.max_hours is None
    assert row.busy_dates == frozenset({date(2026, 10, 10)})
    assert row.synthetic is True


def test_options_preserve_frontend_names_and_order():
    rows = load_contractors(settings())
    options = catalog_options(rows)
    assert options == catalog_options(list(reversed(rows)))
    assert options['event_formats'] == options['event_types']
    assert options['date_min'] == DATE_MIN.isoformat()
    assert options['date_max'] == DATE_MAX.isoformat()
    assert 'Ресторан' in options['categories']
