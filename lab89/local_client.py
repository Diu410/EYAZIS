"""Requests to the local Docker speech service; no cloud fallback."""
import json
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


def request(path, payload):
    port = 8899 if path == '/synthesize' else 8900
    req = Request(f'http://127.0.0.1:{port}' + path, data=json.dumps(payload).encode('utf-8'),
                  headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(req, timeout=1800) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            detail = json.load(exc).get('error', '')
        except Exception:
            detail = ''
        raise ValueError(detail or f'Ошибка локального сервиса (HTTP {exc.code}).') from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise ValueError('Локальный сервис недоступен. Запустите Docker: docker compose -f lab89/local/compose.yaml up -d --build') from exc
