import asyncio
from copy import deepcopy
import json
import httpx
import pytest
from core import ai
from core.explanations import excerpts
from core.recommend import Query, recommend

QUERY = Query(city='Алматы', date='2026-10-10', category='Ведущий', event_format='корпоратив', budget=1000000)
ROW = dict(id='one', anon_name='Профиль', city='Алматы', categories=['Ведущий'], event_formats=['корпоратив'],
           languages=['русский'], price_from_kzt=200000, max_hours=6, busy_dates=[], synthetic=True,
           city_imputed=False, price_imputed=False, description='Веду праздники. Специализируюсь на деловых встречах. Работаю с камерной аудиторией.')


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    ai._cache.clear()
    monkeypatch.setattr(ai, 'dotenv_values', lambda _: {'AI_PROVIDER':'openai','OPENAI_API_KEY':'fake','OPENAI_MODEL':'test'})
    yield
    ai._cache.clear()


def install_client(monkeypatch, mode):
    calls = []
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            calls.append(kwargs['json'])
            assert url == 'https://api.openai.com/v1/responses'
            assert kwargs['json']['store'] is False
            if mode == 'network': raise httpx.ConnectError('Ошибка')
            if mode == 'slow': await asyncio.sleep(1)
            choices = [{'id':'one', 'index':1}]
            if mode == 'unknown': choices[0]['id'] = 'other'
            if mode == 'invalid_index': choices[0]['index'] = 99
            if mode == 'bool': choices[0]['index'] = True
            if mode == 'missing': choices = []
            if mode == 'duplicate': choices *= 2
            body = {'status':'incomplete' if mode == 'incomplete' else 'completed', 'output':[
                {'type':'message','content':[{'type':'output_text','text':json.dumps({'choices':choices})}]}]}
            if mode == 'refusal': body['output'][0]['content'] = [{'type':'refusal','refusal':'Нет'}]
            if mode == 'malformed': body['output'][0]['content'][0]['text'] = 'not json'
            return httpx.Response(429 if mode == 'quota' else 200, request=httpx.Request('POST',url), json=body)
    monkeypatch.setattr(ai.httpx, 'AsyncClient', FakeClient)
    return calls


def test_relevant_evidence_and_budget():
    result = recommend(QUERY, [ROW])
    card = result['results'][0]
    assert card['profile_excerpt'] == 'Специализируюсь на деловых встречах.'
    assert card['profile_excerpt'] in card['explanation']
    assert '800 000' in card['explanation']
    assert all(q in ROW['description'] for q in excerpts(ROW['description'], QUERY))


def test_valid_and_cached(monkeypatch):
    calls = install_client(monkeypatch, 'valid')
    base = recommend(QUERY, [ROW])
    first = asyncio.run(ai.enrich(deepcopy(base), QUERY, [ROW]))
    second = asyncio.run(ai.enrich(deepcopy(base), QUERY, [ROW]))
    assert first == second
    assert len(calls) == 1
    assert first['results'][0]['explanation_source'] == 'openai_quote'
    assert first['results'][0]['profile_excerpt'] in ROW['description']
    assert first['results'][0]['id'] == base['results'][0]['id']


@pytest.mark.parametrize('mode', ['network','quota','unknown','invalid_index','bool','missing','duplicate','incomplete','refusal','malformed','slow'])
def test_fallback(monkeypatch, mode):
    install_client(monkeypatch, mode)
    monkeypatch.setattr(ai, 'TIMEOUT_SECONDS', 0.02)
    base = recommend(QUERY, [ROW])
    assert asyncio.run(ai.enrich(deepcopy(base), QUERY, [ROW])) == base
    assert not ai._cache


@pytest.mark.parametrize('settings', [{'AI_PROVIDER':'off'}, {}, {'AI_PROVIDER':'openai','OPENAI_API_KEY':'fake'}])
def test_no_configuration_no_request(monkeypatch, settings):
    monkeypatch.setattr(ai,'dotenv_values',lambda _: settings)
    monkeypatch.setattr(ai.nvidia,'dotenv_values',lambda _: {})
    calls = install_client(monkeypatch, 'valid')
    base = recommend(QUERY, [ROW])
    assert asyncio.run(ai.enrich(deepcopy(base), QUERY, [ROW])) == base
    assert not calls
