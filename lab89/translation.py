"""Russian to French translation with Groq, using the existing server-side key."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from .transcription import api_key


def translate(text):
    key = api_key()
    if not key:
        raise ValueError('Ключ GROQ_API_KEY не найден.')
    payload = {'model': 'openai/gpt-oss-20b', 'temperature': 0,
               'messages': [{'role': 'system', 'content': 'Translate the user text from Russian to French accurately. Preserve technical terms. Return only the French translation.'},
                            {'role': 'user', 'content': text}], 'max_completion_tokens': 4000, 'reasoning_effort': 'low'}
    req = Request('https://api.groq.com/openai/v1/chat/completions', data=json.dumps(payload).encode('utf-8'),
                  headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'EYAZIS-Labs/1.0'}, method='POST')
    try:
        with urlopen(req, timeout=90) as response:
            choice = json.load(response)['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise ValueError('Перевод не завершён. Попробуйте более короткий текст.')
        result = choice['message']['content']
        if not isinstance(result, str) or not result.strip():
            raise ValueError('Модель не вернула перевод.')
        return result.strip()
    except HTTPError as exc:
        raise ValueError(f'Groq отклонил запрос перевода (HTTP {exc.code}).') from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise ValueError('Не удалось подключиться к Groq для перевода.') from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError('Groq вернул некорректный ответ перевода.') from exc


def handle(handler):
    origin = urlsplit(handler.headers.get('Origin', ''))
    if origin.scheme != 'http' or origin.netloc != handler.headers.get('Host', '') or handler.headers.get('X-Eyazis-Request') != 'lab8':
        handler.send_json({'error': 'Запрос разрешён только со страницы приложения.'}, 403)
        return
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 32000:
            raise ValueError('Некорректный размер запроса.')
        payload = json.loads(handler.rfile.read(length))
        text = payload['text']
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError('Введите русский текст длиной до 4000 символов.')
        handler.send_json({'translation': translate(text.strip()), 'model': 'openai/gpt-oss-20b'})
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        handler.send_json({'error': str(exc)}, 400)
