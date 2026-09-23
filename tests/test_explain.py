"""Объяснения проверяются без сети: факты, retry, fallback и файловый кэш."""
import asyncio
from copy import deepcopy
import json

import pytest

from app.config import Settings
from app.data import load_contractors
from app.explain import Explainer, numbers, template_explanations, validate_explanations
from app.filters import filter_contractors
from app.llm import LLMClient
from app.models import Card, Fact, RecommendRequest
from app.scoring import build_cards, rank_contractors


def query():
    return RecommendRequest(city='Алматы', date='2026-10-10', event_type='корпоратив',
                            category='Ведущий', budget_kzt=700_000)


def card(identifier='A', facts=None):
    return Card(rank=1, id=identifier, name='Тестовый профиль', category='Ведущий',
                categories=['Ведущий'], city='Алматы', price_from_kzt=500_000,
                price_imputed=False, city_imputed=False, synthetic=True,
                languages=['русский'], max_hours=8,
                facts=facts or [Fact(type='budget', text='Цена от 500 000 ₸ при бюджете 700 000 ₸'),
                                Fact(type='duration', text='До 8 ч при запросе 6 ч')])


def raw(text, identifier='A'):
    return json.dumps({'explanations': [{'id': identifier, 'text': text}]}, ensure_ascii=False)


VALID = 'Цена от 500 000 ₸ при бюджете 700 000 ₸. До 8 ч при запросе 6 ч.'


class FakeClient:
    available = True

    def __init__(self, responses=None, delay=0):
        self.responses = responses or [raw(VALID)]
        self.calls = []
        self.delay = delay

    async def complete(self, system, payload, correction=None):
        self.calls.append(correction)
        await asyncio.sleep(self.delay)
        value = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(value, Exception):
            raise value
        return value


def config(tmp_path, **changes):
    return Settings(_env_file=None, llm_provider='openai', openai_model='fake-model',
                    cache_dir=tmp_path, **changes)


def test_valid_facts_and_thousands_are_recognized():
    valid, errors = validate_explanations(raw(VALID), [card()])
    assert valid == {'A': VALID} and not errors
    assert numbers('700 000; 1\u00a0000\u00a0000; 500\u202f000; 6,5') == {'700000', '1000000', '500000', '6.5'}


@pytest.mark.parametrize('text', [
    VALID + ' Отличный выбор.',
    VALID.replace('500 000', '550 000'),
    VALID + ' Имеет высшее музыкальное образование.',
    'Работает с форматом «корпоратив». Указан язык: русский.',
    'Цена от 500 000 ₸ при бюджете 700 000 ₸.',
])
def test_invalid_or_invented_explanations_are_rejected(text):
    valid, errors = validate_explanations(raw(text), [card()])
    assert not valid and 'A' in errors


def test_banned_phrase_is_rejected_within_two_sentences():
    valid, errors = validate_explanations(raw('Отличный выбор: ' + VALID), [card()])
    assert not valid and 'Запрещённая' in errors['A']


def test_template_skips_banned_quote_and_remains_cacheable(tmp_path):
    item = card()
    item.facts.insert(0, Fact(type='quote', text='В описании: «Профессионал своего дела с опытом 8 лет»'))
    client = FakeClient(['bad json'])
    settings = config(tmp_path)
    first = [deepcopy(item)]
    asyncio.run(Explainer(settings, client).explain(query(), first))
    assert 'Профессионал своего дела' not in first[0].explanation
    _, errors = validate_explanations(raw(first[0].explanation), first)
    assert not errors
    restarted = FakeClient()
    second = [deepcopy(item)]
    asyncio.run(Explainer(settings, restarted).explain(query(), second))
    assert not restarted.calls and first == second


@pytest.mark.parametrize('rows', [[], [{'id': 'unknown', 'text': VALID}],
                                  [{'id': 'A', 'text': VALID}, {'id': 'A', 'text': VALID}]])
def test_missing_duplicate_and_unknown_ids_are_rejected(rows):
    valid, errors = validate_explanations(json.dumps({'explanations': rows}), [card()])
    assert not valid and errors


