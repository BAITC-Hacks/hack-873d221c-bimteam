"""SDK-контракт проверяется подставным транспортом, без расхода API."""
import asyncio
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.llm import DiskCache, LLMClient, cache_key


@pytest.mark.parametrize('provider', ['openai', 'nvidia'])
def test_sdk_contract(monkeypatch, provider):
    created, calls = [], []
    class Client:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.chat_call))
            self.embeddings = SimpleNamespace(create=self.embed_call)
        async def chat_call(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{}'))])
        async def embed_call(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(index=1, embedding=[0, 1]), SimpleNamespace(index=0, embedding=[1, 0])])
        async def close(self):
            pass
    monkeypatch.setattr('app.llm.AsyncOpenAI', Client)
    settings = Settings(_env_file=None, llm_provider=provider, embedding_provider=provider,
        embedding_model='embed', openai_api_key='test', nvidia_api_key='test',
        openai_model='test-model', nvidia_model='test-model', llm_seed=42)
    client = LLMClient(settings)
    assert client.available and len(created) == 1 and created[0]['max_retries'] == 0
    assert ('nvidia.com' in created[0]['base_url']) == (provider == 'nvidia')
    assert asyncio.run(client.complete('JSON system', {'cards': []}, 'Повтори JSON')) == '{}'
    assert calls[0]['temperature'] == 0 and calls[0]['seed'] == 42
    assert calls[0]['response_format'] == {'type': 'json_object'}
    assert len(calls[0]['messages']) == 3
    assert asyncio.run(client.embed(['a', 'b'], query=True)) == [[1, 0], [0, 1]]
    if provider == 'nvidia':
        assert calls[1]['extra_body']['input_type'] == 'query'
    asyncio.run(client.close())


def test_cache_key_normalized_and_atomic_json(tmp_path):
    assert cache_key({'a': 1, 'b': 2}) == cache_key({'b': 2, 'a': 1})
    key = cache_key({'text': 'пример'})
    cache = DiskCache(tmp_path)
    cache.put(key, {'text': 'Ответ'})
    assert DiskCache(tmp_path).get(key) == {'text': 'Ответ'}
    assert not list(tmp_path.glob('*.tmp'))
    (tmp_path / f'{key}.json').write_text('broken', encoding='utf-8')
    assert DiskCache(tmp_path).get(key) is None
