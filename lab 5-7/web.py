"""Presentation of completed speech laboratory experiments."""
import json


def content(lab):
    config=json.dumps({'lab':lab})
    return f'''<link rel="stylesheet" href="/static/speech.css?v=3">
<div class="speech-toolbar"><a class="button-link" href="/speech/report/{lab}">Отчёт ZIP</a></div>
<div id="speech-status" role="status" aria-live="polite" class="results-status" hidden></div>
<section class="card" id="results-panel"><label>Опыт<select id="experiment-select"><option>Загрузка…</option></select></label>
<div id="experiment-result"></div>
<details id="result-plots"><summary>Осциллограммы и контуры</summary><div id="result-charts"></div></details>
<details id="result-observation-panel"><summary>Слуховая оценка</summary>
<label>Результат<textarea id="result-observation" rows="3"></textarea></label>
<button type="button" id="result-observation-save" class="secondary">Сохранить</button></details></section>
<section class="card" id="conclusions-panel"><h2>Выводы</h2><div id="lab-conclusions"></div></section>
<script id="speech-config" type="application/json">{config}</script>
<script src="/static/speech-results.js?v=3" defer></script>'''
