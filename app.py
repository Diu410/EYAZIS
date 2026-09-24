"""Local web interface for the EYAZIS laboratory work."""

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse
import argparse
import csv
import io
import json
from pathlib import Path

from db import initialize
from lab1 import search as lab1
from lab1 import benchmark as lab1_benchmark
from lab2 import language as lab2
from lab3 import summarize, save_to_ostis
from lab3 import storage as lab3_store
from lab3.prepare_corpus import ROOT as SUMMARY_CORPUS_ROOT

recognizer = None


def language_recognizer():
    global recognizer
    if recognizer is None:
        recognizer = lab2.Recognizer()
    return recognizer


def h(value):
    return escape(str(value), quote=True)


def page(title, content, active="home"):
    groups = [
        ("Рабочее место", [("home", "Обзор", "/")]),
        ("Лабораторная 1", [("search", "Поиск", "/search"),
                              ("documents", "Документы", "/documents"),
                              ("metrics", "Оценка поиска", "/metrics")]),
        ("Лабораторная 2", [("language", "Язык текста", "/language")]),
        ("Лабораторная 3", [("summary", "Реферирование", "/summary")]),
        ("Справка", [("help", "Помощь", "/help")]),
    ]
    links = "".join(
        f'<div class="nav-group"><div class="nav-label">{label}</div>' +
        "".join(f'<a class="nav-link {"active" if active == key else ""}" href="{path}">{name}</a>'
                for key, name, path in items) + '</div>'
        for label, items in groups
    )
    section = {"home": "Обзор", "search": "Лабораторная 1", "documents": "Лабораторная 1",
               "metrics": "Лабораторная 1", "language": "Лабораторная 2",
               "summary": "Лабораторная 3", "help": "Справка"}.get(active, "Рабочее место")
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)} — EYAZIS</title><link rel="stylesheet" href="/static/style.css"></head>
<body><header class="topbar"><div class="wrap topbar-inner"><a class="brand" href="/">EYAZIS<span class="brand-dot">.</span></a>
<span class="topbar-caption">Информационный поиск и обработка текста</span><span class="variant">Вариант 4</span></div></header>
<div class="wrap layout"><nav aria-label="Разделы приложения">{links}</nav>
<main><div class="page-heading"><span class="eyebrow">{section}</span><h1>{h(title)}</h1></div>{content}</main></div></body></html>'''


def home_page():
    document_count = len(lab1.list_documents())
    language_count = len(lab2.all_results())
    summary_count = len(lab3_store.all_summaries())
    content = f'''<p class="lead">Три лабораторные работы в одном локальном приложении. Данные поиска, распознавания языка и рефераты доступны из бокового меню.</p>
<div class="overview-grid">
<a class="overview-card" href="/search"><span class="work-number">01 / Информационный поиск</span><strong>Поиск документов</strong>
<span>Векторная модель, TF·IDF и оценка качества выдачи.</span><em>{document_count} документов →</em></a>
<a class="overview-card" href="/language"><span class="work-number">02 / Анализ текста</span><strong>Распознавание языка</strong>
<span>Русский и немецкий HTML: N-граммы, алфавит, нейросеть.</span><em>{language_count} результатов →</em></a>
<a class="overview-card" href="/summary"><span class="work-number">03 / Реферирование</span><strong>Реферат документа</strong>
<span>Предложения, ключевые слова, веса и необязательная запись в OSTIS.</span><em>{summary_count} рефератов →</em></a>
</div><div class="card"><h2>Как работать</h2><p>Выберите раздел слева. Из документов первых двух работ можно сразу перейти к реферированию. Каждый результат третьей работы сохраняется в SQLite и доступен для печати или скачивания.</p></div>'''
    return page("Лабораторные работы", content, "home")


def error_page(message):
    return page("Ошибка", f'<div class="alert">{h(message)}</div><p><a href="/">На главную</a></p>')


def search_page(query=""):
    form = f'''<p class="lead">Поиск по русскоязычным документам. Добавьте текст или импортируйте страницу из интернета.</p>
