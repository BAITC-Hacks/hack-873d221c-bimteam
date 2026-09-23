"""Жёсткие ограничения, три исхода и непересекающаяся воронка."""
from dataclasses import replace
from datetime import date

import pytest

from app.config import Settings
from app.data import load_contractors
from app.filters import filter_contractors, result_message
from app.models import RecommendRequest


@pytest.fixture
def catalog():
    return load_contractors(Settings(_env_file=None, llm_provider='none'))


def query_for(row, **changes):
    values = dict(city=row.city, category=row.categories[0], event_type=row.event_formats[0],
                  date=date(2026, 10, 10), budget_kzt=1_000_000_000)
    return RecommendRequest(**(values | changes))


def test_three_statuses_on_real_catalog(catalog):
    leader = next(row for row in catalog if row.city == 'Алматы' and 'Ведущий' in row.categories)
    found = query_for(leader, category='Ведущий')
    assert filter_contractors(found, catalog).status == 'found'
    assert filter_contractors(found.model_copy(update={'budget_kzt': 1}), catalog).status == 'all_filtered'
    missing = RecommendRequest(city='Астана', category='Декоратор', event_type='свадьба',
                               date='2026-10-10', budget_kzt=1_000_000_000)
    result = filter_contractors(missing, catalog)
    assert result.status == 'no_category'
    message, shortfall = result_message(result, missing, catalog)
    assert 'Алматы' in message
    assert shortfall


@pytest.mark.parametrize('identifier,category', [
    ('HK-64395', 'Ресторан'), ('HK-92824', 'Танцевальный коллектив'),
])
def test_real_multicategory_profiles_match_any_category(catalog, identifier, category):
    row = replace(next(row for row in catalog if row.id == identifier), busy_dates=frozenset())
    result = filter_contractors(query_for(row, category=category), [row])
    assert [item.id for item in result.eligible] == [identifier]


def test_exact_price_and_duration_boundaries(catalog):
    row = replace(catalog[0], price_from_kzt=100_000, max_hours=6, busy_dates=frozenset())
    req = query_for(row, budget_kzt=100_000, duration_hours=6)
    assert filter_contractors(req, [row]).status == 'found'
    assert filter_contractors(req, [replace(row, price_from_kzt=100_001)]).status == 'all_filtered'
    assert filter_contractors(req.model_copy(update={'duration_hours': 6.01}), [row]).status == 'all_filtered'


def test_optional_constraints_are_only_applied_when_given(catalog):
    row = replace(catalog[0], languages=('русский',), max_hours=1, busy_dates=frozenset())
    req = query_for(row)
    result = filter_contractors(req, [row])
    assert result.status == 'found'
    assert not {'language', 'duration'} & {step.step for step in result.funnel}
    assert filter_contractors(req.model_copy(update={'language': 'казахский'}), [row]).status == 'all_filtered'
    assert filter_contractors(req.model_copy(update={'duration_hours': 2}), [row]).status == 'all_filtered'


def test_real_florist_null_hours_do_not_restrict_duration(catalog):
    row = next(row for row in catalog if row.id == 'HK-39372')
    assert row.max_hours is None
    row = replace(row, busy_dates=frozenset())
    assert filter_contractors(query_for(row, duration_hours=100), [row]).status == 'found'


def test_busy_profile_never_passes(catalog):
    row = next(row for row in catalog if row.busy_dates)
    req = query_for(row, date=min(row.busy_dates))
    result = filter_contractors(req, [row])
    assert result.status == 'all_filtered'
    assert next(step for step in result.funnel if step.step == 'date').rejected_ids == [row.id]


def test_funnel_is_ordered_disjoint_and_conserves_counts(catalog):
    base = replace(catalog[0], city='Алматы', categories=('Ведущий',),
                   event_formats=('свадьба',), languages=('русский',),
                   price_from_kzt=100, max_hours=6, busy_dates=frozenset())
    req = query_for(base, budget_kzt=100, language='русский', duration_hours=6)
    rows = [replace(base, id='outside', city='Астана'),
            replace(base, id='format', event_formats=('корпоратив',), price_from_kzt=200),
            replace(base, id='busy', busy_dates=frozenset({req.date}), price_from_kzt=200),
            replace(base, id='budget', price_from_kzt=200, languages=('казахский',)),
            replace(base, id='language', languages=('казахский',), max_hours=1),
            replace(base, id='duration', max_hours=1), replace(base, id='ok')]
    result = filter_contractors(req, rows)
    assert [step.step for step in result.funnel] == [
        'category_city', 'event_format', 'date', 'budget', 'language', 'duration']
    rejected = []
    for index, step in enumerate(result.funnel):
        assert step.before - step.after == len(step.rejected_ids) == 1
        if index:
            assert step.before == result.funnel[index - 1].after
        rejected.extend(step.rejected_ids)
    assert len(rejected) == len(set(rejected))
    assert set(rejected) | {row.id for row in result.eligible} == {row.id for row in rows}
    assert [row.id for row in result.eligible] == ['ok']


def test_wishes_do_not_act_as_a_hard_filter(catalog):
    row = replace(catalog[0], busy_dates=frozenset())
    req = query_for(row)
    assert filter_contractors(req, [row]) == filter_contractors(
        req.model_copy(update={'wishes': 'несуществующее пожелание'}), [row])
