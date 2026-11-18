"""Bundled French text examples, independent of the checkout location."""
from pathlib import Path

ROOT = Path(__file__).with_name('examples')
EXAMPLES = (
    ('01_recherche.txt', 'Поиск документов'),
    ('02_apprentissage.txt', 'Машинное обучение'),
    ('03_bases_de_donnees.txt', 'Базы данных'),
    ('04_reseaux.txt', 'Компьютерные сети'),
    ('05_securite.txt', 'Информационная безопасность'),
)


def all_examples():
    result = []
    for name, title in EXAMPLES:
        try:
            text = (ROOT / name).read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError):
            continue
        if text:
            result.append({'id': name, 'title': title, 'text': text})
    return result
