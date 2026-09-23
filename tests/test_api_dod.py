"""Definition of Done через настоящий HTTP-контракт, без сети и ключей."""
from datetime import date
import json
import re
from time import perf_counter

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.explain import validate_explanations
from app.main import create_app
from app.models import Card


@pytest.fixture
def client(tmp_path, monkeypatch):
    def forbidden_sdk(**kwargs):
        raise AssertionError('Оффлайн-тест не должен создавать внешний SDK')
    monkeypatch.setattr('app.llm.AsyncOpenAI', forbidden_sdk)
    settings = Settings(_env_file=None, llm_provider='none', embedding_provider='none', cache_dir=tmp_path)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def demos(client):
    response = client.get('/api/demo')
    assert response.status_code == 200
    return response.json()


def without_elapsed(value):
    return {key: item for key, item in value.items() if key != 'elapsed_ms'}


def legacy(payload):
    converted = dict(payload)
    converted['event_format'] = converted.pop('event_type')
    converted['budget'] = converted.pop('budget_kzt')
    return converted


def test_all_five_demo_responses_match_saved_snapshots_and_latency(client):
    cases = demos(client)
    assert len(cases) == 5
    statuses = set()
    for case in cases:
        start = perf_counter()
        response = client.post('/api/recommend', json=case['request'])
        body = response.json()
        assert perf_counter() - start < 10
        assert response.status_code == 200
        assert 0 <= body['elapsed_ms'] < 10_000
        assert body['status'] == case['expect_status']
        assert without_elapsed(body) == without_elapsed(case['response'])
        assert [card['id'] for card in body['cards']] == case['expected_ids']
        assert body['message'] and len(body['cards']) <= 3
        assert isinstance(body['hints'], list) and len(body['hints']) <= 2
        statuses.add(body['status'])
    assert statuses == {'found', 'no_category', 'all_filtered'}


def test_same_request_is_deterministic_except_elapsed(client):
    for case in demos(client):
        first = client.post('/api/recommend', json=case['request']).json()
        second = client.post('/api/recommend', json=case['request']).json()
        assert without_elapsed(first) == without_elapsed(second)


def test_two_dates_change_cards_and_have_truthful_busy_fact(client):
    cases = demos(client)
    first, second = cases[0]['request'], cases[1]['request']
    assert first['date'] != second['date']
    assert {k: v for k, v in first.items() if k != 'date'} == {k: v for k, v in second.items() if k != 'date'}
    responses = [client.post('/api/recommend', json=payload).json() for payload in (first, second)]
    assert {card['id'] for card in responses[0]['cards']} != {card['id'] for card in responses[1]['cards']}
    rows = client.app.state.service.rows
    for payload, body in zip((first, second), responses):
        group = [row for row in rows if row.city == payload['city'] and payload['category'] in row.categories]
        busy_count = sum(date.fromisoformat(payload['date']) in row.busy_dates for row in group)
        facts = [fact for card in body['cards'] for fact in card['facts'] if fact['type'] == 'busy']
        assert len(facts) == 1
        assert f'заняты {busy_count} из {len(group)}' in facts[0]['text']


def test_funnels_and_cards_obey_all_constraints_and_explanations(client):
    by_id = {row.id: row for row in client.app.state.service.rows}
    for case in demos(client):
        payload = case['request']
        body = client.post('/api/recommend', json=payload).json()
        rejected = []
        for index, step in enumerate(body['funnel']):
            assert step['before'] - step['after'] == len(step['rejected_ids'])
            if index:
                assert step['before'] == body['funnel'][index - 1]['after']
            rejected.extend(step['rejected_ids'])
        assert len(rejected) == len(set(rejected))
        assert len(rejected) + body['funnel'][-1]['after'] == len(by_id)
        for card in body['cards']:
            row = by_id[card['id']]
            assert row.id not in rejected
            assert row.city == payload['city'] and payload['category'] in row.categories
            assert payload['event_type'] in row.event_formats
            assert date.fromisoformat(payload['date']) not in row.busy_dates
            assert row.price_from_kzt <= payload['budget_kzt']
            assert card['profile_excerpt'] in row.description
            assert len(card['profile_excerpt'].split()) <= 12
            assert card['explanation_source'] == 'template'
            for flag in ('synthetic', 'city_imputed', 'price_imputed'):
                assert card[flag] == getattr(row, flag)
        cards = [Card.model_validate(item) for item in body['cards']]
        raw = json.dumps({'explanations': [{'id': c.id, 'text': c.explanation} for c in cards]})
        _, errors = validate_explanations(raw, cards)
        assert not errors
        if len(cards) < 3:
            assert body['shortfall_reason']
        else:
            assert body['shortfall_reason'] is None


def test_empty_budget_hint_really_recovers_results(client):
    case = next(case for case in demos(client) if case['expect_status'] == 'all_filtered')
    body = client.post('/api/recommend', json=case['request']).json()
    budget_hint = next(hint for hint in body['hints'] if 'бюджетом от' in hint)
    match = re.search(r'бюджетом от ([\d ]+) ₸', budget_hint)
    budget = int(match[1].replace(' ', ''))
    changed = case['request'] | {'budget_kzt': budget}
    result = client.post('/api/recommend', json=changed).json()
    assert result['status'] == 'found'


