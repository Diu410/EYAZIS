"""Local English dependency parsing; no generative model requests."""
import threading
from pathlib import Path

_pipeline = None
_lock = threading.RLock()


def parse(text):
    global _pipeline
    with _lock:
        if _pipeline is None:
            try:
                import spacy
            except ImportError as exc:
                raise ValueError('Для разбора установите зависимости: python -m pip install -r lab4/requirements.txt') from exc
            model = Path(__file__).with_name('models') / 'en_core_web_sm'
            if not (model / 'config.cfg').is_file():
                raise ValueError('Не найдена модель разбора lab4/models/en_core_web_sm.')
            _pipeline = spacy.load(model, exclude=['ner', 'lemmatizer'])
        doc = _pipeline(text)
    tokens = [t for t in doc if not t.is_space]
    ids = {t.i: i for i, t in enumerate(tokens, 1)}
    nodes = [{'head': 0 if t.head.i == t.i else ids[t.head.i],
              'rel': t.dep_, 'word': t.text, 'pos': t.pos_} for t in tokens]
    if not nodes:
        raise ValueError('В предложении нет слов для разбора.')
    # Validate the forest: a source selection can include more than one sentence.
    roots = [i for i, n in enumerate(nodes, 1) if n['head'] == 0]
    if not roots:
        raise ValueError('Анализатор не определил корень.')
    for i in range(1, len(nodes)+1):
        current, seen = i, set()
        while current:
            if current in seen or not 1 <= current <= len(nodes):
                raise ValueError('Анализатор вернул некорректные зависимости.')
            seen.add(current)
            current = nodes[current-1]['head']
    children = {}
    for i, n in enumerate(nodes, 1):
        children.setdefault(n['head'], []).append(i)
    lines, stack = [], [(i, 0) for i in reversed(roots)]
    while stack:
        i, depth = stack.pop()
        n = nodes[i-1]
        lines.append('    '*depth + n['word'] + ' [' + n['pos'] + ', ' + n['rel'] + ']')
        stack.extend((child, depth+1) for child in reversed(children.get(i, [])))
    return {'nodes': nodes, 'tree': '\n'.join(lines), 'parser': 'spacy-en_core_web_sm-3.8.0'}


def parse_saved(result_id, index, *, include_nodes=False):
    from .translation import get, connect
    import json
    data = get(result_id)
    if data is None or not 0 <= index < len(data['sentences']):
        raise ValueError('Предложение не найдено.')
    item = data['sentences'][index]
    if item.get('parser') == 'spacy-en_core_web_sm-3.8.0' and item.get('tree') and item.get('nodes'):
        return {key: item[key] for key in ('tree', 'nodes', 'parser')} if include_nodes else item['tree']
    result = parse(item['sentence'])
    # Reload under the DB write lock to preserve another sentence's cached parse.
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT data FROM lab4_results WHERE id=?', (result_id,)).fetchone()
        if row is None:
            raise ValueError('Результат не найден.')
        latest = json.loads(row['data'])
        latest['sentences'][index].update(result)
        db.execute('UPDATE lab4_results SET data=? WHERE id=?', (json.dumps(latest, ensure_ascii=False), result_id))
    return result if include_nodes else result['tree']