<form method="get" action="/search" class="row"><input name="q" value="{h(query)}" placeholder="Введите запрос на русском языке" required autofocus>
<button>Найти</button></form>'''
    if not query:
        return page("Поиск документов", form + '<p class="muted">Откройте «Документы», чтобы добавить первые материалы.</p>', "search")
    results = lab1.search(query)
    cards = [f'<p class="muted">Найдено: {len(results)}</p>']
    for result in results:
        source = (f' · <a href="{h(result["source_url"])}" target="_blank" rel="noopener">Исходная страница ↗</a>'
                  if result["source_url"] else "")
        cards.append(f'''<article class="card"><h2><a href="/document/{result["id"]}">{h(result["title"])}</a></h2>
<p>{h(result["snippet"])}</p><p class="muted">Совпали слова: {h(", ".join(result["matched"]))} · Релевантность: {result["rank"]:.3f}{source}</p></article>''')
    cards.append('<p><a href="/metrics">Оценить качество поиска на тестовой коллекции →</a></p>')
    return page("Поиск документов", form + "".join(cards), "search")


def documents_page():
    documents = lab1.list_documents()
    cards = "".join(f'''<article class="card"><h2><a href="/document/{doc["id"]}">{h(doc["title"])}</a></h2>
<p>{h(doc["body"][:180])}...</p><span class="muted">Добавлен: {h(doc["added_at"])}</span>
<form method="post" action="/delete" onsubmit="return confirm('Удалить документ?')" class="delete-form">
<input type="hidden" name="id" value="{doc["id"]}"><button class="danger small">Удалить</button></form></article>'''
                    for doc in documents)
    return page("Документы", '''<h2>Импорт интернет-страницы</h2>
<form method="post" action="/import" class="row"><input name="url" type="url" placeholder="https://example.org/page" required><button>Импортировать</button></form>
<h2>Добавить текст</h2><form method="post" action="/documents"><label>Заголовок<input name="title" required></label>
<label>Адрес источника, если есть<input name="source_url" type="url"></label>
<label>Выбрать пример или свой TXT-файл<input id="document-file" type="file" accept=".txt,.md,text/plain"></label>
<label>Текст<textarea name="body" rows="8" required></textarea></label><button>Добавить документ</button></form>
<script>document.getElementById('document-file').addEventListener('change',async e=>{const file=e.target.files[0];
if(file){document.querySelector('[name=body]').value=await file.text();
const title=document.querySelector('[name=title]');if(!title.value)title.value=file.name.replace(/\\.[^.]+$/,'');}})</script>
<h2>Коллекция</h2>''' + (cards or '<p class="muted">Документов пока нет.</p>'), "documents")


def document_page(document_id):
    doc = lab1.get_document(document_id)
    if not doc:
        return error_page("Документ не найден")
    source = (f'<p>Источник: <a href="{h(doc["source_url"])}" target="_blank" rel="noopener">{h(doc["source_url"])}</a></p>'
              if doc["source_url"] else "")
    body = "<br>".join(h(line) for line in doc["body"].splitlines())
    return page(doc["title"], source + f'<p><a class="button-link" href="/summary?from_search={document_id}">Реферировать документ →</a></p>'
                + f'<article class="card prose">{body}</article>'
                + f'<form method="post" action="/delete" onsubmit="return confirm(\'Удалить документ?\')"><input type="hidden" name="id" value="{document_id}"><button class="danger">Удалить документ</button></form>', "documents")


def chart(points):
    if not points:
        return '<p class="muted">График не строится: среди документов нет совпадений со словами запроса.</p>'
    coords = " ".join(f'{40 + item["recall"] * 450:.1f},{220 - item["precision"] * 190:.1f}' for item in points)
    marks = "".join(f'<circle cx="{40 + item["recall"] * 450:.1f}" cy="{220 - item["precision"] * 190:.1f}" r="3.5" fill="#0b7184"/>'
                    for item in points)
    return f'''<svg class="chart" viewBox="0 0 520 250" role="img" aria-label="График точности от полноты">
