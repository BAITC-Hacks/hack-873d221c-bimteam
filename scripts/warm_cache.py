"""Прогреть 5 демо-запросов с настройками .env до выступления."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.data import load_contractors
from app.models import RecommendRequest
from app.pipeline import RecommendationService


async def warm() -> None:
    """Два прохода показывают источник объяснений и время тёплого ответа."""
    settings = Settings()
    cases = json.loads(settings.demo_path.read_text(encoding='utf-8'))
    service = RecommendationService(settings, load_contractors(settings))
    try:
        for run in range(1, 3):
            for case in cases:
                result = await service.recommend(RecommendRequest(**case['request']))
                sources = sorted({c.explanation_source for c in result.cards})
                print(f'{run}: {case["title"]}: {result.status}, {sources}, {result.elapsed_ms} мс')
    finally:
        await service.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(warm())
