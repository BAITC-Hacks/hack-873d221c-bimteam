"""Пайплайн без веб-зависимостей: фильтры → скоринг → факты → объяснение."""
import json
import logging
from time import perf_counter

from app.config import Settings
from app.data import Contractor
from app.explain import Explainer
from app.filters import filter_contractors, result_message
from app.hints import make_hints
from app.llm import LLMClient
from app.models import RecommendRequest, RecommendResponse
from app.scoring import rank_contractors, build_cards
from app.semantic import SemanticIndex

logger = logging.getLogger('uvicorn.error')


class RecommendationService:
    """Каталог, клиенты и индекс создаются ровно один раз на lifespan."""

    def __init__(self, settings: Settings, rows: list[Contractor]) -> None:
        self.settings, self.rows = settings, rows
        self.client = LLMClient(settings)
        self.semantic = SemanticIndex(settings, rows, self.client)
        self.explainer = Explainer(settings, self.client)

    async def recommend(self, req: RecommendRequest) -> RecommendResponse:
        """Модель видит только факты уже выбранных карточек, не управляет порядком."""
        start = perf_counter()
        filtered = filter_contractors(req, self.rows)
        similarities = await self.semantic.similarities(req) if filtered.eligible else {}
        selected = rank_contractors(filtered.eligible, req, similarities)[:3]
        cards = build_cards(selected, filtered.eligible, filtered.category_city, req)
        await self.explainer.explain(req, cards)
        message, shortfall = result_message(filtered, req, self.rows)
        response = RecommendResponse(status=filtered.status, message=message, cards=cards,
            shortfall_reason=shortfall, funnel=filtered.funnel,
            hints=make_hints(req, self.rows, len(filtered.eligible)),
            elapsed_ms=round((perf_counter() - start) * 1000))
        record = req.model_dump(mode='json', exclude={'wishes'}) | dict(
            status=response.status, cards=len(cards),
            provider=self.settings.llm_provider if any(c.explanation_source == 'llm' for c in cards) else 'template',
            elapsed_ms=response.elapsed_ms)
        logger.info('recommend %s', json.dumps(record, ensure_ascii=False, sort_keys=True))
        return response

    async def close(self) -> None:
        """Закрыть используемые SDK-клиенты."""
        await self.client.close()