<path d="M40 30 V220 H490 M40 125 H490 M265 30 V220" fill="none" stroke="#d7e2e6" stroke-width="1"/>
<path d="M40 30 V220 H490" fill="none" stroke="#82909b" stroke-width="2"/>
<polyline points="{coords}" fill="none" stroke="#0b7184" stroke-width="3"/>
{marks}<text x="35" y="239">0</text><text x="252" y="239">0.5</text><text x="482" y="239">1</text>
<text x="14" y="222">0</text><text x="2" y="128">0.5</text><text x="14" y="34">1</text>
<text x="208" y="248">Полнота</text><text x="45" y="20">Точность</text></svg>'''


def metrics_page(query=""):
    query = query.strip() or lab1_benchmark.CASES[0]["query"]
    case = lab1_benchmark.get_case(query)
    options = ''.join(f'<option value="{h(item["query"])}"></option>' for item in lab1_benchmark.CASES)
    form = ('<p class="lead">Введите любой запрос. Для подготовленных запросов используется независимый эталон; '
            'для остальных программа создаёт ориентировочную автооценку по совпадению слов.</p>'
            f'<form method="get" action="/metrics" class="row"><input name="q" list="evaluation-queries" '
            f'value="{h(query)}" required><datalist id="evaluation-queries">{options}</datalist>'
            '<button>Искать и оценить</button></form>')
    if case is None:
        documents = lab1.list_documents()
        document_ids = [doc["id"] for doc in documents]
        relevant_ids = lab1.estimate_relevant_ids(query, documents)
        data = lab1.evaluate(query, document_ids, relevant_ids)
        label_source = "автооценке"
        notice = ('<div class="alert">Ориентировочная оценка: релевантными автоматически считаются документы '
                  'с наибольшим числом совпавших значимых слов запроса. Это не независимая экспертная разметка; '
                  'такие показатели не заменяют оценку качества на эталонной коллекции.</div>')
    else:
        data = lab1_benchmark.evaluate_case(case)
        collection_ids = lab1_benchmark.ensure_collection()
        documents = [doc for doc in lab1.list_documents() if doc["id"] in collection_ids.values()]
        document_ids = list(collection_ids.values())
        label_source = "эталону"
        notice = ''
    stats = [("Точность", data["precision"]), ("Полнота", data["recall"]), ("F1", data["f1"]),
             ("P@10", data["p10"]), ("Средняя точность AP", data["ap"]), ("R-точность", data["r_precision"])]
    table = ('<table><tr><th>Метрика</th><th>Значение</th></tr>' + "".join(
        f'<tr><td>{name}</td><td>{value:.3f}</td></tr>' for name, value in stats) + '</table>'
             if data["relevant_total"] else '<p class="muted">Для запроса нет совпадающих документов; метрики не определены.</p>')
    documents_by_id = {doc["id"]: doc for doc in documents}
    ranked_ids = {result["id"] for result in data["ranked"]}
    ordered = data["ranked"] + [documents_by_id[doc_id] for doc_id in document_ids
                                if doc_id not in ranked_ids]
    reference_rows = ''.join(
        f'<tr><td><a href="/document/{doc["id"]}">{h(doc["title"])}</a></td>'
        f'<td>{doc["rank"]:.3f}</td><td>{"Да" if data["labels"][doc["id"]] else "Нет"}</td></tr>'
        if "rank" in doc else
        f'<tr><td><a href="/document/{doc["id"]}">{h(doc["title"])}</a></td>'
        f'<td>Не найден</td><td>{"Да" if data["labels"][doc["id"]] else "Нет"}</td></tr>'
        for doc in ordered)
    note = (f'<p class="muted">Запрос: <strong>{h(case["query"] if case else query)}</strong>. '
            f'Документов: {data["judged"]}; релевантных по {label_source}: {data["relevant_total"]}. '
            'Сходство вычисляется векторным поиском, оценки — по указанной разметке.</p>')
    metric_title = 'Метрики поиска по эталону' if case else 'Ориентировочные метрики поиска'
    graph_title = ('11-точечный график точности и полноты по эталону' if case else
                   '11-точечный график по автоматической оценке релевантности')
    results = (f'<h2>{metric_title}</h2>' + table + f'<h2>{graph_title}</h2>'
               + chart(data["interpolated"]) + '<h2>Документы и оценки релевантности</h2>'
               + '<div class="table-scroll"><table><tr><th>Документ</th><th>Сходство с запросом</th>'
               f'<th>Релевантен по {label_source}</th></tr>' + reference_rows + '</table></div>')
    return page("Оценка поиска", form + notice + note + results, "metrics")


def help_page():
    return page("Помощь", '''<h2>Лабораторная 1 — поиск</h2><ol>
