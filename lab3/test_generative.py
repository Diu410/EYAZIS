"""Protocol, failure, migration and HTTP checks without requiring a loaded model."""

from contextlib import closing, contextmanager
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import app
import db
from lab3 import GenerativeError, generative, storage, summarize


SOURCE = "Алгоритм последовательно обрабатывает данные. Проверка подтвердила правильность результата."
PARAPHRASE = "Проверенный алгоритм корректно выполняет обработку данных."


def reply(text=PARAPHRASE, **fields):
    return BytesIO(json.dumps({"done": True, "done_reason": "stop",
                              "message": {"content": text},
                              **fields}).encode())


@contextmanager
def isolated_database():
    previous = db.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        db.DB_PATH = Path(directory) / "test.sqlite3"
        try:
            yield
        finally:
            db.DB_PATH = previous


class Generation(unittest.TestCase):
    def test_local_model_paraphrases_and_keeps_source_analysis(self):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "qwen3.5:4b"}), \
             patch.object(generative, "urlopen", return_value=reply()) as transport:
            result = summarize(SOURCE, method="generative", max_sentences=2)
        request = transport.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], "qwen3.5:4b")
        self.assertFalse(body["think"])
        self.assertFalse(body["stream"])
        self.assertEqual(json.loads(body["messages"][1]["content"])["source"], SOURCE)
        self.assertEqual(result["summary"], [PARAPHRASE])
        self.assertNotIn(PARAPHRASE, SOURCE)
        self.assertEqual(result["document"], SOURCE)
        self.assertEqual(result["keywords"], summarize(SOURCE)["keywords"])
        self.assertEqual(result["method"], "generative")

    def test_failed_or_truncated_responses_are_never_extractive_fallbacks(self):
        for response in (reply(done_reason="length"), reply(text="Оборванный текст"),
                         BytesIO(b'{"done":true,"message":{"content":"invalid"}}'),
                         BytesIO(b'invalid'), reply(text=""), reply(text="Первый итог. Второй итог.")):
            with self.subTest(response=response), \
                 patch.object(generative, "urlopen", return_value=response), \
                 self.assertRaises(GenerativeError):
                summarize(SOURCE, method="generative", max_sentences=1)
        for error in (URLError("connection refused"), TimeoutError(),
                      HTTPError("http://localhost", 404, "missing model", {}, BytesIO())):
            with self.subTest(error=error), patch.object(generative, "urlopen", side_effect=error), \
                 self.assertRaises(GenerativeError):
                summarize(SOURCE, method="generative")

    def test_long_document_covers_all_source_fragments_before_final_summary(self):
        text = "Алгоритм обрабатывает данные.\n\n" * 300
        sources = []
        def respond(request, **kwargs):
            sources.append(json.loads(json.loads(request.data)["messages"][1]["content"])["source"])
            return reply()
        with patch.object(generative, "urlopen", side_effect=respond):
            result = summarize(text, method="generative")
        self.assertEqual("".join(sources[:-1]), text)
        self.assertEqual(result["generation"]["strategy"], "map_reduce")
        self.assertEqual(result["generation"]["requests"], len(sources))
        self.assertEqual(result["document"], text)

    def test_excess_sentences_are_rewritten_by_the_model(self):
        with patch.object(generative, "urlopen", side_effect=[
                reply(text="Обработка выполнена. Результат проверен."), reply()]):
            result = summarize(SOURCE, method="generative", max_sentences=1)
        self.assertEqual(result["summary"], [PARAPHRASE])
        self.assertEqual(result["generation"]["requests"], 2)


class Persistence(unittest.TestCase):
    def test_migration_keeps_old_results_and_is_repeatable(self):
        result = summarize(SOURCE)
        result.pop("method")  # Existing results predate the method field.
        with isolated_database():
            with closing(db.connect()) as connection, connection:
                connection.execute("""CREATE TABLE summaries (
                    id INTEGER PRIMARY KEY, title TEXT, source_url TEXT, result_json TEXT,
                    ostis_saved INTEGER, created_at TEXT)""")
                connection.execute("INSERT INTO summaries VALUES (7, 'old', '', ?, 1, '2026-01-01')",
                                   (json.dumps(result),))
            storage.initialize()
            storage.initialize()
            self.assertEqual(storage.get(7)["result"], result)
            self.assertEqual(storage.get(7)["created_at"], "2026-01-01")
            self.assertEqual(storage.all_summaries()[0]["method"], "extractive")
            with closing(db.connect()) as connection:
                self.assertNotIn("ostis_saved", {row["name"] for row in connection.execute("PRAGMA table_info(summaries)")})
            self.assertIn("Классический реферат", app.summary_result_page(7))

    def test_http_generation_exports_and_errors_preserve_inputs(self):
        with isolated_database():
            storage.initialize()
            server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_port}"
            form = {"document": SOURCE, "title": "Проверка <модели>", "language": "ru",
                    "method": "generative", "max_sentences": "2"}
            try:
                request = Request(base + "/summary/create", data=urlencode(form).encode())
                with patch.object(generative, "urlopen", return_value=reply()), urlopen(request) as response:
                    html = response.read().decode()
                    summary_id = int(response.url.rsplit("/", 1)[-1])
                self.assertIn("Генеративный реферат", html)
                self.assertIn(PARAPHRASE, html)
                self.assertNotIn("OSTIS", html)
                with urlopen(base + f"/summary/export/{summary_id}.json") as response:
                    result = json.load(response)
                    self.assertEqual(result["method"], "generative")
                    self.assertEqual(result["document"], SOURCE)
                    self.assertEqual(result["model"], "qwen3.5:4b")
                with urlopen(base + f"/summary/export/{summary_id}.txt") as response:
                    self.assertIn("Генеративный реферат", response.read().decode("utf-8-sig"))
                with patch.object(generative, "urlopen", side_effect=URLError("offline")):
                    try:
                        urlopen(request)
                        self.fail("Unavailable model must return an error")
                    except HTTPError as error:
                        self.assertEqual(error.code, 503)
                        html = error.read().decode()
                        error.close()
                self.assertIn(SOURCE, html)
                self.assertIn("Проверка &lt;модели&gt;", html)
                self.assertIn('value="generative" selected', html)
                self.assertEqual(len(storage.all_summaries()), 1)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
