"""Семантика необязательна; тестовые векторы не требуют внешнего API."""
import asyncio
from dataclasses import replace
import json

import numpy as np
import pytest

from app.config import Settings
from app.data import load_contractors
from app.models import RecommendRequest
from app.semantic import SemanticIndex, dataset_fingerprint


class FakeClient:
    def __init__(self, vector=None, error=None):
        self.vector = [1.0, 0.0] if vector is None else vector
        self.error = error
        self.calls = 0

    async def embed(self, texts, *, query=False):
        self.calls += 1
        assert len(texts) == 1 and query
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return [self.vector]


def req():
    return RecommendRequest(city='Алматы', date='2026-10-10', event_type='свадьба',
                            category='Ведущий', budget_kzt=700_000, wishes='камерная свадьба')


@pytest.fixture
def bundle(tmp_path):
    settings = Settings(_env_file=None, llm_provider='none', embedding_provider='openai',
                        embedding_model='fake-embedding', cache_dir=tmp_path / 'cache',
                        embeddings_path=tmp_path / 'embeddings.npy',
                        embeddings_ids_path=tmp_path / 'ids.json')
    rows = load_contractors(settings)[:2]
    return settings, rows


def write_index(settings, rows, **meta_changes):
    np.save(settings.embeddings_path, np.array([[3.0, 0.0], [0.0, 2.0]]))
    meta = dict(ids=[row.id for row in rows], fingerprint=dataset_fingerprint(rows),
                provider=settings.embedding_provider, model=settings.embedding_model)
    settings.embeddings_ids_path.write_text(json.dumps(meta | meta_changes), encoding='utf-8')


def test_missing_files_disable_semantics_without_calling_api(bundle):
    settings, rows = bundle
    client = FakeClient(error=AssertionError('Нет файлов — нет API'))
    index = SemanticIndex(settings, rows, client)
    assert asyncio.run(index.similarities(req())) == {}
    assert client.calls == 0


@pytest.mark.parametrize('change', [{'ids': ['wrong', 'ids']}, {'fingerprint': 'stale'},
                                    {'model': 'another-model'}, {'provider': 'nvidia'}])
def test_stale_index_is_ignored_without_api(bundle, change):
    settings, rows = bundle
    write_index(settings, rows, **change)
    client = FakeClient()
    index = SemanticIndex(settings, rows, client)
    assert asyncio.run(index.similarities(req())) == {}
    assert client.calls == 0


def test_description_change_invalidates_fingerprint(bundle):
    settings, rows = bundle
    write_index(settings, rows)
    changed = [replace(rows[0], description=rows[0].description + ' Новый текст.'), rows[1]]
    assert dataset_fingerprint(rows) == dataset_fingerprint(list(reversed(rows)))
    assert dataset_fingerprint(changed) != dataset_fingerprint(rows)
    assert SemanticIndex(settings, changed, FakeClient()).matrix is None


def test_valid_vectors_cosine_cache_and_restart(bundle):
    settings, rows = bundle
    write_index(settings, rows)
    client = FakeClient([2.0, 0.0])
    index = SemanticIndex(settings, rows, client)
    result = asyncio.run(index.similarities(req()))
    assert result == pytest.approx({rows[0].id: 1.0, rows[1].id: 0.0})
    assert asyncio.run(index.similarities(req())) == result
    assert client.calls == 1
    restarted = FakeClient(error=AssertionError('Должен использоваться дисковый кэш'))
    assert asyncio.run(SemanticIndex(settings, rows, restarted).similarities(req())) == result
    assert restarted.calls == 0


@pytest.mark.parametrize('vector', [[0.0, 0.0], [float('nan'), 1.0], [1.0, 0.0, 0.0]])
def test_invalid_query_vector_uses_cached_zero_semantics(bundle, vector):
    settings, rows = bundle
    write_index(settings, rows)
    client = FakeClient(vector)
    index = SemanticIndex(settings, rows, client)
    assert asyncio.run(index.similarities(req())) == {}
    assert asyncio.run(index.similarities(req())) == {}
    assert client.calls == 1


def test_failed_query_caches_disabled_state_across_restart(bundle):
    settings, rows = bundle
    write_index(settings, rows)
    client = FakeClient(error=OSError('Сеть недоступна'))
    assert asyncio.run(SemanticIndex(settings, rows, client).similarities(req())) == {}
    assert client.calls == 1
    restarted = FakeClient()
    assert asyncio.run(SemanticIndex(settings, rows, restarted).similarities(req())) == {}
    assert restarted.calls == 0


def test_concurrent_same_embedding_is_requested_once(bundle):
    settings, rows = bundle
    write_index(settings, rows)
    client = FakeClient()
    index = SemanticIndex(settings, rows, client)
    async def both():
        return await asyncio.gather(index.similarities(req()), index.similarities(req()))
    first, second = asyncio.run(both())
    assert first == second and client.calls == 1
