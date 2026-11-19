"""French synthesis via Microsoft's online voices through edge-tts."""
import asyncio
import base64
import json
from urllib.parse import urlsplit
from . import recordings, local_client

VOICES = {"fr-FR-DeniseNeural", "fr-FR-HenriNeural", "ru-RU-SvetlanaNeural",
          "en-US-JennyNeural", "de-DE-KatjaNeural"}


async def synthesize(text, voice, rate):
    import edge_tts
    data = bytearray()
    async for item in edge_tts.Communicate(text, voice, rate=f"{round((rate - 1) * 100):+d}%").stream():
        if item["type"] == "audio":
            data.extend(item["data"])
        if len(data) > 15_000_000:
            raise ValueError("Полученное аудио слишком большое.")
    if not data:
        raise ValueError("Сервис озвучивания не вернул аудио.")
    return bytes(data)


def handle(handler):
    origin = urlsplit(handler.headers.get("Origin", ""))
    if origin.scheme != "http" or origin.netloc != handler.headers.get("Host", "") or handler.headers.get("X-Eyazis-Request") != "lab8":
        handler.send_json({"error": "Запрос разрешён только со страницы приложения."}, 403)
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        if not 0 < length <= 32_000:
            raise ValueError("Некорректный размер запроса.")
        payload = json.loads(handler.rfile.read(length))
        text, voice, rate = payload["text"], payload["voice"], float(payload["rate"])
        if not isinstance(text, str) or not text.strip() or len(text) > 6000:
            raise ValueError("Введите текст длиной до 6000 символов.")
        if voice not in VOICES | {'piper-fr_FR-siwis-medium'} or not 0.5 <= rate <= 2:
            raise ValueError("Неверный голос или скорость.")
        if voice == 'piper-fr_FR-siwis-medium':
            result = local_client.request('/synthesize', {'text': text, 'rate': rate})
            audio = base64.b64decode(result['audio'], validate=True)
        else:
            audio = asyncio.run(asyncio.wait_for(synthesize(text, voice, rate), timeout=90))
        saved = recordings.save(audio, text.strip(), voice, rate,
                                source='Piper локально' if voice.startswith('piper-') else 'Microsoft Edge TTS')
        handler.send_json({"audio": base64.b64encode(audio).decode("ascii"), "format": "mp3", "recording": saved})
    except ImportError:
        handler.send_json({"error": "Установите зависимости: python -m pip install -r lab89/requirements.txt"}, 503)
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        handler.send_json({"error": str(exc)}, 400)
    except Exception:
        handler.send_json({"error": "Сервис Microsoft Edge TTS недоступен. Проверьте интернет и повторите запрос."}, 502)
