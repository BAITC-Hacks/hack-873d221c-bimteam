from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from core.catalog import ROOT, load_catalog
from core.recommend import Query, recommend, START, END
from core.nvidia import enrich
from core.venues import venue_catalog


app = FastAPI(title="Сервис подрядчиков")
catalog = load_catalog()
app.mount('/web', StaticFiles(directory=ROOT / 'web'), name='web')


@app.get('/')
def index():
    return FileResponse(ROOT / 'web/index.html')


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        'message': 'Проверьте поля: город, категория, формат, бюджет от 0; дата — с 23.09.2026 по 31.12.2026; длительность — больше 0.',
        'fields': [str(e['loc'][-1]) for e in exc.errors()]})


@app.get('/api/options')
def options():
    return {'cities': sorted({r['city'] for r in catalog}),
            **{field: sorted({v for r in catalog for v in r[field]})
               for field in ('categories', 'event_formats', 'languages')},
            'date_min': START.isoformat(), 'date_max': END.isoformat()}


@app.post('/api/recommend')
async def get_recommendations(query: Query):
    return await enrich(recommend(query, catalog), query, catalog)


@app.get('/api/venues')
def get_venues(city: str | None = None):
    return venue_catalog(catalog, city)


@app.get("/health")
def health() -> dict[str, str]:
    """Проверить готовность сервиса принимать запросы."""
    return {"status": "готов"}
