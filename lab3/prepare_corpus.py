"""Prepare four equal-length text examples for the variant 4 summary screen."""

import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).with_name("corpus")
TARGET_CHARACTERS = 20_000
TOPICS = [
    ("ru", "computer science", "Информатика", ["Информатика", "Алгоритм"]),
    ("ru", "литература", "Литература", ["Литература", "Роман"]),
    ("de", "computer science", "Informatik", ["Informatik", "Algorithmus"]),
    ("de", "литература", "Literatur", ["Literatur", "Roman"]),
]


def fetch_extract(language, title):
    query = urlencode({"action": "query", "prop": "extracts", "explaintext": "1",
                       "titles": title, "format": "json"})
    request = Request(f"https://{language}.wikipedia.org/w/api.php?{query}",
                      headers={"User-Agent": "EYAZIS/1.0 (educational summary corpus)"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=20) as response:
                pages = json.load(response)["query"]["pages"]
            text = next(iter(pages.values())).get("extract", "")
            return re.sub(r"(?m)^=+.*?=+\s*$", "", text).strip()
        except HTTPError as error:
            if error.code != 429 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def main():
    ROOT.mkdir(exist_ok=True)
    metadata = []
    for language, subject_area, title, articles in TOPICS:
        filename = f"sample_{language}_{'computer_science' if subject_area == 'computer science' else 'literature'}.txt"
        path = ROOT / filename
        urls = [f"https://{language}.wikipedia.org/wiki/{article.replace(' ', '_')}"
                for article in articles]
        if not path.exists():
            pieces = []
            for article in articles:
                pieces.append(fetch_extract(language, article))
                if len("\n\n".join(pieces)) >= TARGET_CHARACTERS:
                    break
                time.sleep(1)
            text = "\n\n".join(pieces)
            if len(text) < TARGET_CHARACTERS:
                raise ValueError(f"Слишком короткий источник: {language} / {subject_area}")
            path.write_text(text[:TARGET_CHARACTERS], encoding="utf-8")
        metadata.append({"file": filename, "language": language,
                         "subject_area": subject_area, "title": title,
                         "source_urls": urls})
    (ROOT / "sources.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print("Подготовлены четыре документа по 20 000 символов.")


if __name__ == "__main__":
    main()
