"""Streaming Silero VAD: per-session recurrent state, no audio persistence."""
import base64
import binascii
import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

MODEL = Path(__file__).with_name('models') / 'silero_vad_v6.onnx'
_lock = threading.Lock()
_model = None
_sessions = {}


def _get_model():
    global _model
    if _model is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        _model = ort.InferenceSession(str(MODEL), sess_options=opts, providers=['CPUExecutionProvider'])
    return _model


def _valid_session(value):
    return isinstance(value, str) and len(value) == 32 and all(c in '0123456789abcdef' for c in value)


def handle(handler):
    origin = urlsplit(handler.headers.get('Origin', ''))
    if (origin.scheme != 'http' or origin.netloc != handler.headers.get('Host', '')
            or handler.headers.get('X-Eyazis-Request') != 'lab9'):
        handler.send_json({'error': 'Запрос разрешён только со страницы приложения.'}, 403)
        return
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 12_000:
            raise ValueError('Некорректный размер аудиофрагмента.')
        payload = json.loads(handler.rfile.read(length))
        session_id = payload['session']
        if not _valid_session(session_id):
            raise ValueError('Некорректная сессия распознавания.')
        with _lock:
            now = time.monotonic()
            for key in [key for key, value in _sessions.items() if now - value['time'] > 120]:
                del _sessions[key]
            if payload.get('end') is True:
                _sessions.pop(session_id, None)
                handler.send_json({'closed': True})
                return
            raw = base64.b64decode(payload['audio'], validate=True)
            if len(raw) != 4096:
                raise ValueError('Для Silero нужен блок 2048 отсчётов PCM16.')
            import numpy as np
            if session_id not in _sessions:
                if len(_sessions) >= 32:
                    raise ValueError('Слишком много сессий микрофона.')
                _sessions[session_id] = {'h': np.zeros((1, 1, 128), np.float32),
                                         'c': np.zeros((1, 1, 128), np.float32),
                                         'context': np.zeros(64, np.float32), 'time': now}
            state = _sessions[session_id]
            samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
            probabilities = []
            model = _get_model()
            for frame in samples.reshape(-1, 512):
                data = np.concatenate((state['context'], frame)).reshape(1, 576)
                output, state['h'], state['c'] = model.run(None, {'input': data, 'h': state['h'], 'c': state['c']})
                state['context'] = frame[-64:].copy()
                probabilities.append(float(output.ravel()[0]))
            state['time'] = now
        handler.send_json({'probabilities': probabilities})
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error) as exc:
        handler.send_json({'error': str(exc)}, 400)
    except (ImportError, OSError):
        handler.send_json({'error': 'Silero VAD недоступен. Установите зависимости из lab89/requirements.txt.'}, 503)
    except Exception as exc:
        print('Silero VAD error:', type(exc).__name__, str(exc), flush=True)
        handler.send_json({'error': 'Не удалось обработать аудио через Silero VAD.'}, 500)
