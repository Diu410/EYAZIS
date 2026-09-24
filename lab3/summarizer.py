"""Extractive summarizer using the formulas from laboratory work 3.

OSTIS is deliberately outside this module. The returned dictionary is the
single result object that a future storage adapter can consume.
"""

from collections import Counter
from math import log
import re


RUSSIAN_WORD = re.compile(r"[А-Яа-яЁё]+")
GERMAN_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]+")
SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)", re.DOTALL)
PARAGRAPH = re.compile(r"\S.*?(?=(?:\r?\n\s*\r?\n)|\Z)", re.DOTALL)

RUSSIAN_STOP = set("""
а без более бы был была были было быть в вам вас весь во вот все всего всей всем всеми
всех всю вы где да даже для до его ее если есть еще же за зачем здесь и из или им
их к как какая какие какой когда кого кому которая которые который кто ли либо мне
может мой мы на над нам нас не него нее нет ни них но о об один она они оно от
перед по под после при про с сам себе себя со так также такой там те тем тех то
того тоже той только тот тут ты у уже хотя чего чем через что чтобы эта эти это
этого этой этом я
""".split())

GERMAN_STOP = set("""
aber als am an auch auf aus bei bin bis bist da dadurch daher darum das dass
dein deine dem den der des die dies diese diesem diesen dieser dieses doch dort du
durch ein eine einem einen einer eines er es für gegen gewesen haben hat hatte
hier hin hinter ich ihr ihre im in ist ja jede jedem jeden jeder jedes jene jenem
jenen jener jenes jetzt kann kein keine mit muss nach nicht noch nun oder ohne sehr
sein seine sich sie sind so soll und unser unsere unter vom von vor war waren was
weil weiter welche welchem welchen welcher welches wenn wer werde werden wie wieder
wir wird wo zu zum zur über
""".split())


def _tokens(text: str, language: str) -> list[str]:
    if language == "ru":
        pattern, stop = RUSSIAN_WORD, RUSSIAN_STOP
    elif language == "de":
        pattern, stop = GERMAN_WORD, GERMAN_STOP
    else:
        raise ValueError("Поддерживаются языки ru и de")
    return [word for match in pattern.finditer(text)
            if (word := match.group().lower()) not in stop and len(word) > 1]


def _paragraphs(document: str) -> list[tuple[str, int]]:
    return [(match.group().strip(), match.start())
            for match in PARAGRAPH.finditer(document) if match.group().strip()]


def _sentences(document: str) -> list[dict]:
    result = []
    for paragraph, paragraph_start in _paragraphs(document):
        for match in SENTENCE.finditer(paragraph):
            raw = match.group()
            sentence = raw.strip()
            if not sentence:
                continue
            before = match.start() + len(raw) - len(raw.lstrip())
            result.append({"sentence": sentence, "start": paragraph_start + before,
                           "paragraph_start": before, "paragraph_length": len(paragraph)})
    return result


def _reference_collection(document: str, language: str,
                          reference_documents: list[str] | None) -> list[set[str]]:
    if reference_documents is not None:
        texts = [document, *reference_documents]
    else:
        texts = [paragraph for paragraph, _ in _paragraphs(document)]
        # A document without paragraph breaks still needs an IDF collection.
        if len(texts) == 1:
            texts = [item["sentence"] for item in _sentences(document)]
    return [set(_tokens(text, language)) for text in texts if text.strip()]


def summarize(document: str, language: str = "ru",
              reference_documents: list[str] | None = None,
              max_sentences: int = 10, max_keywords: int = 20,
              subject_area: str | None = None) -> dict:
    """Return an ordered extract and weighted keywords for a Russian/German text.

    TF-IDF is 0.5 * (1 + TF(t,D)/TFmax(D)) * ln(|DB|/DF(t)). If a
    reference collection is supplied, DB consists of the input document plus
    those documents; otherwise its paragraphs (or sentences for a single
    paragraph) serve as document units. Scores follow the lab handout exactly.
    """
    if not isinstance(document, str) or not document.strip():
        raise ValueError("Передайте непустой текст документа")
    if language not in ("ru", "de"):
        raise ValueError("Поддерживаются языки ru и de")
    if max_sentences < 1 or max_keywords < 1:
        raise ValueError("Лимиты предложений и ключевых слов должны быть положительными")
    if reference_documents is not None and not all(isinstance(item, str) for item in reference_documents):
        raise ValueError("Опорная коллекция должна содержать строки")

    sentences = _sentences(document)
    term_counts = Counter(_tokens(document, language))
    collection = _reference_collection(document, language, reference_documents)
    document_frequency = Counter(term for unit in collection for term in unit)
    count_documents = len(collection)
    max_tf = max(term_counts.values(), default=0)

    word_weights = {
        term: 0.5 * (1 + frequency / max_tf) * log(count_documents / document_frequency[term])
        for term, frequency in term_counts.items()
    } if max_tf and count_documents else {}

    scores = []
    document_length = len(document)
    for index, item in enumerate(sentences):
        sentence_tf = Counter(_tokens(item["sentence"], language))
        lexical_score = sum(frequency * word_weights[term]
                            for term, frequency in sentence_tf.items())
        position_document = 1 - item["start"] / document_length
        position_paragraph = 1 - item["paragraph_start"] / item["paragraph_length"]
        score = position_document * position_paragraph * lexical_score
        scores.append({"index": index, "sentence": item["sentence"],
                       "score": score, "lexical_score": lexical_score,
                       "position_document": position_document,
                       "position_paragraph": position_paragraph})

    chosen = sorted(sorted(scores, key=lambda item: (-item["score"], item["index"]))[:max_sentences],
                    key=lambda item: item["index"])
    keywords = sorted(word_weights.items(), key=lambda item: (-item[1], item[0]))[:max_keywords]
    result = {
        "document": document,
        "summary": [item["sentence"] for item in chosen],
        "keywords": [{"word": word, "weight": weight} for word, weight in keywords],
        "sentence_scores": scores,
        "language": language,
    }
    if subject_area:
        result["subject_area"] = subject_area
    return result
