"""Download reproducible public text samples from Wikipedia's plain-text API."""

from html import escape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re
import time
from urllib.error import HTTPError

ROOT = Path(__file__).with_name("corpus")
TRAIN = {
    "ru": ["Информатика", "Алгоритм", "База данных", "Литература"],
    "de": ["Informatik", "Algorithmus", "Datenbank", "Literatur"],
}
TEST = {
    "ru": ["Машинное обучение", "Роман", "Программирование", "Поэзия"],
    "de": ["Maschinelles Lernen", "Roman", "Programmierung", "Lyrik"],
}


def article(language, title):
    query = urlencode({"action": "query", "prop": "extracts", "explaintext": "1",
                       "titles": title, "format": "json"})
    url = f"https://{language}.wikipedia.org/w/api.php?{query}"
    request = Request(url, headers={"User-Agent": "EYAZIS/1.0 (educational text corpus)"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=20) as response:
                pages = json.load(response)["query"]["pages"]
            break
        except HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    text = next(iter(pages.values())).get("extract", "")
    text = re.sub(r"(?m)^=+.*?=+\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 3000:
        raise ValueError(f"Слишком короткая статья: {language}:{title}")
    return text


def main():
    ROOT.mkdir(exist_ok=True)
    sources = []
    for lang, titles in TRAIN.items():
        if (ROOT / f"train_{lang}.txt").exists():
            for title in titles:
                sources.append({"purpose": "training", "language": lang, "title": title,
                                "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"})
            continue
        pieces = []
        for title in titles:
            body = article(lang, title)
            pieces.append(body)
            time.sleep(1)
            sources.append({"purpose": "training", "language": lang, "title": title,
                            "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"})
        # Stay inside the required 20–120 KB range per language.
        text = "\n\n".join(pieces).encode("utf-8")[:100_000].decode("utf-8", errors="ignore")
        if not 20_000 <= len(text.encode("utf-8")) <= 120_000:
            raise ValueError(f"Размер корпуса {lang} вне диапазона")
        (ROOT / f"train_{lang}.txt").write_text(text, encoding="utf-8")
    for lang, titles in TEST.items():
        for index, title in enumerate(titles, 1):
            filename = f"test_{lang}_{index}.html"
            source_url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
            if (ROOT / filename).exists():
                sources.append({"purpose": "test", "language": lang, "title": title,
                                "file": filename, "url": source_url})
                continue
            body = article(lang, title)
            time.sleep(1)
            # Equal-sized input texts, roughly one A4 page.
            excerpt = body[:3000]
            html = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
                    f'<title>{escape(title)}</title></head><body><main><p>{escape(excerpt)}</p></main></body></html>')
            (ROOT / filename).write_text(html, encoding="utf-8")
            sources.append({"purpose": "test", "language": lang, "title": title,
                            "file": filename, "url": source_url})
    (ROOT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Подготовлены обучающие корпуса и 8 HTML-документов из Wikipedia.")


if __name__ == "__main__":
    main()