def test_legacy_contract_preserves_same_cards_and_statuses(client):
    mappings = {'found': 'ok', 'no_category': 'no_category_in_city', 'all_filtered': 'no_matches'}
    for case in demos(client):
        canonical = client.post('/api/recommend', json=case['request']).json()
        response = client.post('/api/recommend', json=legacy(case['request']))
        assert response.status_code == 200
        old = response.json()
        assert old['status'] == mappings[canonical['status']]
        assert old['results'] == canonical['cards']
        assert old['candidate_count'] == canonical['funnel'][0]['after']
        assert old['eligible_count'] == canonical['funnel'][-1]['after']
        assert isinstance(old['rejection_summary'], dict)


def test_original_zero_budget_preset_stays_compatible(client):
    payload = dict(city='Алматы', category='Ведущий', event_format='корпоратив',
                   date='2026-10-10', budget=0, language=None, duration_hours=None)
    response = client.post('/api/recommend', json=payload)
    assert response.status_code == 200
    assert response.json()['status'] == 'no_matches'
    assert response.json()['results'] == []


@pytest.mark.parametrize('change', [
    {'category': 'Несуществующая категория'}, {'event_type': 'Несуществующий формат'},
    {'city': 'Несуществующий город'}, {'language': 'Несуществующий язык'},
    {'date': '2026-09-22'}, {'date': '2027-01-01'}, {'date': 'bad'},
    {'budget_kzt': 0}, {'budget_kzt': -1}, {'budget_kzt': 1.5},
    {'duration_hours': 0}, {'duration_hours': -1}, {'duration_hours': 101},
    {'event_format': 'конференция'}, {'budget': 1_300_000},
])
def test_invalid_or_mixed_canonical_requests_return_russian_422(client, change):
    payload = demos(client)[0]['request'] | change
    response = client.post('/api/recommend', json=payload)
    assert response.status_code == 422
    error = response.json()
    assert re.search(r'[А-Яа-яЁё]', error['message'])
    assert error['fields']


def test_legacy_error_fields_use_form_names(client):
    payload = legacy(demos(client)[0]['request']) | {'event_format': 'неизвестно'}
    response = client.post('/api/recommend', json=payload)
    assert response.status_code == 422
    assert 'event_format' in response.json()['fields']


def test_venue_map_assets_and_preset_use_current_backend(client):
    for path in ('/web/venue-map.js', '/web/map-data.mjs', '/web/venue-map.css',
                 '/web/vendor/leaflet/leaflet.js', '/web/vendor/leaflet/leaflet.css',
                 '/web/data/venue-locations.json'):
        assert client.get(path).status_code == 200
    html = client.get('/').text
    assert 'Площадки на карте' in html and 'ДЕМО-КАРТА' in html
    source = client.get('/web/data/venue-locations.json').json()
    rows = {row.id: row for row in client.app.state.service.rows}
    assert source['version'] == 1
    for identity, place in source['locations'].items():
        assert identity in rows
        assert place['city'] == rows[identity].city
        assert place['kind'] == 'demo'
        assert -85 <= place['lat'] <= 85 and -180 <= place['lng'] <= 180
    request = dict(city='Алматы', category='Банкетный зал', event_format='свадьба',
                   date='2026-10-10', budget=6_000_000, language=None, duration_hours=None)
    response = client.post('/api/recommend', json=request)
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok' and len(body['results']) == 3
    for card in body['results']:
        assert card['id'] in source['locations']
        assert card['price_from_kzt'] == rows[card['id']].price_from_kzt
        assert date.fromisoformat(request['date']) not in rows[card['id']].busy_dates


def test_options_health_demo_static_and_openapi(client):
    for path in ('/', '/web/app.js', '/web/styles.css', '/web/enhancements.js',
                 '/web/designs.js', '/web/editorial.css', '/web/city-picker.css',
                 '/web/favicon.svg', '/web/art/host.svg', '/web/art/florist.svg',
                 '/web/art/photo.svg', '/web/art/venue.svg',
                 '/web/media/celebration-editorial.jpg', '/docs', '/openapi.json', '/health'):
        assert client.get(path).status_code == 200
    assert '<title>Той таңдау · BIMteam</title>' in client.get('/').text
    assert client.get('/web/media/celebration-editorial.jpg').headers['content-type'] == 'image/jpeg'
    assert client.get('/api/health').json() == {'ok': True, 'llm_provider': 'none', 'profiles': 66}
    options = client.get('/api/options').json()
    for field in ('cities', 'categories', 'event_formats', 'event_types', 'languages'):
        assert options[field] and options[field] == sorted(set(options[field]))
    assert options['event_formats'] == options['event_types']
    assert options['date_min'] == '2026-09-23' and options['date_max'] == '2026-12-31'
    assert len(demos(client)) == 5
    assert client.get('/.env').status_code == 404
    assert client.get('/web/.env').status_code == 404
