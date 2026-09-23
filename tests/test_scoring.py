"""Воспроизводимый порядок и утверждения, подтверждённые сравнениями."""
from dataclasses import replace

import pytest

from app.config import Settings
from app.data import load_contractors
from app.filters import filter_contractors
from app.models import RecommendRequest
from app.scoring import build_cards, profile_quote, rank_contractors, score


@pytest.fixture
def catalog():
    return load_contractors(Settings(_env_file=None, llm_provider='none'))


@pytest.fixture
def request_model():
    return RecommendRequest(city='Алматы', date='2026-10-10', category='Ведущий',
                            event_type='корпоратив', budget_kzt=1_000_000)


def facts(card, kind):
    return [fact.text for fact in card.facts if fact.type == kind]


def test_real_ranking_is_independent_of_input_order(catalog, request_model):
    rows = filter_contractors(request_model, catalog).eligible
    assert rows
    assert rank_contractors(rows, request_model) == rank_contractors(list(reversed(rows)), request_model)


def test_equal_scores_are_sorted_by_id(catalog, request_model):
    base = replace(catalog[0], event_formats=('корпоратив',), price_from_kzt=500_000)
    rows = [replace(base, id=identifier) for identifier in ('C', 'A', 'B')]
    assert len({score(row, request_model) for row in rows}) == 1
    assert [row.id for row in rank_contractors(rows, request_model)] == ['A', 'B', 'C']


def test_tied_prices_are_not_claimed_unique_cheapest(catalog, request_model):
    base = replace(catalog[0], price_from_kzt=100_000, languages=('казахский',))
    rows = [replace(base, id=identifier) for identifier in ('A', 'B', 'C')]
    cards = build_cards(rows, rows, rows, request_model)
    assert all(not facts(card, 'cheapest') for card in cards)
    assert all(not facts(card, 'unique_language') for card in cards)


def test_comparisons_consider_unselected_eligible_profiles(catalog, request_model):
    base = replace(catalog[0], languages=('казахский',), price_from_kzt=200_000)
    selected = [replace(base, id='A'), replace(base, id='B', languages=('русский',), price_from_kzt=300_000)]
    cheaper_unselected = replace(base, id='C', price_from_kzt=100_000)
    eligible = selected + [cheaper_unselected]
    first = build_cards(selected, eligible, eligible, request_model)[0]
    assert not facts(first, 'cheapest')
    assert not facts(first, 'unique_language')


def test_unique_facts_are_supported_when_true(catalog, request_model):
    first = replace(catalog[0], id='A', price_from_kzt=100_000, languages=('казахский',))
    second = replace(first, id='B', price_from_kzt=200_000, languages=('русский',))
    cards = build_cards([first, second], [first, second], [first, second], request_model)
    assert facts(cards[0], 'cheapest')
    assert facts(cards[0], 'unique_language')
    assert not facts(cards[1], 'cheapest')


def test_null_hours_are_not_treated_as_a_smaller_duration(catalog, request_model):
    a = replace(catalog[0], id='A', max_hours=10)
    b = replace(a, id='B', max_hours=None)
    req = request_model.model_copy(update={'duration_hours': 6})
    cards = build_cards([a, b], [a, b], [a, b], req)
    assert not facts(cards[0], 'hours_comparison')
    assert facts(cards[1], 'duration') == ['Длительность присутствия не применяется']


def test_busy_fact_counts_category_city_group_and_occurs_once(catalog, request_model):
    available = replace(catalog[0], id='A', busy_dates=frozenset())
    second = replace(available, id='B')
    busy_other_format = replace(available, id='C', event_formats=('другой',),
                                busy_dates=frozenset({request_model.date}))
    group = [available, second, busy_other_format]
    cards = build_cards([available, second], [available, second], group, request_model)
    assert len(facts(cards[0], 'busy')) == 1
    assert 'заняты 1 из 3' in facts(cards[0], 'busy')[0]
    assert not facts(cards[1], 'busy')


def test_quotes_are_short_literal_substrings_of_real_descriptions(catalog, request_model):
    for row in catalog:
        quote = profile_quote(row.description, request_model)
        assert quote in row.description
        assert len(quote.split()) <= 12
        assert len(quote) <= 100


def test_card_preserves_data_provenance(catalog, request_model):
    row = replace(catalog[0], city_imputed=True, price_imputed=True, synthetic=True)
    card = build_cards([row], [row], [row], request_model)[0]
    assert card.city_imputed and card.price_imputed and card.synthetic
    assert card.categories == list(row.categories)
