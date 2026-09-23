"""Подсказки меняют одно условие и действительно увеличивают число кандидатов."""
from dataclasses import replace
from datetime import date, timedelta
import re

import pytest

from app.config import DATE_MAX, DATE_MIN, Settings
from app.data import load_contractors
from app.filters import filter_contractors
from app.hints import make_hints
from app.models import RecommendRequest


@pytest.fixture
def base():
    row = load_contractors(Settings(_env_file=None, llm_provider='none'))[0]
    return replace(row, city='Алматы', categories=('Ведущий',), event_formats=('свадьба',),
                   languages=('русский',), price_from_kzt=100, max_hours=6, busy_dates=frozenset())


def request_model(**changes):
    return RecommendRequest(**(dict(city='Алматы', category='Ведущий', event_type='свадьба',
                                   date='2026-10-10', budget_kzt=100) | changes))


@pytest.mark.parametrize('day,expected', [(DATE_MIN, DATE_MIN + timedelta(days=1)),
                                         (DATE_MAX, DATE_MAX - timedelta(days=1))])
def test_date_hint_stays_in_calendar_and_really_improves(base, day, expected):
    req = request_model(date=day)
    rows = [replace(base, busy_dates=frozenset({day}))]
    hints = make_hints(req, rows, 0)
    date_hint = next(hint for hint in hints if 'дату' in hint and 'ближайшую' in hint)
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_hint)
    actual = date(int(match[3]), int(match[2]), int(match[1]))
    assert actual == expected
    assert 0 < abs((actual - req.date).days) <= 7
    assert len(filter_contractors(req.model_copy(update={'date': actual}), rows).eligible) == 1


def test_budget_hint_preserves_other_constraints_and_uses_minimum(base):
    req = request_model()
    rows = [replace(base, id='valid', price_from_kzt=200),
            replace(base, id='busy-cheaper', price_from_kzt=150, busy_dates=frozenset({req.date})),
            replace(base, id='wrong-format', price_from_kzt=120, event_formats=('корпоратив',))]
    hint = next(hint for hint in make_hints(req, rows, 0) if 'бюджетом' in hint)
    assert '200 ₸' in hint
    assert filter_contractors(req.model_copy(update={'budget_kzt': 199}), rows).status == 'all_filtered'
    assert [row.id for row in filter_contractors(req.model_copy(update={'budget_kzt': 200}), rows).eligible] == ['valid']


@pytest.mark.parametrize('field,value,label', [('language', 'казахский', 'языку'),
                                               ('duration_hours', 8, 'длительности')])
def test_optional_constraint_hint_is_verified(base, field, value, label):
    req = request_model(**{field: value})
    assert not filter_contractors(req, [base]).eligible
    hints = make_hints(req, [base], 0)
    assert any(f'по {label}' in hint and 'профилей: 1 вместо 0' in hint for hint in hints)
    assert len(filter_contractors(req.model_copy(update={field: None}), [base]).eligible) == 1


def test_no_unhelpful_hint_when_combined_restrictions_still_fail(base):
    req = request_model(language='казахский', duration_hours=8)
    assert make_hints(req, [base], 0) == []


def test_hints_are_deterministic_limited_and_absent_for_full_results(base):
    req = request_model()
    rows = [replace(base, id='B', price_from_kzt=200),
            replace(base, id='A', busy_dates=frozenset({req.date}))]
    hints = make_hints(req, rows, 0)
    assert hints == make_hints(req, list(reversed(rows)), 0)
    assert len(hints) <= 2
    assert make_hints(req, rows, 3) == []
