"""Bounded local proxy for Groq Whisper; audio and keys are never saved here."""
import base64
import binascii
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
from . import local_client

MAX_AUDIO = 10 * 1024 * 1024
FORMATS = {"webm": "audio/webm", "wav": "audio/wav", "mp3": "audio/mpeg",
           "m4a": "audio/mp4", "mp4": "audio/mp4", "ogg": "audio/ogg", "flac": "audio/flac"}
LANGUAGES = {'fr', 'ru', 'en', 'de'}
CONTEXTS = {
    'fr': 'Transcription en français. Informatique, algorithme, données, logiciel, réseau.',
    'ru': 'Транскрипция на русском языке. Информатика, алгоритм, данные, программа, сеть.',
    'en': 'English transcription. Computer science, algorithm, data, software, network.',
    'de': 'Transkription auf Deutsch. Informatik, Algorithmus, Daten, Software, Netzwerk.',
}


def api_key():
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    # Project-local key is convenient for this app; keep it outside version control.
    root = os.environ.get("LOCALAPPDATA")
    paths = [Path(__file__).resolve().parent.parent / '.env.groq']
    if root:
        paths.append(Path(root) / "TgAgent" / "secrets" / ".env.groq")
    for path in paths:
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip() == "GROQ_API_KEY" and value.strip().strip("\"'"):
                    return value.strip().strip("\"'")
    return ""


def transcribe(audio, extension, key, opener=urlopen, language='fr'):
    if not key:
        raise ValueError("Ключ GROQ_API_KEY не найден. Настройте переменную окружения или файл .env.groq в папке проекта.")
    if extension not in FORMATS or not audio or len(audio) > MAX_AUDIO:
        raise ValueError("Нужен аудиофайл webm, wav, mp3, m4a, mp4, ogg или flac размером до 10 МБ.")
    if language not in LANGUAGES:
        raise ValueError('Неподдерживаемый язык распознавания.')
    boundary = "eyazis" + uuid4().hex
    parts = []
    for name, value in (("model", "whisper-large-v3-turbo"), ("language", language),
                        ("prompt", CONTEXTS[language]), ("response_format", "json"), ("temperature", "0")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.{extension}"\r\nContent-Type: {FORMATS[extension]}\r\n\r\n'.encode() + audio + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    request = Request("https://api.groq.com/openai/v1/audio/transcriptions", data=b"".join(parts),
                      headers={"Authorization": "Bearer " + key, "Content-Type": "multipart/form-data; boundary=" + boundary,
                               "User-Agent": "EYAZIS-Labs/1.0"}, method="POST")
    try:
        with opener(request, timeout=90) as response:
            data = json.load(response)
    except HTTPError as exc:
        raise ValueError(f"Groq отклонил запрос (HTTP {exc.code}). Проверьте ключ, лимиты и формат аудио.") from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise ValueError("Не удалось подключиться к Groq. Проверьте интернет.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        raise ValueError("Groq вернул некорректный ответ.")
    return data["text"].strip()


def handle(handler):
    origin = urlsplit(handler.headers.get("Origin", ""))
    host = handler.headers.get("Host", "")
    if origin.scheme != "http" or origin.netloc != host or handler.headers.get("X-Eyazis-Request") != "lab9":
        handler.send_json({"error": "Запрос разрешён только со страницы приложения."}, 403)
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        if length <= 0 or length > (MAX_AUDIO * 4 // 3 + 4096):
            handler.send_json({"error": "Аудио должно быть размером до 10 МБ."}, 413)
            return
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict) or not isinstance(payload.get("audio"), str) or not isinstance(payload.get("format"), str):
            raise ValueError("Неверный формат запроса.")
        audio = base64.b64decode(payload["audio"], validate=True)
        extension = payload["format"].lower()
        if extension not in FORMATS or not audio or len(audio) > MAX_AUDIO:
            raise ValueError("Неподдерживаемый формат или размер аудио.")
        engine = payload.get('engine', 'groq')
        language = payload.get('language', 'fr')
        if not isinstance(language, str) or language not in LANGUAGES:
            raise ValueError('Неподдерживаемый язык распознавания.')
        if engine == 'local':
            result = local_client.request('/transcribe', {'audio': payload['audio'], 'language': language})
            text = result['text']
        elif engine == 'groq':
            text = transcribe(audio, extension, api_key(), language=language)
        else:
            raise ValueError('Неизвестный движок распознавания.')
        handler.send_json({"text": text, "language": language, "model": "whisper-large-v3-turbo", "engine": engine})
    except (ValueError, TypeError, UnicodeError, binascii.Error, OSError) as exc:
        handler.send_json({"error": str(exc)}, 400)
