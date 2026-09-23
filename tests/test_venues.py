"""Обзор площадок работает с актуальным app/, без внешних ключей и запросов."""
from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.venues import venue_catalog, venue_name


@pytest.fixture
def client(tmp_path, monkeypatch):
    def forbidden_sdk(**kwargs):
        raise AssertionError('Обзор не должен создавать внешний SDK')
    monkeypatch.setattr('app.llm.AsyncOpenAI', forbidden_sdk)
    settings = Settings(_env_file=None, llm_provider='none', embedding_provider='none', cache_dir=tmp_path)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_overview_is_complete_sorted_and_uses_catalog_prices(client):
    rows = client.app.state.service.rows
    result = venue_catalog(rows)
    assert len(result['venues']) == 8
    assert result['availability_checked'] is False
    assert result == venue_catalog(list(reversed(rows)))
    assert [(v['price_from_kzt'], v['id']) for v in result['venues']] == sorted(
        (v['price_from_kzt'], v['id']) for v in result['venues'])
    originals = {row.id: row for row in rows}
    for venue in result['venues']:
        original = originals[venue['id']]
        assert venue['name'] in original.description
        assert venue['price_from_kzt'] == original.price_from_kzt
        assert venue['profile_name'] == original.name
        for flag in ('price_imputed', 'city_imputed', 'synthetic'):
            assert venue[flag] == getattr(original, flag)
        assert 'busy_dates' not in venue
    assert client.get('/api/venues').json() == result


def test_city_overview_is_not_limited_to_three_or_search_budget(client):
    response = client.get('/api/venues', params={'city': 'Алматы'})
    assert response.status_code == 200
    data = response.json()
    assert len(data['venues']) == 7
    assert data['availability_checked'] is False
    assert data['venues'][0]['name'] == 'Villa Cavallone'
    assert data['venues'][0]['price_from_kzt'] == 2_000_000
    assert len(client.get('/api/venues', params={'city': 'Астана'}).json()['venues']) == 1
    for city in ('Зарубежье', 'Несуществующий город'):
        assert client.get('/api/venues', params={'city': city}).json()['venues'] == []
    query = dict(city='Алматы', date='2026-10-10', category='Ресторан',
                 event_format='свадьба', budget=1_000_000)
    assert client.post('/api/recommend', json=query).json()['results'] == []
    assert client.get('/api/venues', params={'city': 'Алматы'}).json() == data


@pytest.mark.parametrize('legacy', [False, True])
def test_recommendation_keeps_profile_name_and_exposes_venue_name(client, legacy):
    query = dict(city='Алматы', date='2026-10-10', category='Ресторан')
    query.update({'event_format': 'свадьба', 'budget': 6_000_000} if legacy else
                 {'event_type': 'свадьба', 'budget_kzt': 6_000_000})
    response = client.post('/api/recommend', json=query)
    assert response.status_code == 200
    results = response.json()['results' if legacy else 'cards']
    assert len(results) == 3
    assert results[0]['name'] == 'Хината Хьюга'
    assert results[0]['venue_name'] == 'Villa Cavallone'
    assert all(card['price_from_kzt'] <= 6_000_000 for card in results)


def test_unknown_description_falls_back_to_profile_name(client):
    row = client.app.state.service.rows[0]
    assert venue_name(replace(row, name='Имя профиля', description='Описание без названия.')) == 'Имя профиля'
    assert venue_name(replace(row, description='  Тестовый ресторан — описание.')) == 'Тестовый ресторан'


def test_nonvenue_recommendation_has_no_venue_name(client):
    case = client.get('/api/demo').json()[0]
    result = client.post('/api/recommend', json=case['request']).json()
    assert result['cards']
    assert all(card['venue_name'] is None for card in result['cards'])
