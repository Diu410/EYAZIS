"""Laboratory 1: Russian document indexing, vector search and evaluation."""

from collections import Counter
from html.parser import HTMLParser
from math import log, sqrt
import re
from urllib.request import Request, urlopen
from urllib.parse import quote, urlparse, urlunparse

from db import connect

WORD_RE = re.compile(r"[а-яё]+", re.IGNORECASE)
STOP = set("и в во на по с со к ко у о об от до для при из за над под а но или что как это тот эта эти его ее их мы вы он она они не ни же бы ли есть быть был была было были так также уже еще только очень все весь тут там который которая которые когда где чем чтобы если то".split())


def tokens(text):
    return [word.lower() for word in WORD_RE.findall(text) if word.lower() not in STOP and len(word) > 2]


def normalize_query(query):
    return " ".join(query.lower().split())


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())
            if self.in_title:
                self.title.append(data.strip())


def extract_html(html):
    parser = VisibleText()
    parser.feed(html)
    return " ".join(parser.title), "\n".join(parser.parts)


def fetch_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Нужен адрес http:// или https://")
    safe_url = urlunparse(parsed._replace(path=quote(parsed.path, safe="/%:@"),
                                         query=quote(parsed.query, safe="=&%/?+:;,@")))
    request = Request(safe_url, headers={"User-Agent": "EYAZIS-Lab/1.0 (educational local importer)"})
    with urlopen(request, timeout=12) as response:
        if "html" not in response.headers.get_content_type():
            raise ValueError("Адрес должен вести на HTML-страницу")
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Страница больше 2 МБ")
        charset = response.headers.get_content_charset() or "utf-8"
    return extract_html(data.decode(charset, errors="replace"))


def add_document(title, body, source_url=""):
    title, body = title.strip(), body.strip()
    if not title or not body:
        raise ValueError("Укажите заголовок и текст документа")
    counts = Counter(tokens(title + " " + body))
    if not counts:
        raise ValueError("В тексте нет русских ключевых слов")
    with connect() as db:
        cursor = db.execute("INSERT INTO documents(title, body, source_url) VALUES (?, ?, ?)", (title, body, source_url.strip()))
        document_id = cursor.lastrowid
        db.executemany("INSERT INTO terms(document_id, term, frequency) VALUES (?, ?, ?)",
                       [(document_id, term, count) for term, count in counts.items()])
    return document_id


def delete_document(document_id):
    with connect() as db:
        db.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def list_documents():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM documents ORDER BY id DESC")]


def get_document(document_id):
    with connect() as db:
        row = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    return dict(row) if row else None


def search(query, document_ids=None):
    words = set(tokens(query))
    if not words:
        return []
    with connect() as db:
        docs = [dict(row) for row in db.execute("SELECT * FROM documents")]
        rows = list(db.execute("SELECT document_id, term, frequency FROM terms"))
    if document_ids is not None:
        allowed_ids = set(document_ids)
        docs = [doc for doc in docs if doc["id"] in allowed_ids]
    if not docs:
        return []
    document_terms = {doc["id"]: {} for doc in docs}
    document_frequency = Counter()
    for row in rows:
        if row["document_id"] not in document_terms:
            continue
        document_terms[row["document_id"]][row["term"]] = row["frequency"]
        document_frequency[row["term"]] += 1
    total = len(docs)
    # Formula 1.6: A_ij = Q_ij * log(N/P_i); query weights are binary.
    query_norm = sqrt(len(words))
    results = []
    for doc in docs:
        frequencies = document_terms[doc["id"]]
        matched = sorted(words & frequencies.keys())
        if not matched:
            continue
        weights = {term: tf * log(total / document_frequency[term])
                   for term, tf in frequencies.items()}
        norm = sqrt(sum(weight * weight for weight in weights.values()))
        rank = sum(weights[term] for term in matched) / (norm * query_norm) if norm else 0.0
        results.append({**doc, "rank": rank, "matched": matched,
                        "snippet": doc["body"][:300]})
    return sorted(results, key=lambda result: (-result["rank"], result["id"]))


def evaluate(query, document_ids, relevant_ids):
    """Evaluate ranking against supplied relevance labels."""
    document_ids = set(document_ids)
    relevant_ids = set(relevant_ids)
    if not relevant_ids <= document_ids:
        raise ValueError("Эталон содержит документы вне тестовой коллекции")
    ranked = search(query, document_ids=document_ids)
    labels = {document_id: document_id in relevant_ids for document_id in document_ids}
    relevant_total = sum(labels.values())
    points = []
    correct = 0
    precision_sum = 0.0
    for position, result in enumerate(ranked, 1):
        if labels.get(result["id"], False):
            correct += 1
            precision_sum += correct / position
        points.append({"rank": position, "precision": correct / position,
                       "recall": correct / relevant_total if relevant_total else 0.0,
                       "relevant": labels.get(result["id"])})
    count = len(ranked)
    precision = correct / count if count else 0.0
    recall = correct / relevant_total if relevant_total else 0.0
    p10 = sum(bool(labels.get(item["id"])) for item in ranked[:10]) / 10
    ap = precision_sum / relevant_total if relevant_total else 0.0
    r_precision = (sum(bool(labels.get(item["id"])) for item in ranked[:relevant_total]) / relevant_total
                   if relevant_total else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    interpolated = ([{"recall": threshold / 10,
                      "precision": max((point["precision"] for point in points
                                        if point["recall"] >= threshold / 10), default=0.0)}
                     for threshold in range(11)] if relevant_total else [])
    return {"ranked": ranked, "labels": labels, "points": points, "relevant_total": relevant_total,
            "judged": len(labels), "precision": precision, "recall": recall, "f1": f1,
            "p10": p10, "ap": ap, "r_precision": r_precision, "interpolated": interpolated}


def estimate_relevant_ids(query, documents):
    """Create provisional labels from query-word coverage, never from rank scores.

    This is a proxy for a user-defined query, not independent ground truth.
    All documents with the largest positive number of matching query terms
    are treated as relevant.
    """
    words = set(tokens(query))
    if not words:
        return set()
    coverage = {doc["id"]: len(words & set(tokens(doc["title"] + " " + doc["body"])))
                for doc in documents}
    best = max(coverage.values(), default=0)
    return {document_id for document_id, count in coverage.items()
            if count == best and best > 0}
