"""Regression tests for corrected requirements of labs 2 and 3 only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from html import unescape
import gc
import json
import math
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import app
import db
from lab2.language import html_text, sample_files, ROOT as LANGUAGE_ROOT
from lab3 import storage
from lab3.summarizer import _sentences, summarize
from lab3.prepare_corpus import ROOT, equal_length_text


class LanguageInput(unittest.TestCase):
    def test_head_scripts_templates_do_not_influence_language(self):
        self.assertEqual(html_text('<head><title>Other language</title></head><body><p>Hallo Welt.</p><script>bad</script><template>bad</template></body>'), 'Hallo Welt.')

    def test_all_eight_inputs_are_exactly_equal(self):
        sizes = [len(html_text((LANGUAGE_ROOT / item['file']).read_text(encoding='utf-8'))) for item in sample_files()]
        self.assertEqual(sizes, [3000] * 8)


class Summarization(unittest.TestCase):
    def test_sentence_boundaries_preserve_decimal_abbreviations_and_quotes(self):
        cases = {
            'В версии 3.14 алгоритм изменён. Это итог.': ['В версии 3.14 алгоритм изменён.', 'Это итог.'],
            'Das ist z. B. ein Algorithmus. Er funktioniert.': ['Das ist z. B. ein Algorithmus.', 'Er funktioniert.'],
            'Im 17. Jahrhundert erschien das Buch. Es blieb wichtig.': ['Im 17. Jahrhundert erschien das Buch.', 'Es blieb wichtig.'],
            'А. С. Пушкин написал роман. Это факт.': ['А. С. Пушкин написал роман.', 'Это факт.'],
            'Он сказал: «Это итог». Далее текст.': ['Он сказал: «Это итог».', 'Далее текст.'],
            'Полное предложение. Оборванное сло': ['Полное предложение.'],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                sentences = _sentences(text)
                self.assertEqual([s['sentence'] for s in sentences], expected)
                for s in sentences:
                    self.assertEqual(text[s['start']:s['start'] + len(s['sentence'])], s['sentence'])

    def test_idf_counts_documents_and_is_independent_of_paragraph_breaks(self):
        text = 'Алгоритм ищет документы. Поиск находит ответ. Алгоритм завершён.'
        reference = ['Литература раскрывает характер героя.']
        one = summarize(text, reference_documents=reference)
        two = summarize(text.replace(' Поиск', '\n\nПоиск'), reference_documents=reference)
        self.assertEqual(one['idf_document_count'], 2)
        self.assertEqual(one['keywords'], two['keywords'])
        weights = {k['word']: k['weight'] for k in one['keywords']}
        self.assertAlmostEqual(weights['алгоритм'], math.log(2))
        self.assertAlmostEqual(weights['документы'], .75 * math.log(2))
        duplicate = summarize(text, reference_documents=[text, *reference, reference[0]])
        self.assertEqual(one['keywords'], duplicate['keywords'])

    def test_order_and_sentence_weights_follow_formula(self):
        text = 'Алгоритм обрабатывает данные.\n\nДокументы содержат данные. Алгоритм завершён.'
        r = summarize(text, reference_documents=['Литература раскрывает характер.'], max_sentences=2)
        scores = r['sentence_scores']
        chosen = sorted(sorted(scores, key=lambda s: (-s['score'], s['index']))[:2], key=lambda s: s['index'])
        self.assertEqual(r['summary'], [s['sentence'] for s in chosen])
        for score in scores:
            self.assertAlmostEqual(score['score'], score['lexical_score'] * score['position_document'] * score['position_paragraph'])

    def test_corpus_is_complete_equal_and_reproducible(self):
        for item in json.loads((ROOT / 'documents.json').read_text(encoding='utf-8')):
            text = (ROOT / item['file']).read_text(encoding='utf-8')
            self.assertEqual(text, equal_length_text(item))
            self.assertEqual(len(text), 4500)
            self.assertTrue(text.endswith('.'))
            self.assertEqual(text, (ROOT.parent / 'examples' / item['file']).read_text(encoding='utf-8'))
            result = summarize(text, item['language'])
            self.assertEqual(result['idf_document_count'], 2)
            self.assertEqual(len(result['summary']), 10)


class SourceAndExports(unittest.TestCase):
    def test_saved_source_is_available_without_external_url(self):
        original = db.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            db.DB_PATH = Path(tmp) / 'tests.sqlite3'
            storage.initialize()
            server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            text = 'Алгоритм обрабатывает данные.\n\nДокументы содержат <важные> данные.'
            try:
                req = Request(base + '/summary/create', data=urlencode({'document':text, 'language':'ru'}).encode())
                with urlopen(req) as response:
                    result_html = response.read().decode()
                    summary_id = int(response.url.rsplit('/', 1)[1])
                source = f'/summary/source/{summary_id}'
                self.assertIn(f'href="{source}"', result_html)
                with urlopen(base + source) as response:
                    source_html = response.read().decode()
                    self.assertIn(text, unescape(source_html))
                    self.assertNotIn('<важные>', source_html)
                with urlopen(base + f'/summary/export/{summary_id}.json') as response:
                    payload = json.load(response)
                    self.assertEqual(payload['document'], text)
                    self.assertEqual(payload['original_document_url'], source)
                with urlopen(base + f'/summary/export/{summary_id}.txt') as response:
                    self.assertIn(source, response.read().decode('utf-8-sig'))
                with self.assertRaises(HTTPError) as missing:
                    urlopen(base + '/summary/source/99999')
                self.assertEqual(missing.exception.code, 404)
                missing.exception.close()
            finally:
                server.shutdown(); server.server_close()
                db.DB_PATH = original
                gc.collect()


if __name__ == '__main__':
    unittest.main()