<li>Добавьте русскоязычные тексты через форму или URL HTML-страницы.</li>
<li>Введите естественно-языковой запрос. Поиск использует веса TF·IDF и косинусную близость.</li>
<li>Откройте «Оценка поиска»: можно ввести любой запрос. Для подготовленных запросов график строится по эталону, для остальных — по ориентировочной автоматической оценке совпадения слов.</li></ol>
<h2>Лабораторная 2 — язык текста</h2><ol><li>Выберите собственные HTML-файлы или примеры из папки lab2/examples.</li>
<li>Для оценки точности укажите известный язык. Просмотрите результаты каждого метода и среднее время.</li>
<li>Сохраните CSV или нажмите «Распечатать».</li></ol>
<h2>Лабораторная 3 — реферирование</h2><ol><li>Откройте «Реферирование» и вставьте текст либо загрузите TXT-файл. Можно начать со страницы документа первой или второй работы.</li>
<li>Выберите русский или немецкий язык и при необходимости предметную область. Приложение выделит до десяти предложений, покажет ключевые слова и веса.</li>
<li>Для наглядного реферата возьмите длинный текст тестовой коллекции. Короткий текст из трёх предложений почти не сокращается. Результат можно скачать, распечатать или удалить. Кнопка «Записать в OSTIS» работает, когда установлен py-sc-client и запущен sc-server.</li></ol>
<p>Приложение запускается локально. Данные и оценки хранятся в SQLite рядом с программой.</p>''', "help")


def language_page():
    rows = lab2.all_results()
    methods = [("ngram", "N-граммы"), ("alphabet", "Алфавит"), ("neural", "Нейросеть")]
    summary = []
    labelled = [row for row in rows if row["expected"]]
    for key, label in methods:
        accuracy = sum(row[key] == row["expected"] for row in labelled) / len(labelled) if labelled else None
        mean_ms = sum(row[f"{key}_ms"] for row in rows) / len(rows) if rows else None
        summary.append(f'<tr><td>{label}</td><td>{accuracy:.1%}</td><td>{mean_ms:.2f} мс</td></tr>'
                       if accuracy is not None else f'<tr><td>{label}</td><td>Нужна разметка</td><td>{mean_ms:.2f} мс</td></tr>'
                       if mean_ms is not None else f'<tr><td>{label}</td><td>—</td><td>—</td></tr>')
    result_rows = "".join(f'''<tr><td><a href="/language/document/{row["id"]}">{h(row["filename"])}</a></td>
<td>{h(row["expected"] or "—")}</td><td>{h(row["ngram"])}</td><td>{h(row["alphabet"])}</td>
<td>{h(row["neural"])}</td><td><strong>{h(row["overall"])}</strong></td>
<td><form method="post" action="/language/delete" onsubmit="return confirm('Удалить результат?')">
<input type="hidden" name="id" value="{row["id"]}"><button class="danger small">Удалить</button></form></td></tr>''' for row in rows)
    return page("Распознавание языка", '''<p class="lead">Русский и немецкий HTML-текст. Сравнение N-грамм, алфавитного и нейросетевого методов. Файлы для демонстрации лежат в папке lab2/examples.</p>
