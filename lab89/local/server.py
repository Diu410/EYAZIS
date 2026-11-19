"""Loopback-only service: Piper CPU synthesis and CTranslate2 GPU transcription."""
import base64
import io
import json
import os
import subprocess
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlretrieve

VOICE = 'fr_FR-siwis-medium'
VOICE_DIR = Path('/models/piper')
MODEL_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/'
lock = threading.Lock()
voice = None
whisper = None


def get_voice():
    global voice
    if voice is None:
        from piper import PiperVoice
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        for suffix in ('.onnx', '.onnx.json'):
            path = VOICE_DIR / (VOICE + suffix)
            if not path.exists():
                tmp = path.with_suffix(path.suffix + '.part')
                urlretrieve(MODEL_URL + path.name, tmp)
                tmp.replace(path)
        voice = PiperVoice.load(str(VOICE_DIR / (VOICE + '.onnx')))
    return voice


def get_whisper():
    global whisper
    if whisper is None:
        from faster_whisper import WhisperModel
        whisper = WhisperModel('turbo', device=os.environ.get('WHISPER_DEVICE', 'cuda'),
                               compute_type=os.environ.get('WHISPER_COMPUTE_TYPE', 'int8_float16'))
    return whisper


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, {'service': 'lab89', 'piper_loaded': voice is not None, 'whisper_loaded': whisper is not None})
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        try:
            if self.headers.get('Origin') or self.headers.get_content_type() != 'application/json':
                self.reply(403, {'error': 'Доступ разрешён только локальному приложению'})
                return
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 14_000_000:
                raise ValueError('Некорректный размер запроса')
            payload = json.loads(self.rfile.read(length))
            with lock:
                if self.path == '/synthesize':
                    from piper import SynthesisConfig
                    text, rate = payload['text'], float(payload['rate'])
                    if not isinstance(text, str) or not text.strip() or len(text) > 6000 or not 0.5 <= rate <= 2:
                        raise ValueError('Некорректный текст или скорость')
                    wav = io.BytesIO()
                    with wave.open(wav, 'wb') as out:
                        get_voice().synthesize_wav(text, out, syn_config=SynthesisConfig(length_scale=1 / rate))
                    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-f', 'mp3', 'pipe:1'], input=wav.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
                    self.reply(200, {'audio': base64.b64encode(result.stdout).decode('ascii')})
                elif self.path == '/transcribe':
                    audio = base64.b64decode(payload['audio'], validate=True)
                    if not audio or len(audio) > 10 * 1024 * 1024:
                        raise ValueError('Некорректный размер аудио')
                    language = payload.get('language', 'fr')
                    if language not in ('fr', 'ru', 'en', 'de'):
                        raise ValueError('Неподдерживаемый язык распознавания')
                    # PyAV detects the format from the data rather than the file name.
                    segments, _ = get_whisper().transcribe(io.BytesIO(audio), language=language, task='transcribe', beam_size=5)
                    self.reply(200, {'text': ' '.join(segment.text.strip() for segment in segments).strip()})
                else:
                    self.reply(404, {'error': 'Not found'})
        except Exception as exc:
            print(f'{type(exc).__name__}: {exc}', flush=True)
            self.reply(500, {'error': f'Ошибка локального сервиса: {exc}'})


ThreadingHTTPServer(('0.0.0.0', 8899), Handler).serve_forever()
