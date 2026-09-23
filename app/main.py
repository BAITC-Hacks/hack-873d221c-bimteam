"""FastAPI и совместимость с существующим интерфейсом без правок web/."""
from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, Settings
from app.data import load_contractors, catalog_options
from app.models import LegacyRequest, LegacyResponse, RecommendRequest, RecommendResponse
from app.pipeline import RecommendationService
from app.venues import venue_catalog


def legacy_response(result: RecommendResponse) -> LegacyResponse:
    """Перевести названия полей, не менять результаты фильтрации/скоринга."""
    names = dict(date='busy', budget='budget', event_format='format', duration='duration', language='language')
    return LegacyResponse(
        status={'found': 'ok', 'no_category': 'no_category_in_city', 'all_filtered': 'no_matches'}[result.status],
        message=result.message, results=result.cards, candidate_count=result.funnel[0].after,
        eligible_count=result.funnel[-1].after,
        rejection_summary={names[f.step]: len(f.rejected_ids) for f in result.funnel[1:]},
        shortfall_reason=result.shortfall_reason, funnel=result.funnel, hints=result.hints, elapsed_ms=result.elapsed_ms)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Фабрика для изолированных оффлайн-тестов и рабочего процесса сервера."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        rows = load_contractors(settings)
        service = RecommendationService(settings, rows)
        application.state.service = service
        application.state.options = catalog_options(rows)
        application.state.demo = json.loads(settings.demo_path.read_text(encoding='utf-8')) if settings.demo_path.exists() else None
        try:
            yield
        finally:
            await service.close()

    application = FastAPI(title='Точно к месту — подбор подрядчиков', version='2.0', lifespan=lifespan)
    application.mount('/web', StaticFiles(directory=ROOT / 'web'), name='web')

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({str(error['loc'][-1]) for error in exc.errors()})
        body = exc.body if isinstance(exc.body, dict) else {}
        if 'event_format' in body or 'budget' in body:
            names = {'event_type': 'event_format', 'budget_kzt': 'budget'}
            fields = sorted({names.get(field, field) for field in fields})
        return JSONResponse(status_code=422, content={
            'message': 'Проверьте поля запроса. Дата: 23.09–31.12.2026; бюджет — целое положительное число; '
                       'длительность — больше 0 и до 100 ч. Используйте один формат API, без смешения названий полей.',
            'fields': fields})

    @application.get('/', include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(ROOT / 'web/index.html')

    @application.get('/api/options')
    async def options(request: Request) -> dict:
        return request.app.state.options

    @application.get('/api/demo')
    async def demo(request: Request):
        if request.app.state.demo is None:
            return JSONResponse(status_code=503, content={'message': 'Сначала выполните python scripts/find_demo_queries.py'})
        return request.app.state.demo

    @application.get('/api/venues')
    async def venues(request: Request, city: str | None = None) -> dict:
        """Обзор цен, не подбор: бюджет и доступность не проверяются."""
        return venue_catalog(request.app.state.service.rows, city)

    @application.get('/api/health')
    async def health(request: Request) -> dict:
        service = request.app.state.service
        return {'ok': True, 'llm_provider': settings.llm_provider, 'profiles': len(service.rows)}

    @application.get('/health', include_in_schema=False)
    async def old_health() -> dict:
        return {'status': 'готов'}

    @application.post('/api/recommend', response_model=RecommendResponse | LegacyResponse)
    async def recommend(query: RecommendRequest | LegacyRequest, request: Request):
        options = request.app.state.options
        invalid = [field for field, key in [('category', 'categories'), ('event_type', 'event_types'),
                                            ('city', 'cities'), ('language', 'languages')]
                   if getattr(query, field) is not None and getattr(query, field) not in options[key]]
        if invalid:
            if isinstance(query, LegacyRequest):
                invalid = ['event_format' if f == 'event_type' else f for f in invalid]
            return JSONResponse(status_code=422, content={
                'message': 'Проверьте значения: ' + ', '.join(invalid) + '. Выберите варианты из /api/options.',
                'fields': invalid})
        result = await request.app.state.service.recommend(query)
        return legacy_response(result) if isinstance(query, LegacyRequest) else result

    return application


app = create_app()
