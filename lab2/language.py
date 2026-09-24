"""Laboratory 2: Russian/German HTML language recognition by three methods."""

from collections import Counter
from html.parser import HTMLParser
from math import exp, sqrt, tanh
from pathlib import Path
import json
import random
import re
import time

from db import connect

ROOT = Path(__file__).with_name("corpus")
LANGS = ("ru", "de")
ALPHABET = "абвгдеёжзийклмнопрстуфхцчшщъыьэюяabcdefghijklmnopqrstuvwxyzäöüß"
FEATURES = len(ALPHABET)
WORD_RE = re.compile(r"[a-zA-ZäöüßА-Яа-яЁё]+")


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_text(html):
    parser = HTMLText()
    parser.feed(html)
    return " ".join(parser.parts)


def vector(text):
    counts = Counter(char for char in text.lower() if char in ALPHABET)
    total = sum(counts.values()) or 1
    return [counts[char] / total for char in ALPHABET]


def ngrams(text, n=5):
    counts = Counter()
    for word in WORD_RE.findall(text.lower()):
        padded = "_" + word + "_"
        for size in range(1, n + 1):
            counts.update(padded[i:i + size] for i in range(len(padded) - size + 1))
    return [gram for gram, _ in counts.most_common(300)]


def out_of_place(profile, reference):
    positions = {gram: i for i, gram in enumerate(reference)}
    penalty = len(reference)
    return sum(abs(i - positions[gram]) if gram in positions else penalty
               for i, gram in enumerate(profile))


def cosine(a, b):
    denominator = sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / denominator if denominator else 0.0


class TinyNetwork:
    """One-hidden-layer neural classifier trained by stochastic gradient descent."""

    def __init__(self, hidden=16):
        rng = random.Random(4)
        self.w1 = [[rng.uniform(-0.4, 0.4) for _ in range(FEATURES)] for _ in range(hidden)]
        self.b1 = [0.0] * hidden
        self.w2 = [[rng.uniform(-0.4, 0.4) for _ in range(hidden)] for _ in LANGS]
        self.b2 = [0.0] * len(LANGS)

    def forward(self, x):
        hidden = [tanh(sum(wi * xi for wi, xi in zip(weights, x)) + bias)
                  for weights, bias in zip(self.w1, self.b1)]
        logits = [sum(wi * hi for wi, hi in zip(weights, hidden)) + bias
                  for weights, bias in zip(self.w2, self.b2)]
        maximum = max(logits)
        exps = [exp(value - maximum) for value in logits]
        total = sum(exps)
        return hidden, [value / total for value in exps]

    def train(self, samples, epochs=60, learning_rate=0.45):
        rng = random.Random(4)
        for _ in range(epochs):
            rng.shuffle(samples)
            for x, target in samples:
                hidden, probability = self.forward(x)
                delta2 = [probability[i] - (1 if i == target else 0) for i in range(len(LANGS))]
                delta1 = [(1 - hidden[j] ** 2) * sum(delta2[i] * self.w2[i][j]
                          for i in range(len(LANGS))) for j in range(len(hidden))]
                for i in range(len(LANGS)):
                    for j in range(len(hidden)):
                        self.w2[i][j] -= learning_rate * delta2[i] * hidden[j]
                    self.b2[i] -= learning_rate * delta2[i]
                for j in range(len(hidden)):
                    for k in range(FEATURES):
                        self.w1[j][k] -= learning_rate * delta1[j] * x[k]
                    self.b1[j] -= learning_rate * delta1[j]

    def predict(self, text):
        _, probabilities = self.forward(vector(text))
        return LANGS[max(range(len(LANGS)), key=lambda i: probabilities[i])], max(probabilities)


class Recognizer:
    def __init__(self):
        training = {}
        for lang in LANGS:
            path = ROOT / f"train_{lang}.txt"
            if not path.exists():
                raise FileNotFoundError("Нет обучающих текстов. Запустите python prepare_corpus.py")
            raw = path.read_text(encoding="utf-8")
            size = path.stat().st_size
            if not 20_000 <= size <= 120_000:
                raise ValueError(f"Обучающий набор {lang} должен иметь размер 20–120 КБ")
            training[lang] = raw
        self.ngram_profiles = {lang: ngrams(text) for lang, text in training.items()}
        self.alphabet_profiles = {lang: vector(text) for lang, text in training.items()}
        samples = []
        for index, lang in enumerate(LANGS):
            text = training[lang]
            for offset in range(0, len(text) - 500, 500):
                samples.append((vector(text[offset:offset + 500]), index))
        self.network = TinyNetwork()
        self.network.train(samples)

    def analyze(self, html):
        text = html_text(html)
        if len(WORD_RE.findall(text)) < 20:
            raise ValueError("Для распознавания нужно не менее 20 слов текста")
        start = time.perf_counter()
        profile = ngrams(text)
        distances = {lang: out_of_place(profile, ref) for lang, ref in self.ngram_profiles.items()}
        ngram_lang = min(distances, key=distances.get)
        ngram_ms = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        char_vector = vector(text)
        similarities = {lang: cosine(char_vector, ref) for lang, ref in self.alphabet_profiles.items()}
        alphabet_lang = max(similarities, key=similarities.get)
        alphabet_ms = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        network_lang, confidence = self.network.predict(text)
        network_ms = (time.perf_counter() - start) * 1000
        votes = Counter((ngram_lang, alphabet_lang, network_lang))
        overall = votes.most_common(1)[0][0]
        return {"ngram": ngram_lang, "alphabet": alphabet_lang, "neural": network_lang,
                "overall": overall, "confidence": confidence,
                "ngram_ms": ngram_ms, "alphabet_ms": alphabet_ms, "neural_ms": network_ms,
                "ngram_distance": distances, "alphabet_similarity": similarities}


def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS language_documents (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            html TEXT NOT NULL,
            text TEXT NOT NULL,
            expected TEXT,
            source_url TEXT,
            ngram TEXT NOT NULL,
            alphabet TEXT NOT NULL,
            neural TEXT NOT NULL,
            overall TEXT NOT NULL,
            ngram_ms REAL NOT NULL,
            alphabet_ms REAL NOT NULL,
            neural_ms REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)


def save_result(filename, html, result, expected="", source_url=""):
    if expected and expected not in LANGS:
        raise ValueError("Ожидаемый язык должен быть ru или de")
    with connect() as db:
        cursor = db.execute("""INSERT INTO language_documents
            (filename, html, text, expected, source_url, ngram, alphabet, neural, overall,
             ngram_ms, alphabet_ms, neural_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (filename, html, html_text(html), expected, source_url, result["ngram"], result["alphabet"],
             result["neural"], result["overall"], result["ngram_ms"], result["alphabet_ms"], result["neural_ms"]))
    return cursor.lastrowid


def all_results():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM language_documents ORDER BY id DESC")]


def get_result(document_id):
    with connect() as db:
        row = db.execute("SELECT * FROM language_documents WHERE id = ?", (document_id,)).fetchone()
    return dict(row) if row else None


def delete_result(document_id):
    with connect() as db:
        db.execute("DELETE FROM language_documents WHERE id = ?", (document_id,))


def sample_files():
    meta = ROOT / "sources.json"
    if not meta.exists():
        return []
    return [item for item in json.loads(meta.read_text(encoding="utf-8")) if item["purpose"] == "test"]
