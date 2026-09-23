"""Разовый предрасчёт описаний; явно запускается человеком с его API-ключом."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from app.config import Settings
from app.data import load_contractors
from app.llm import LLMClient
from app.semantic import dataset_fingerprint


async def build() -> None:
    """Сохранить матрицу, ID, модель и отпечаток текста для защиты от устаревания."""
    settings = Settings()
    if settings.embedding_provider == 'none' or not settings.embedding_model or not settings.api_key(settings.embedding_provider):
        raise SystemExit('Заполните EMBEDDING_PROVIDER, EMBEDDING_MODEL и ключ в .env. Без этого сервис работает без семантики.')
    rows = load_contractors(settings)
    client = LLMClient(settings)
    try:
        vectors = []
        for offset in range(0, len(rows), 16):
            batch = await asyncio.wait_for(client.embed([c.description for c in rows[offset:offset+16]]), timeout=60)
            vectors.extend(batch)
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(rows) or not np.isfinite(matrix).all() or np.any(np.linalg.norm(matrix, axis=1) == 0):
            raise ValueError('Неполные или неверные векторы')
        settings.embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        settings.embeddings_ids_path.parent.mkdir(parents=True, exist_ok=True)
        # Читатель проверяет согласованность обоих файлов до использования.
        np.save(settings.embeddings_path, matrix, allow_pickle=False)
        metadata = dict(ids=[c.id for c in rows], fingerprint=dataset_fingerprint(rows),
                        provider=settings.embedding_provider, model=settings.embedding_model)
        settings.embeddings_ids_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Готово: {len(rows)} описаний, размерность {matrix.shape[1]}. Перезапустите сервер.')
    finally:
        await client.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(build())
