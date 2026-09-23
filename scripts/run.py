"""Локальный сервер; браузер открывается только после успешного health-запроса."""
import argparse
from pathlib import Path
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def open_when_ready() -> None:
    """Подождать готовности сервера в отдельном потоке, не задерживая запуск."""
    for _ in range(60):
        try:
            with urlopen('http://127.0.0.1:8000/api/health', timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open('http://127.0.0.1:8000/')
                    return
        except (OSError, URLError):
            time.sleep(0.5)


def main() -> None:
    """--check проверяет установку без запуска фонового сервера и браузера."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        from app.config import Settings
        from app.data import load_contractors
        from app.main import create_app
        settings = Settings(_env_file=None, llm_provider='none')
        create_app(settings)
        print(f'Установка готова, профилей: {len(load_contractors(settings))}')
        return
    import uvicorn
    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000, access_log=False)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
