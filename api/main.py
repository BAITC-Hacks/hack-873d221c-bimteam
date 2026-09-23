from fastapi import FastAPI


app = FastAPI(title="Сервис подрядчиков")


@app.get("/health")
def health() -> dict[str, str]:
    """Проверить готовность сервиса принимать запросы."""
    return {"status": "готов"}
