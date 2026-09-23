"""Общий SDK, атомарный файловый кэш, без скрытых сетевых повторов."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from weakref import WeakValueDictionary

from openai import AsyncOpenAI

from app.config import Settings


def cache_key(payload: Any) -> str:
    """Стабильный ключ: нет времени, случайности или секрета."""
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class DiskCache:
    """Кэш локального демо. Отсутствующая/повреждённая запись считается промахом."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._memory: dict[str, Any] = {}
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def lock(self, key: str) -> asyncio.Lock:
        """Объединить одновременные одинаковые запросы одного процесса."""
        return self._locks.setdefault(key, asyncio.Lock())

    def get(self, key: str) -> Any:
        """Загрузить JSON; не интерпретировать содержимое как код."""
        if key in self._memory:
            return self._memory[key]
        try:
            path = self.directory / f'{key}.json'
            if path.stat().st_size > 1_000_000:
                return None
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def put(self, key: str, value: Any) -> None:
        """Сначала временный файл, затем атомарная замена; сбой диска не роняет подбор."""
        if len(self._memory) >= 256:
            self._memory.pop(next(iter(self._memory)))
        self._memory[key] = value
        temp_path = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                             suffix='.tmp', delete=False) as source:
                temp_path = Path(source.name)
                json.dump(value, source, ensure_ascii=False, allow_nan=False)
            os.replace(temp_path, self.directory / f'{key}.json')
        except (OSError, ValueError):
            pass
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass


class LLMClient:
    """Один выбранный провайдер; переключение на NVIDIA явно через .env."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.clients: dict[str, AsyncOpenAI] = {}
        for provider in sorted({settings.llm_provider, settings.embedding_provider} - {'none'}):
            if settings.api_key(provider):
                self.clients[provider] = AsyncOpenAI(
                    api_key=settings.api_key(provider), max_retries=0, timeout=settings.llm_timeout_s,
                    base_url='https://integrate.api.nvidia.com/v1' if provider == 'nvidia' else 'https://api.openai.com/v1')

    @property
    def available(self) -> bool:
        """Без ключа и имени модели внешних вызовов нет."""
        return self.settings.llm_provider in self.clients and bool(self.settings.llm_model)

    async def complete(self, system: str, payload: dict, correction: str | None = None) -> str:
        """Один batch из уже выбранных карточек; SDK retries отключены."""
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
        if correction:
            messages.append({'role': 'user', 'content': 'Исправь ошибки проверки и верни весь JSON: ' + correction})
        kwargs = {'seed': self.settings.llm_seed} if self.settings.llm_seed is not None else {}
        response = await self.clients[self.settings.llm_provider].chat.completions.create(
            model=self.settings.llm_model, temperature=0, max_tokens=1200,
            response_format={'type': 'json_object'}, messages=messages, **kwargs)
        if not response.choices or response.choices[0].finish_reason != 'stop':
            raise ValueError('Модель вернула неполный ответ')
        return response.choices[0].message.content or ''

    async def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        """Векторы в порядке входных текстов, NVIDIA получает тип query/passage."""
        provider = self.settings.embedding_provider
        if provider not in self.clients or not self.settings.embedding_model:
            raise ValueError('Не заданы провайдер, модель или ключ эмбеддингов')
        extra = {'extra_body': {'input_type': 'query' if query else 'passage', 'truncate': 'END'}} if provider == 'nvidia' else {}
        response = await self.clients[provider].embeddings.create(
            model=self.settings.embedding_model, input=texts, encoding_format='float', **extra)
        items = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in items] != list(range(len(texts))):
            raise ValueError('Неполный набор эмбеддингов')
        return [item.embedding for item in items]

    async def close(self) -> None:
        """Освободить сетевые соединения при остановке приложения."""
        for client in self.clients.values():
            await client.close()
