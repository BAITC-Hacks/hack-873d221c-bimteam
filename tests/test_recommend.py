from copy import deepcopy
from datetime import timedelta
import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from api.main import app
from core.catalog import load_catalog
from core.recommend import Query, recommend, START
from core import nvidia

BASE = dict(city='Алматы', date='2026-10-10', category='Ведущий', event_format='корпоратив', budget=1000000)
ROW = dict(id='test', anon_name='Тест', city='Алматы', categories=['Ведущий'],
           event_formats=['корпоратив'], languages=['русский'], price_from_kzt=1000000,
           max_hours=6, busy_dates=[], synthetic=True, city_imputed=False,
           price_imputed=False, description='Проводит камерные деловые вечера и встречи команд.')


def test_catalog():
    rows = load_catalog()
    assert len(rows) == len({r['id'] for r in rows}) == 66
    assert sum(r['synthetic'] for r in rows) == 13


@pytest.mark.parametrize('change,reason', [({'busy_dates':['2026-10-10']},'busy'),
    ({'price_from_kzt':1000001},'budget'), ({'event_formats':['свадьба']},'format'),
    ({'max_hours':3},'duration'), ({'languages':['английский']},'language')])
def test_hard_constraints(change, reason):
    row = ROW | change
    result = recommend(Query(**(BASE | {'duration_hours':4,'language':'русский'})), [row])
    assert result['status'] == 'no_matches'
    assert result['rejection_summary'][reason] == 1
    assert not result['results']


def test_boundaries_and_short_result():
    result = recommend(Query(**(BASE | {'duration_hours':20})), [ROW | {'max_hours':None}])
    assert result['eligible_count'] == 1
    assert 'меньше трёх' in result['message']


def test_absent_category():
    result = recommend(Query(**(BASE | {'city':'Астана'})), [ROW])
    assert result['status'] == 'no_category_in_city'


def test_order_and_limit():
    rows = [ROW | {'id':i} for i in ['d','c','b','a']]
    first = recommend(Query(**BASE), rows)
    assert [r['id'] for r in first['results']] == ['a','b','c']
    assert first == recommend(Query(**BASE), list(reversed(rows)))


def test_dates_change_results():
    rows = [ROW | {'busy_dates':['2026-10-10']}]
    assert not recommend(Query(**BASE), rows)['results']
    assert recommend(Query(**(BASE | {'date':'2026-10-11'})), rows)['results']


@pytest.mark.parametrize('change', [{'budget':-1},{'date':'2027-01-01'}, {'date':'bad'}, {'duration_hours':0}, {'city':' '}])
def test_bad_request(change, monkeypatch):
    monkeypatch.setattr(nvidia, 'dotenv_values', lambda _: {})
    response = TestClient(app).post('/api/recommend', json=BASE | change)
    assert response.status_code == 422
    assert 'Проверьте' in response.json()['message']


def test_live_data_and_pages(monkeypatch):
    monkeypatch.setattr(nvidia, 'dotenv_values', lambda _: {})
    client = TestClient(app)
    for path in ['/', '/web/app.js', '/web/styles.css', '/health', '/docs', '/api/options']:
        assert client.get(path).status_code == 200
    response = client.post('/api/recommend', json=BASE)
    assert response.status_code == 200
    assert response.json() == client.post('/api/recommend', json=BASE).json()
    by_id = {r['id']:r for r in load_catalog()}
    for card in response.json()['results']:
        row = by_id[card['id']]
        assert BASE['date'] not in row['busy_dates']
        assert card['price_from_kzt'] <= BASE['budget']
        assert card['profile_excerpt'] in row['description']


@pytest.mark.parametrize('mode', ['failure', 'invalid', 'valid'])
def test_nvidia_fallback_and_quote_validation(monkeypatch, mode):
    monkeypatch.setattr(nvidia, 'dotenv_values', lambda _: {'NVIDIA_API_KEY':'test','LLM_MODEL':'test'})
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            if mode == 'failure': raise httpx.ConnectError('Недоступно')
            import json
            quote = ROW['description'] if mode == 'valid' else 'Выдуманная характеристика подрядчика'
            return httpx.Response(200, request=httpx.Request('POST','https://example.com'),
                json={'choices':[{'message':{'content':json.dumps({'quotes':{'test':quote}})}}]})
    monkeypatch.setattr(nvidia.httpx, 'AsyncClient', FakeClient)
    original = recommend(Query(**BASE), [ROW])
    result = asyncio.run(nvidia.enrich(deepcopy(original), Query(**BASE), [ROW]))
    if mode == 'valid':
        assert result['results'][0]['explanation_source'] == 'nvidia_quote'
    else:
        assert result == original
