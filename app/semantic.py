"""Необязательные предрассчитанные векторы; отсутствие файлов = нулевая семантика."""
import asyncio
import json

import numpy as np
from openai import OpenAIError

from app.config import Settings
from app.data import Contractor
from app.llm import DiskCache, LLMClient, cache_key
from app.models import RecommendRequest


def dataset_fingerprint(rows: list[Contractor]) -> str:
    """Изменение описания делает старые векторы непригодными."""
    return cache_key([(c.id, c.description) for c in sorted(rows, key=lambda c: c.id)])


class SemanticIndex:
    """Вектора нормируются один раз при старте, а текст запроса кэшируется."""

    def __init__(self, settings: Settings, rows: list[Contractor], client: LLMClient) -> None:
        self.settings, self.client = settings, client
        self.cache = DiskCache(settings.cache_dir / 'embeddings')
        self.matrix: np.ndarray | None = None
        self.ids: list[str] = []
        self.fingerprint = dataset_fingerprint(rows)
        try:
            if settings.embedding_provider == 'none':
                return
            meta = json.loads(settings.embeddings_ids_path.read_text(encoding='utf-8'))
            matrix = np.load(settings.embeddings_path, allow_pickle=False)
            ids = [c.id for c in rows]
            if (meta['ids'] != ids or meta['fingerprint'] != self.fingerprint
                    or meta['model'] != settings.embedding_model or meta['provider'] != settings.embedding_provider
                    or matrix.ndim != 2 or matrix.shape[0] != len(ids) or not np.isfinite(matrix).all()):
                return
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            if np.any(norms == 0):
                return
            self.matrix, self.ids = matrix / norms, ids
        except (OSError, ValueError, TypeError, KeyError):
            pass

    async def similarities(self, req: RecommendRequest) -> dict[str, float]:
        """Максимум один embedding-вызов на новый текст; сбой тоже кэшируется."""
        if self.matrix is None:
            return {}
        text = ' | '.join(filter(None, (req.event_type, req.category, req.wishes)))
        key = cache_key([self.settings.embedding_provider, self.settings.embedding_model,
                         self.fingerprint, text])
        async with self.cache.lock(key):
            cached = self.cache.get(key)
            if isinstance(cached, dict) and cached.get('disabled') is True:
                return {}
            try:
                if cached is None:
                    vectors = await asyncio.wait_for(self.client.embed([text], query=True), self.settings.embedding_timeout_s)
                    cached = {'vector': vectors[0]}
                vector = np.asarray(cached['vector'], dtype=float)
                norm = np.linalg.norm(vector)
                if vector.shape != (self.matrix.shape[1],) or not np.isfinite(vector).all() or norm == 0:
                    raise ValueError('Неверный вектор запроса')
                similarities = self.matrix @ (vector / norm)
                self.cache.put(key, cached)
                return {identity: float(value) for identity, value in zip(self.ids, similarities)}
            except (OpenAIError, TimeoutError, OSError, ValueError, TypeError, KeyError, IndexError):
                self.cache.put(key, {'disabled': True})
                return {}
