from core.recommend import Query, recommend
from core.explanations import profile_evidence

BASE = dict(city='Астана', date='2026-11-14', category='Ведущий', event_format='той', budget=700000, language='казахский')
ROW = dict(id='a', anon_name='Ведущий А', city='Астана', categories=['Ведущий'], event_formats=['той'],
           languages=['казахский'], price_from_kzt=600000, max_hours=8, busy_dates=[], synthetic=True,
           city_imputed=False, price_imputed=False, description='Всем привет! Провожу тои на 300+ гостей. Опыт 12 лет.')


def test_unique_language_and_budget_and_exact_evidence():
    rows = [ROW, ROW | {'id':'b', 'languages':['русский']}]
    card = recommend(Query(**BASE), rows)['results'][0]
    assert 'Единственный из 2 свободных' in card['explanation']
    assert '600 000 ₸ при бюджете 700 000 ₸' in card['explanation']
    assert '100 000 ₸' in card['explanation']
    assert 'Провожу тои на 300+ гостей' in card['explanation']
    assert card['profile_excerpt'] in ROW['description']


def test_language_uniqueness_includes_unaffordable_candidates_and_unshown_results():
    rows = [ROW | {'id':str(i), 'price_from_kzt':600000+i} for i in range(5)]
    rows.append(ROW | {'id':'expensive', 'price_from_kzt':900000})
    cards = recommend(Query(**BASE), rows)['results']
    assert len(cards) == 3
    assert all('Единственный' not in card['explanation'] for card in cards)
    result = recommend(Query(**BASE), [ROW, rows[-1]])['results'][0]
    assert 'Единственный из 2 профилей' in result['explanation']
    assert 'Единственный из 2 свободных' not in result['explanation']


def test_busy_and_other_city_do_not_distort_comparison():
    rows = [ROW, ROW | {'id':'busy','busy_dates':['2026-11-14']}, ROW | {'id':'other','city':'Алматы'}]
    text = recommend(Query(**BASE),rows)['results'][0]['explanation']
    assert 'Единственный из 1 свободных' in text


def test_tied_prices_and_missing_evidence_are_honest():
    rows = [ROW | {'id':str(i),'description':''} for i in range(2)]
    text = recommend(Query(**(BASE | {'language':None})),rows)['results'][0]['explanation']
    assert 'Одна из самых низких' in text
    assert 'недостаточно конкретных сведений' in text
    assert '300' not in text


def test_negation_is_preserved_and_long_sentence_is_not_cut():
    query = Query(**BASE)
    assert profile_evidence('Не провожу тои на 300+ гостей.',query) == 'Не провожу тои на 300+ гостей.'
    assert profile_evidence('Опыт тоев ' + 'очень ' * 70,query) == ''


def test_imputed_price_and_duration_and_repeatability():
    query = Query(**(BASE | {'language':None,'duration_hours':6}))
    rows = [ROW | {'price_imputed':True}, ROW | {'id':'b','price_from_kzt':650000}]
    result = recommend(query,rows)
    assert result == recommend(query,list(reversed(rows)))
    text = result['results'][0]['explanation']
    assert 'до 8 ч на площадке при запросе 6 ч' in text
    assert 'цена проставлена при подготовке датасета' in text
