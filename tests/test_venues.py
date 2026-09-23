from fastapi.testclient import TestClient
from api.main import app
from core.catalog import load_catalog
from core.recommend import Query, recommend
from core.venues import venue_catalog, venue_name


def test_overview_is_complete_sorted_and_uses_catalog_prices():
    rows = load_catalog()
    result = venue_catalog(rows)
    assert len(result['venues']) == 8
    assert result['availability_checked'] is False
    assert result == venue_catalog(list(reversed(rows)))
    originals = {row['id']: row for row in rows}
    for venue in result['venues']:
        original = originals[venue['id']]
        assert venue['name'] in original['description']
        assert venue['price_from_kzt'] == original['price_from_kzt']
        assert venue['profile_name'] == original['anon_name']
        assert venue['price_imputed'] == original['price_imputed']
        assert 'busy_dates' not in venue


def test_city_overview_is_not_limited_to_three_or_search_budget():
    client = TestClient(app)
    response = client.get('/api/venues', params={'city': 'Алматы'})
    assert response.status_code == 200
    data = response.json()
    assert len(data['venues']) == 7
    assert data['venues'][0]['name'] == 'Villa Cavallone'
    assert data['venues'][0]['price_from_kzt'] == 2000000
    assert len(client.get('/api/venues', params={'city': 'Астана'}).json()['venues']) == 1
    assert client.get('/api/venues', params={'city': 'Зарубежье'}).json()['venues'] == []
    query = Query(city='Алматы', date='2026-10-10', category='Ресторан', event_format='свадьба', budget=1000000)
    assert recommend(query, load_catalog())['results'] == []


def test_recommendation_keeps_profile_name_and_exposes_venue_name():
    query = Query(city='Алматы', date='2026-10-10', category='Ресторан', event_format='свадьба', budget=6000000)
    results = recommend(query, load_catalog())['results']
    assert len(results) == 3
    assert results[0]['name'] == 'Хината Хьюга'
    assert results[0]['venue_name'] == 'Villa Cavallone'


def test_unknown_description_falls_back_to_profile_name():
    assert venue_name({'anon_name': 'Имя профиля', 'description': 'Описание без названия.'}) == 'Имя профиля'
    assert venue_name({'anon_name': 'Имя профиля', 'description': '  Тестовый ресторан — описание.'}) == 'Тестовый ресторан'
