"""Persistent local MP3 collection shared by labs 8 and 9."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).with_name('recordings')


def save(audio, text, voice, rate, title='', source=''):
    ROOT.mkdir(exist_ok=True)
    ident = uuid4().hex
    meta = {'id': ident, 'title': str(title).strip()[:150] or text[:75], 'text': text,
            'voice': voice, 'rate': rate, 'source': source, 'created_at': datetime.now(timezone.utc).isoformat()}
    (ROOT / (ident + '.mp3')).write_bytes(audio)
    (ROOT / (ident + '.json')).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return meta


def all_recordings():
    if not ROOT.exists():
        return []
    result = []
    for path in ROOT.glob('*.json'):
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
            ident = item.get('id', '')
            if path.stem == ident and len(ident) == 32 and all(c in '0123456789abcdef' for c in ident) and (ROOT / (ident + '.mp3')).is_file():
                result.append(item)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return sorted(result, key=lambda item: item.get('created_at', ''), reverse=True)


def audio_path(ident):
    if len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
        raise ValueError('Неверный идентификатор записи.')
    path = ROOT / (ident + '.mp3')
    if not path.is_file():
        raise ValueError('Запись не найдена.')
    return path
