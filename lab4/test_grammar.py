"""Check real dependency parsing and the graph API using an isolated database."""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import app
import db
from lab4 import grammar, translation

SENTENCE = ('The railway station looked smaller than she remembered, but the clock '
            'above the entrance still showed the same careful hands.')


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as directory, patch.object(db, 'DB_PATH', Path(directory) / 'test.sqlite3'):
        translation.initialize()
        data = {'model': 'test', 'total': 1, 'translated': 1, 'source': SENTENCE,
                'translation': 'Test', 'words': [],
                'sentences': [{'sentence': SENTENCE, 'tree': 'legacy text',
                               'parser': 'spacy-en_core_web_sm-3.8.0'}]}
        with translation.connect() as connection:
            connection.execute('INSERT INTO lab4_results(id, data) VALUES (1, ?)', (json.dumps(data),))
        yield data


class GrammarGraph(unittest.TestCase):
    def test_second_application_cannot_bind_same_port(self):
        with app.ApplicationServer(('127.0.0.1', 0), app.Handler) as first:
            with self.assertRaises(OSError):
                app.ApplicationServer(first.server_address, app.Handler)

    def test_real_parser_preserves_all_words_and_builds_forest(self):
        result = grammar.parse(SENTENCE + ' She waited.')
        nodes = result['nodes']
        self.assertEqual([node['word'] for node in nodes if node['head'] == 0], ['looked', 'waited'])
        station = next(i for i, node in enumerate(nodes, 1) if node['word'] == 'station')
        self.assertEqual(nodes[nodes[station - 1]['head'] - 1]['word'], 'looked')
        self.assertEqual(nodes[station - 1]['rel'], 'nsubj')
        self.assertIn('hands', [node['word'] for node in nodes])

    def test_tree_http_api_repairs_legacy_cache_and_keeps_text_export(self):
        with fixture():
            server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                request = Request(base + '/translation/tree/1', data=b'index=0')
                with urlopen(request) as response:
                    result = json.load(response)
                self.assertTrue(result['nodes'])
                self.assertIn('looked [VERB, ROOT]', result['tree'])
                self.assertEqual(translation.get(1)['sentences'][0]['nodes'], result['nodes'])
                with patch.object(grammar, 'parse', side_effect=AssertionError('Cache should be used')):
                    self.assertEqual(translation.parse_sentence(1, 0), result['tree'])
                    with urlopen(request) as response:
                        self.assertEqual(json.load(response), result)
                with urlopen(base + '/translation/result/1') as response:
                    html = response.read().decode()
                    self.assertIn('/static/translation-tree.js', html)
                with urlopen(base + '/static/translation-tree.js') as response:
                    self.assertIn('javascript', response.headers['Content-Type'])
                with urlopen(base + '/translation/export/1') as response:
                    self.assertIn(result['tree'], response.read().decode('utf-8-sig'))
                for path, body in [('/translation/tree/1', b'index=999'), ('/translation/tree/999', b'index=0')]:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(base + path, data=body))
                    self.assertEqual(error.exception.code, 400)
                    self.assertIn('error', json.load(error.exception))
                    error.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join()

    def test_embedded_sentence_data_cannot_close_script_tag(self):
        with fixture() as data:
            data['sentences'][0]['sentence'] = '</script><script>alert(1)</script>'
            html = app.translation_result(1, data)
            payload = html.split('<script id="syntax-data" type="application/json">', 1)[1].split('</script>', 1)[0]
            self.assertNotIn('<', payload)
            self.assertEqual(json.loads(payload)['sentences'], data['sentences'])


if __name__ == '__main__':
    unittest.main()
