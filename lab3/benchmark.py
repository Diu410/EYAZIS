"""Evaluate against stored editorial labels, without consulting predicted scores."""
from pathlib import Path
from collections import Counter
import argparse
import json
import platform
import re
import statistics
import time

from lab3 import summarize

ROOT = Path(__file__).with_name('corpus')


def metrics(predicted, reference):
    predicted, reference = set(predicted), set(reference)
    correct = len(predicted & reference)
    precision = correct / len(predicted) if predicted else 0.0
    recall = correct / len(reference) if reference else 0.0
    return {'correct': correct, 'predicted': len(predicted), 'reference': len(reference),
            'precision': precision, 'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def rouge_scores(predicted, reference):
    """Word overlap and LCS, case insensitive, without stemming or lemmatization."""
    predicted = re.findall(r"[^\W_]+", predicted.lower())
    reference = re.findall(r"[^\W_]+", reference.lower())
    overlap = sum((Counter(predicted) & Counter(reference)).values())
    previous = [0] * (len(reference) + 1)
    for word in predicted:
        current = [0]
        for index, other in enumerate(reference):
            current.append(previous[index] + 1 if word == other else
                           max(previous[index + 1], current[-1]))
        previous = current

    def score(correct):
        precision = correct / len(predicted) if predicted else 0.0
        recall = correct / len(reference) if reference else 0.0
        return {"precision": precision, "recall": recall,
                "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}

    return {"rouge1": score(overlap), "rougeL": score(previous[-1])}


def evaluate(repeats=10, method="extractive"):
    if repeats < 1:
        raise ValueError("Количество повторов должно быть положительным")
    labels = {item['file']: item for item in json.loads((ROOT / 'reference_annotations.json').read_text(encoding='utf-8'))}
    output = []
    for item in json.loads((ROOT / 'sources.json').read_text(encoding='utf-8')):
        text = (ROOT / item['file']).read_text(encoding='utf-8')
        result = summarize(text, item['language'])  # validate source labels without loading Qwen
        reference = labels[item['file']]
        available = {s['sentence'] for s in result['sentence_scores']}
        if not set(reference['summary_sentences']) <= available:
            raise ValueError(f"Эталонные предложения отсутствуют в документе {item['file']}")
        samples = []
        for _ in range(repeats):
            start = time.perf_counter()
            result = summarize(text, item['language'], subject_area=item['subject_area'], method=method)
            samples.append((time.perf_counter() - start) * 1000)
        output.append({'file': item['file'], 'language': item['language'],
                       'subject_area': item['subject_area'], 'characters': len(text),
                       'sentences': len(result['sentence_scores']), 'chosen': len(result['summary']),
                       'idf_documents': result['idf_document_count'],
                       'method': method, 'model': result.get('model'),
                       'summary': result['summary'], 'generation': result.get('generation'),
                       'summary_metrics': (metrics(result['summary'], reference['summary_sentences'])
                                           if method == 'extractive' else None),
                       'rouge': rouge_scores(' '.join(result['summary']), ' '.join(reference['summary_sentences'])),
                       'keyword_metrics': metrics([k['word'] for k in result['keywords']], reference['keywords']),
                       'reduction': 1 - sum(map(len, result['summary'])) / len(text),
                       'mean_ms': statistics.mean(samples), 'stdev_ms': statistics.stdev(samples) if repeats > 1 else None,
                       'repeats': repeats})
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'method': method,
            'annotation': 'Учебная редакторская разметка, составлена с помощью ИИ до расчёта рангов; не независимая экспертная оценка.',
            'rouge_note': 'ROUGE-1 и ROUGE-L: слова и числа, без учёта регистра, без стемминга. Лексическое сходство с эталоном, не оценка достоверности фактов. Время генерации включает загрузку модели, если она ещё не загружена.',
            'results': output}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Сравнение методов реферирования на RU/DE корпусе")
    parser.add_argument('--method', choices=('extractive', 'generative', 'both'), default='extractive')
    parser.add_argument('--repeats', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    methods = ('extractive', 'generative') if args.method == 'both' else (args.method,)
    evaluations = [evaluate(args.repeats if args.repeats is not None else
                            (1 if method == 'generative' else 10), method) for method in methods]
    payload = {'methods': evaluations} if args.method == 'both' else evaluations[0]
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + '\n', encoding='utf-8')
        print(f'Результаты сохранены: {args.output}')
    else:
        print(output)
