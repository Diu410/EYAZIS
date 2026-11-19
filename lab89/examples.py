"""Bundled text examples, independent of the checkout location."""
from pathlib import Path

ROOT = Path(__file__).with_name('examples')
EXAMPLES = (
    ('01_recherche.txt', 'Поиск документов', 'fr'),
    ('02_apprentissage.txt', 'Машинное обучение', 'fr'),
    ('03_bases_de_donnees.txt', 'Базы данных', 'fr'),
    ('04_reseaux.txt', 'Компьютерные сети', 'fr'),
    ('05_securite.txt', 'Информационная безопасность', 'fr'),
    ('06_search_ru.txt', 'Поиск документов', 'ru'),
    ('07_search_en.txt', 'Поиск документов', 'en'),
    ('08_search_de.txt', 'Поиск документов', 'de'),
)


def all_examples():
    result = []
    for name, title, language in EXAMPLES:
        try:
            text = (ROOT / name).read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError):
            continue
        if text:
            result.append({'id': name, 'title': title, 'language': language, 'text': text})
    return result
