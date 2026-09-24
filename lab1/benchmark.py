"""Fixed test collection and independent relevance judgments for lab 1."""

from lab1.search import add_document, evaluate, list_documents, normalize_query
from lab1.seed import SAMPLES


CASES = (
    {
        "query": "поиск документов",
        "relevant_titles": (
            "Поисковые системы",
            "Векторная модель поиска",
            "Оценка информационного поиска",
        ),
    },
    {
        "query": "база данных",
        "relevant_titles": ("База данных SQLite",),
    },
    {
        "query": "распознавание языка",
        "relevant_titles": ("Распознавание языка",),
    },
    {
        "query": "нейронные сети",
        "relevant_titles": ("Нейронные сети",),
    },
)


def get_case(query):
    normalized = normalize_query(query)
    return next((case for case in CASES if normalize_query(case["query"]) == normalized), None)


def ensure_collection():
    """Add the bundled documents once and return their IDs by title."""
    existing = {(row["title"], row["body"]): row["id"] for row in list_documents()}
    ids = {}
    for title, body in SAMPLES:
        ids[title] = existing.get((title, body)) or add_document(title, body)
    return ids


def evaluate_case(case):
    ids = ensure_collection()
    relevant_ids = [ids[title] for title in case["relevant_titles"]]
    return evaluate(case["query"], ids.values(), relevant_ids)