<h2>Добавить HTML-файлы</h2><p>Выберите документы примерно одинакового объёма. Можно указать их известный язык для оценки точности.</p>
<form id="language-upload"><label>HTML-файлы<input type="file" name="files" accept=".html,.htm,text/html" multiple required></label>
<label>Известный язык<select name="expected"><option value="">Не указан</option><option value="ru">Русский</option><option value="de">Немецкий</option></select></label>
<button>Распознать</button><span id="upload-status"></span></form>
<script>document.getElementById('language-upload').addEventListener('submit',async e=>{e.preventDefault();const f=e.target;
const items=await Promise.all([...f.files.files].map(async file=>({filename:file.name,html:await file.text(),expected:f.expected.value})));
const s=document.getElementById('upload-status');s.textContent='Обработка...';
try{const r=await fetch('/language/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(items)});
if(!r.ok)throw Error(await r.text());location.href='/language'}catch(err){s.textContent='Ошибка: '+err.message}})</script>
<h2>Сводная статистика</h2><table><tr><th>Метод</th><th>Точность на размеченных</th><th>Среднее время</th></tr>'''
                + "".join(summary) + '''</table><p><a href="/language/export">Сохранить CSV</a> · <button type="button" onclick="window.print()">Распечатать</button></p>
<h2>Документы</h2><div class="table-scroll"><table><tr><th>Документ</th><th>Эталон</th><th>N-граммы</th><th>Алфавит</th><th>Нейросеть</th><th>Итог</th><th>Действие</th></tr>'''
                + result_rows + '</table></div>', "language")


def language_document_page(document_id):
    row = lab2.get_result(document_id)
    if not row:
        return error_page("Документ не найден")
    source = (f'<p>Источник: <a href="{h(row["source_url"])}" target="_blank" rel="noopener">{h(row["source_url"])}</a></p>'
              if row["source_url"] else "")
    return page(row["filename"], f'<p><a href="/language">← К результатам</a></p>{source}'
                + f'<p>Распознанный язык: <strong>{h(row["overall"])}</strong></p>'
                + f'<p><a class="button-link" href="/summary?from_language={document_id}">Реферировать текст →</a></p>'
                + f'<article class="card prose">{h(row["text"])}</article>'
                + f'<form method="post" action="/language/delete" onsubmit="return confirm(\'Удалить результат?\')">'
                  f'<input type="hidden" name="id" value="{document_id}"><button class="danger">Удалить результат</button></form>', "language")


def summary_samples():
    path = SUMMARY_CORPUS_ROOT / "sources.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def summary_page(from_search="", from_language="", sample=""):
    title, document, language, source_url = "", "", "ru", ""
    item = None
    if from_search:
        source = lab1.get_document(int(from_search))
        if not source:
            return error_page("Документ поиска не найден")
        title, document, source_url = source["title"], source["body"], f'/document/{source["id"]}'
    elif from_language:
        source = lab2.get_result(int(from_language))
        if not source:
            return error_page("Документ распознавания не найден")
        title, document = source["filename"], source["text"]
        language, source_url = source["overall"], f'/language/document/{source["id"]}'
    elif sample:
        item = next((entry for entry in summary_samples() if entry["file"] == sample), None)
        if item is None:
            return error_page("Пример документа не найден")
        title, language = item["title"], item["language"]
        document = (SUMMARY_CORPUS_ROOT / item["file"]).read_text(encoding="utf-8")
        source_url = item["source_urls"][0]

    history = lab3_store.all_summaries()
    examples = "".join(f'''<a class="sample-card" href="/summary?sample={quote(item["file"])}">
<strong>{h(item["title"])}</strong><span>{h(item["language"])} · {h(item["subject_area"])} · 20 000 знаков</span></a>'''
                       for item in summary_samples())
    cards = "".join(f'''<div class="history-row"><a class="history-item" href="/summary/result/{row["id"]}">
<span><strong>{h(row["title"])}</strong><small>{h(row["created_at"])}</small></span>
<span class="history-arrow">→</span></a>
<form method="post" action="/summary/delete" onsubmit="return confirm('Удалить реферат?')">
<input type="hidden" name="id" value="{row["id"]}"><button class="danger small">Удалить</button></form></div>''' for row in history)
    short_source = ('<div class="alert">Этот исходный текст короткий. Методичка рекомендует выбирать около десяти предложений из большого документа; '
                    'для наглядного реферата возьмите один из текстов тестовой коллекции ниже.</div>'
                    if document and len(document) < 1000 else '')
    form = f'''<p class="lead">Классический реферат здесь — это предложения исходного текста с наибольшим весом, сохранённые в исходном порядке. Методичка рекомендует около десяти предложений из большого документа.</p>{short_source}
<form method="post" action="/summary/create" id="summary-form" class="card form-card">
<div class="form-grid"><label>Название документа<input name="title" value="{h(title)}" placeholder="Например, статья об алгоритмах"></label>
<label>Язык<select name="language"><option value="ru" {"selected" if language == "ru" else ""}>Русский</option>
<option value="de" {"selected" if language == "de" else ""}>Немецкий</option></select></label></div>
<label>Предметная область<input name="subject_area" list="subject-areas" placeholder="Например, computer science" value="{h(item["subject_area"] if sample and item else "")}"></label>
<datalist id="subject-areas"><option value="computer science"><option value="литература"></datalist>
<label>Ссылка на исходный документ<input name="source_url" value="{h(source_url)}" placeholder="URL или ссылка на документ в приложении"></label>
<label>Текст документа<textarea name="document" id="summary-text" rows="13" required placeholder="Вставьте текст документа...">{h(document)}</textarea></label>
<label class="upload-label">Загрузить текстовый файл (.txt, .md)<input id="summary-file" type="file" accept=".txt,.md,text/plain"></label>
<div class="form-grid narrow"><label>Предложений в реферате<input name="max_sentences" type="number" min="1" max="30" value="10" required></label>
<label>Ключевых слов<input name="max_keywords" type="number" min="1" max="50" value="20" required></label></div>
<button>Построить реферат</button></form>
<script>document.getElementById('summary-file').addEventListener('change',async e=>{{const file=e.target.files[0];
if(file){{document.getElementById('summary-text').value=await file.text();
const title=document.querySelector('#summary-form [name=title]');if(!title.value)title.value=file.name;}}}})</script>
<h2>Тестовая коллекция</h2><p class="muted">Для демонстрации реферирования используйте эти четыре текста по 20 000 знаков. Короткий текст из первой работы может содержать всего три предложения и почти не сокращается.</p>
<div class="sample-grid">{examples}</div>
<h2>Сохранённые рефераты</h2>{cards or '<p class="muted">Рефератов пока нет.</p>'}'''
    return page("Реферирование документов", form, "summary")


def summary_result_page(summary_id, ostis_status=""):
    row = lab3_store.get(summary_id)
    if row is None:
        return error_page("Реферат не найден")
    result = row["result"]
    source_sentence_count = len(result["sentence_scores"])
    summary_sentence_count = len(result["summary"])
    summary_char_count = sum(len(sentence) for sentence in result["summary"])
    compression = 1 - summary_char_count / max(len(result["document"]), 1)
    source_url = row["source_url"]
    parsed = urlparse(source_url)
    safe_source = source_url.startswith(("/document/", "/language/document/")) or parsed.scheme in ("http", "https")
    source = f'<a href="{h(source_url)}" target="_blank" rel="noopener">Открыть исходный документ ↗</a>' if source_url and safe_source else ""
    notice = ('<div class="success">Результат записан в OSTIS.</div>' if ostis_status == "ok" else
              '<div class="alert">Не удалось записать в OSTIS. Реферат сохранён локально; проверьте sc-server и py-sc-client.</div>'
              if ostis_status == "fail" else "")
    length_notice = (f'<div class="alert">Исходный текст содержит только {source_sentence_count} предложений. '
                     'Это слишком мало для содержательного сокращения: реферат почти повторяет оригинал. '
                     'Для демонстрации возьмите текст из тестовой коллекции объёмом 20 000 знаков.</div>'
                     if source_sentence_count <= summary_sentence_count else '')
    meta = f'''<div class="result-meta"><span>Язык: <strong>{h(result["language"])}</strong></span>
<span>Область: <strong>{h(result.get("subject_area") or "не указана")}</strong></span>
<span>Предложений в реферате: <strong>{summary_sentence_count} из {source_sentence_count}</strong></span>
<span>Сокращение по символам: <strong>{compression:.0%}</strong></span></div>'''
    summary_text = h(" ".join(result["summary"]))
    keywords = "".join(f'<tr><td>{h(item["word"])}</td><td>{item["weight"]:.4f}</td></tr>'
                       for item in result["keywords"])
    scores = "".join(f'''<tr><td>{item["index"] + 1}</td><td>{h(item["sentence"])}</td>
<td>{item["score"]:.4f}</td><td>{item["lexical_score"]:.4f}</td>
<td>{item["position_document"]:.3f}</td><td>{item["position_paragraph"]:.3f}</td></tr>'''
                     for item in result["sentence_scores"])
    ostis_button = ("Уже записано в OSTIS" if row["ostis_saved"] else "Записать в OSTIS")
    content = f'''<p><a href="/summary">← К реферированию</a></p>{notice}{length_notice}{meta}
<div class="actions">{source}<a href="/summary/export/{summary_id}.txt">Сохранить TXT</a>
<a href="/summary/export/{summary_id}.json">Сохранить JSON</a>
<button type="button" onclick="window.print()">Распечатать</button>
<form method="post" action="/summary/ostis"><input type="hidden" name="id" value="{summary_id}">
<button class="secondary" {"disabled" if row["ostis_saved"] else ""}>{ostis_button}</button></form>
<form method="post" action="/summary/delete" onsubmit="return confirm('Удалить локальный реферат?')">
<input type="hidden" name="id" value="{summary_id}"><button class="danger small">Удалить</button></form></div>
<section class="card"><h2>Классический реферат</h2><p class="summary-prose">{summary_text}</p></section>
<section class="card"><h2>Ключевые слова</h2><div class="table-scroll"><table><tr><th>Слово</th><th>Вес TF·IDF</th></tr>{keywords}</table></div></section>
<details class="card"><summary>Веса всех предложений</summary><div class="table-scroll"><table>
<tr><th>№</th><th>Предложение</th><th>Итог</th><th>Лексический вес</th><th>Позиция в документе</th><th>Позиция в абзаце</th></tr>{scores}</table></div></details>
<details class="card"><summary>Исходный текст</summary><div class="prose source-text">{h(result["document"])}</div></details>'''
    return page(row["title"], content, "summary")


def summary_export_text(row):
    result = row["result"]
    lines = [row["title"], f'Язык: {result["language"]}',
             f'Предметная область: {result.get("subject_area") or "не указана"}']
    if row["source_url"]:
        lines.append(f'Источник: {row["source_url"]}')
    lines.extend(["", "Классический реферат"])
    lines.append(" ".join(result["summary"]))
    lines.extend(["", "Ключевые слова"])
    lines.extend(f'{item["word"]}: {item["weight"]:.6f}' for item in result["keywords"])
    lines.extend(["", "Оценки предложений"])
    lines.extend(f'{item["index"] + 1}. {item["score"]:.6f} — {item["sentence"]}'
                 for item in result["sentence_scores"])
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def send_html(self, content, status=200):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, destination):
        self.send_response(303)
        self.send_header("Location", destination)
        self.end_headers()

    def send_download(self, data, filename, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = urlparse(self.path)
        parameters = parse_qs(route.query)
        query = parameters.get("q", [""])[0].strip()
        if route.path == "/static/style.css":
            data = (Path(__file__).with_name("static") / "style.css").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route.path == "/":
            self.send_html(home_page())
        elif route.path == "/search":
            self.send_html(search_page(query))
        elif route.path == "/documents":
            self.send_html(documents_page())
        elif route.path.startswith("/document/"):
            try:
                self.send_html(document_page(int(route.path.rsplit("/", 1)[-1])))
            except ValueError:
                self.send_html(error_page("Неверный номер документа"), 400)
        elif route.path == "/metrics":
            self.send_html(metrics_page(query))
        elif route.path == "/language":
            self.send_html(language_page())
        elif route.path.startswith("/language/document/"):
            try:
                self.send_html(language_document_page(int(route.path.rsplit("/", 1)[-1])))
            except ValueError:
                self.send_html(error_page("Неверный номер документа"), 400)
        elif route.path == "/language/export":
            output = io.StringIO()
            writer = csv.writer(output)
            fields = ["filename", "source_url", "expected", "ngram", "alphabet", "neural", "overall",
                      "ngram_ms", "alphabet_ms", "neural_ms"]
            writer.writerow(fields)
            for row in lab2.all_results():
                writer.writerow([row[field] for field in fields])
            data = ("\ufeff" + output.getvalue()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="language_results.csv"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route.path == "/summary":
            try:
                self.send_html(summary_page(parameters.get("from_search", [""])[0],
                                            parameters.get("from_language", [""])[0],
                                            parameters.get("sample", [""])[0]))
            except ValueError:
                self.send_html(error_page("Неверный номер исходного документа"), 400)
        elif route.path.startswith("/summary/result/"):
            try:
                self.send_html(summary_result_page(int(route.path.rsplit("/", 1)[-1]),
                                                   parameters.get("ostis", [""])[0]))
            except ValueError:
                self.send_html(error_page("Неверный номер реферата"), 400)
        elif route.path.startswith("/summary/export/"):
            name = route.path.rsplit("/", 1)[-1]
            try:
                number, extension = name.rsplit(".", 1)
                summary_id = int(number)
                if extension not in ("txt", "json"):
                    raise ValueError
                row = lab3_store.get(summary_id)
                if row is None:
                    self.send_html(error_page("Реферат не найден"), 404)
                    return
                if extension == "txt":
                    data = ("\ufeff" + summary_export_text(row)).encode("utf-8")
                    content_type = "text/plain; charset=utf-8"
                else:
                    data = json.dumps(row["result"], ensure_ascii=False, indent=2).encode("utf-8")
                    content_type = "application/json; charset=utf-8"
                self.send_download(data, f"summary_{summary_id}.{extension}", content_type)
            except ValueError:
                self.send_html(error_page("Неверный формат выгрузки"), 400)
        elif route.path == "/help":
            self.send_html(help_page())
        else:
            self.send_html(error_page("Страница не найдена"), 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            self.send_html(error_page("Данные больше 2 МБ"), 413)
            return
        raw = self.rfile.read(length)
        if self.path == "/language/upload":
            try:
                items = json.loads(raw)
                if not isinstance(items, list) or len(items) > 30:
                    raise ValueError("Выберите от одного до 30 HTML-файлов")
                model = language_recognizer()
                for item in items:
                    filename = str(item.get("filename", ""))
                    html = str(item.get("html", ""))
                    if not filename.lower().endswith((".html", ".htm")):
                        raise ValueError("Разрешены только HTML-файлы")
                    result = model.analyze(html)
                    lab2.save_result(filename, html, result, item.get("expected", ""))
                self.send_html("Готово")
            except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
                self.send_html(error_page(str(exc)), 400)
            return
        form = {key: values[0] for key, values in parse_qs(raw.decode("utf-8")).items()}
        try:
            if self.path == "/documents":
                lab1.add_document(form.get("title", ""), form.get("body", ""), form.get("source_url", ""))
                self.redirect("/documents")
            elif self.path == "/import":
                url = form.get("url", "")
                title, body = lab1.fetch_url(url)
                lab1.add_document(title or url, body, url)
                self.redirect("/documents")
            elif self.path == "/delete":
                lab1.delete_document(int(form.get("id", "0")))
                self.redirect("/documents")
            elif self.path == "/language/delete":
                lab2.delete_result(int(form.get("id", "0")))
                self.redirect("/language")
            elif self.path == "/summary/create":
                max_sentences = int(form.get("max_sentences", "10"))
                max_keywords = int(form.get("max_keywords", "20"))
                if not 1 <= max_sentences <= 30 or not 1 <= max_keywords <= 50:
                    raise ValueError("Укажите от 1 до 30 предложений и от 1 до 50 ключевых слов")
                result = summarize(form.get("document", ""), language=form.get("language", "ru"),
                                   max_sentences=max_sentences, max_keywords=max_keywords,
                                   subject_area=form.get("subject_area", "").strip() or None)
                summary_id = lab3_store.save(form.get("title", ""), result,
                                             form.get("source_url", ""))
                self.redirect(f"/summary/result/{summary_id}")
            elif self.path == "/summary/delete":
                lab3_store.delete(int(form.get("id", "0")))
                self.redirect("/summary")
            elif self.path == "/summary/ostis":
                summary_id = int(form.get("id", "0"))
                row = lab3_store.get(summary_id)
                if row is None:
                    self.send_html(error_page("Реферат не найден"), 404)
                    return
                saved = save_to_ostis(row["result"])
                if saved:
                    lab3_store.mark_ostis_saved(summary_id)
                self.redirect(f'/summary/result/{summary_id}?ostis={"ok" if saved else "fail"}')
            else:
                self.send_html(error_page("Страница не найдена"), 404)
        except (ValueError, OSError, UnicodeError, FileNotFoundError) as exc:
            self.send_html(error_page(str(exc)), 400)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EYAZIS: локальное веб-приложение")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    initialize()
    lab2.initialize()
    lab3_store.initialize()
    print(f"Откройте http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