def test_duplicate_ids_with_matching_count_are_rejected():
    rows = [{'id': 'A', 'text': VALID}, {'id': 'A', 'text': VALID}]
    valid, errors = validate_explanations(json.dumps({'explanations': rows}), [card('A'), card('B')])
    assert not valid and set(errors) == {'A', 'B'}


def test_similar_texts_are_rejected_even_when_the_facts_are_true():
    rows = [{'id': identifier, 'text': VALID} for identifier in ('A', 'B')]
    valid, errors = validate_explanations(json.dumps({'explanations': rows}), [card('A'), card('B')])
    assert not valid and all('похожие' in message for message in errors.values())


def test_template_explanations_on_real_catalog():
    rows = load_contractors(Settings(_env_file=None, llm_provider='none'))
    exercised = 0
    for row in rows:
        req = query().model_copy(update={'city': row.city, 'category': row.categories[0],
                                        'event_type': row.event_formats[0], 'budget_kzt': 1_000_000_000})
        result = filter_contractors(req, rows)
        selected = rank_contractors(result.eligible, req)[:3]
        if not selected:
            continue
        cards = build_cards(selected, result.eligible, result.category_city, req)
        texts = template_explanations(cards)
        payload = json.dumps({'explanations': [{'id': key, 'text': text} for key, text in texts.items()]})
        valid, errors = validate_explanations(payload, cards)
        assert not errors, (req.model_dump(), errors, texts)
        assert len(valid) == len(cards)
        exercised += 1
    assert exercised > 20


def test_one_retry_then_valid_output_and_disk_cache_after_restart(tmp_path):
    settings = config(tmp_path)
    client = FakeClient(['invalid json', raw(VALID)])
    first = [card()]
    asyncio.run(Explainer(settings, client).explain(query(), first))
    assert len(client.calls) == 2
    assert client.calls[0] is None and client.calls[1]
    assert first[0].explanation_source == 'llm'
    restarted_client = FakeClient([AssertionError('Кэш должен исключить вызов')])
    again = [card()]
    asyncio.run(Explainer(settings, restarted_client).explain(query(), again))
    assert not restarted_client.calls
    assert again == first


def test_second_invalid_response_falls_back_and_is_cached(tmp_path):
    settings = config(tmp_path)
    client = FakeClient(['not json'])
    first = [card()]
    asyncio.run(Explainer(settings, client).explain(query(), first))
    assert len(client.calls) == 2
    assert first[0].explanation_source == 'template'
    restarted = FakeClient()
    again = [card()]
    asyncio.run(Explainer(settings, restarted).explain(query(), again))
    assert not restarted.calls and again == first


def test_timeout_falls_back_and_caches_result(tmp_path):
    settings = config(tmp_path, llm_timeout_s=0.01)
    client = FakeClient(delay=0.1)
    cards = [card()]
    asyncio.run(Explainer(settings, client).explain(query(), cards))
    assert len(client.calls) == 1
    assert cards[0].explanation_source == 'template' and cards[0].explanation
    restarted = FakeClient()
    asyncio.run(Explainer(settings, restarted).explain(query(), [card()]))
    assert not restarted.calls


def test_no_keys_means_no_sdk_and_no_api(tmp_path, monkeypatch):
    def forbidden_sdk(**kwargs):
        raise AssertionError('SDK не должен создаваться без ключей')
    monkeypatch.setattr('app.llm.AsyncOpenAI', forbidden_sdk)
    settings = config(tmp_path)
    client = LLMClient(settings)
    assert not client.available
    cards = [card()]
    asyncio.run(Explainer(settings, client).explain(query(), cards))
    assert cards[0].explanation_source == 'template'


def test_concurrent_identical_requests_make_one_call(tmp_path):
    client = FakeClient(delay=0.01)
    explainer = Explainer(config(tmp_path), client)
    first, second = [card()], [card()]
    before = deepcopy(first)
    async def both():
        await asyncio.gather(explainer.explain(query(), first), explainer.explain(query(), second))
    asyncio.run(both())
    assert len(client.calls) == 1 and first == second
    assert first[0].id == before[0].id and first[0].facts == before[0].facts
