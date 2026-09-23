"""Старая команда uvicorn api.main:app совместима; логика находится в app/."""
from app.main import app

__all__ = ['app']
