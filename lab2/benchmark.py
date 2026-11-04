"""Reproducible evaluation of the eight distinct bundled HTML documents."""
import json
import platform
import statistics

from lab2.language import Recognizer, ROOT, html_text, sample_files


def evaluate(repeats=10):
    model = Recognizer()
    documents = []
    for item in sample_files():
        html = (ROOT / item['file']).read_text(encoding='utf-8')
        model.analyze(html)  # warm-up; model training is outside timing
        runs = [model.analyze(html) for _ in range(repeats)]
        documents.append({'file': item['file'], 'expected': item['language'],
                          'characters': len(html_text(html)),
                          **{method: runs[0][method] for method in ('ngram', 'alphabet', 'neural', 'overall')},
                          **{method + '_ms': statistics.mean(r[method + '_ms'] for r in runs)
                             for method in ('ngram', 'alphabet', 'neural')}})
    methods = {method: {'correct': sum(d[method] == d['expected'] for d in documents),
                        'accuracy': sum(d[method] == d['expected'] for d in documents) / len(documents),
                        'mean_ms': statistics.mean(d[method + '_ms'] for d in documents)}
               for method in ('ngram', 'alphabet', 'neural')}
    return {'python': platform.python_version(), 'platform': platform.platform(), 'repeats': repeats,
            'training_bytes': {lang: (ROOT / f'train_{lang}.txt').stat().st_size for lang in ('ru', 'de')},
            'documents': documents, 'methods': methods}


if __name__ == '__main__':
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
