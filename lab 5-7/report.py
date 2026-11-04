"""Portable report materials: real measurements, audio, SVGs and user observations."""
import csv
from html import escape
import io
import json
import math
import zipfile

from . import audio, storage
from .tasks import NAMES, TASKS


def measurements(data):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["time_s", "f0_hz", "rms"])
    writer.writerows(zip(data["times"], ["" if v is None else v for v in data["f0"]], data["energy"]))
    return ("\ufeff" + out.getvalue()).encode("utf-8")


def plot(data, kind="wave", title=""):
    width, height, left, right = 1000, 260, 65, 975
    top, bottom = 40, 210
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
                '<rect width="100%" height="100%" fill="white"/>',
                f'<text x="{left}" y="23" font-family="sans-serif" font-size="16">{escape(title)}</text>']
    peak = max(.001, data['peak'])
    unit = 10 ** math.floor(math.log10(peak))
    amplitude = math.ceil(peak / unit) * unit
    energy_max = max(.001, max(data['energy'], default=0)) * 1.1
    for i in range(5):
        y = top + (bottom - top) * i / 4
        elements.append(f'<path d="M{left},{y} H{right}" stroke="#dce5e8"/>')
        label = f'{(1-i/2)*amplitude:.3f}' if kind == "wave" else f'{500-i*125:g}'
        elements.append(f'<text x="8" y="{y+5}" font-family="sans-serif" font-size="12">{label}</text>')
    start, end = data["start"], data["end"]
    for i in range(6):
        x = left + (right - left) * i / 5
        elements.append(f'<text x="{x}" y="235" text-anchor="middle" font-family="sans-serif" font-size="12">{start+(end-start)*i/5:.3f} с</text>')
    if kind == "wave":
        low, high = data["wave"]["low"], data["wave"]["high"]
        commands = []
        for i, (lo, hi) in enumerate(zip(low, high)):
            x = left + (right - left) * (i + .5) / len(low)
            commands.append(f'M{x:.2f},{125-hi/amplitude*85:.2f} V{125-lo/amplitude*85:.2f}')
        elements.append(f'<path d="{" ".join(commands)}" stroke="#087b89" fill="none"/>')
    else:
        for values, maximum, color in ((data["f0"], 500, "#087b89"), (data["energy"], energy_max, "#ba5b28")):
            commands, drawing = [], False
            for t, v in zip(data["times"], values):
                if v is None:
                    drawing = False
                    continue
                x = left + (right-left) * (t-start) / max(end-start, 1e-9)
                y = bottom - (bottom-top) * min(v/maximum, 1)
                commands.append(f'{"L" if drawing else "M"}{x:.2f},{y:.2f}')
                drawing = True
            elements.append(f'<path d="{" ".join(commands)}" stroke="{color}" stroke-width="2" fill="none"/>')
        elements.append(f'<text x="700" y="23" font-family="sans-serif" font-size="12">F₀: 0–500 Гц · RMS: 0–{energy_max:.3f}</text>')
    return ''.join(elements) + '</svg>'


def build(lab):
    rows = storage.list_clips(lab)
    experiments = storage.experiments(lab)
    required = {item['id'] for case in experiments for item in case['items']}
    required.update(n for case in experiments for n in case.get('supporting_ids',[]))
    clips = {clip_id: storage.get(clip_id) for clip_id in required} if experiments else {
        row["id"]: storage.get(row["id"]) for row in rows}
    missing = set()
    pending = list(clips.values())
    while pending:
        row = pending.pop()
        provenance = row["provenance"]
        sources = [provenance["source_id"]] if "source_id" in provenance else []
        sources += provenance.get('source_ids', [])
        sources += [p["id"] for p in provenance.get("pieces", []) if "id" in p]
        for clip_id in sources:
            if clip_id in clips or clip_id in missing:
                continue
            try:
                source = storage.get(clip_id)
            except ValueError:
                missing.add(clip_id)
                continue
            clips[clip_id] = source
            pending.append(source)
    out = io.BytesIO()
    title = f'Лабораторная {lab}. {NAMES[lab]}'
    body = [f'<h1>{escape(title)}</h1>',
            '<p>ПО: локальное приложение EYAZIS, модуль обработки речи. WAV PCM; для анализа стерео сводится в моно. '
            'Осциллограмма: минимумы/максимумы отсчётов; F₀: автокорреляция окон Ханна 40 мс с поправкой на перекрытие, диапазон 60–500 Гц; '
            'энергия: RMS. Отсутствие F₀ означает неуверенную оценку. '
            'Изменение длительности и независимый сдвиг тона используют фазовый вокодер STFT; '
            'изменение частоты дискретизации — ресемплинг Фурье с ограничением полосы. '
            '</p>', '<h2>Содержание работы</h2>']
    for key, heading, prompt, instruction in TASKS[lab]:
        body.append(f'<h3>{escape(heading)}</h3><p>{escape(instruction)}</p>')
    if missing:
        body.append(f'<p>Некоторые исходники ранее удалены из библиотеки: {sorted(missing)}.</p>')
    if storage.notes(lab):
        body.append('<h2>Выводы</h2><pre>' + escape(storage.notes(lab)) + '</pre>')
    if lab == 7:
        body.append('<h2>Структура моделируемого компиляционного синтезатора</h2><p>'
                    'Орфографический текст → ручная транскрипция с ударениями → последовательность фонем/слогов '
                    '→ поиск записей в фонетической базе → приведение к общей частоте → монтаж и паузы '
                    '→ обработка тона, амплитуды и длительности → WAV.</p>')
    manifest = []
    figures = {}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for clip_id, row in sorted(clips.items()):
            x, rate, _ = audio.decode(row["wav"])
            data = audio.analyze(x, rate)
            prefix = f'clips/{clip_id}'
            archive.writestr(f'{prefix}.wav', row["wav"])
            archive.writestr(f'{prefix}.csv', measurements(data))
            wave_svg = plot(data, "wave", row["title"])
            contour_svg = plot(data, "contours", row["title"])
            archive.writestr(f'{prefix}-wave.svg', wave_svg)
            archive.writestr(f'{prefix}-contours.svg', contour_svg)
            figures[clip_id] = (wave_svg, contour_svg)
            info = {k: v for k, v in row.items() if k != "wav"}
            info["measurements"] = {k: v for k, v in data.items() if k not in ("wave", "times", "f0", "energy")}
            manifest.append(info)
            source_note = ' · исходник из другой работы' if row["lab"] != lab else ''
            if experiments:
                continue
            body.extend([f'<section><h2>#{clip_id} {escape(row["title"])}{source_note}</h2>',
                         f'<p>{row["sample_rate"]} Гц · {row["bits"]} бит · {row["duration"]:.3f} с · '
                         f'{len(row["wav"])} байт · {escape(row["speaker"])}</p>',
                         f'<p>{escape(row["text"])}</p><audio controls src="{prefix}.wav"></audio>',
                         wave_svg, contour_svg,
                         '<p>Разметка: ' + escape('; '.join(f'{r["label"]}: {r["start"]:.5f}–{r["end"]:.5f} с '
                           f'({r["end"]-r["start"]:.5f} с)' for r in row["regions"]) or 'не добавлена') + '</p>',
                         '<pre>' + escape(row["notes"]) + '</pre>' if row['notes'] else '',
                         '<details><summary>История получения</summary><pre>' + escape(json.dumps(row["provenance"], ensure_ascii=False, indent=2)) + '</pre></details></section>'])
        for case in experiments:
            body += [f'<section><h2>{escape(case["title"])}</h2><p>{escape(case["description"])}</p>']
            if case.get('transcription'):
                body.append('<p><b>Транскрипция:</b> '+escape(case['transcription'])+'</p>')
            body.append('<table><thead><tr><th>Вариант</th><th>Длительность, с</th><th>F₀, Гц</th><th>RMS</th><th>Формат</th><th>Запись</th></tr></thead><tbody>')
            for item in case['items']:
                n=item['id'];m=item.get('measurement',{})
                pitch=f'{m["median_f0"]:.1f}' if m.get('median_f0') else '—'
                body.append(f'<tr><td>{escape(item["role"])}</td><td>{m.get("duration",0):.3f}</td>'
                            f'<td>{pitch}</td><td>{m.get("rms",0):.4f}</td><td>{m.get("sample_rate",0)} Гц / {m.get("bits",0)} бит</td>'
                            f'<td><audio controls preload="none" src="clips/{n}.wav"></audio>'
                            f'<a href="clips/{n}.csv">CSV</a> · <a href="clips/{n}-wave.svg">SVG</a></td></tr>')
            body.append('</tbody></table><p>'+escape(case.get('finding',''))+'</p>')
            if case.get('recipe'):
                body.append('<details><summary>Параметры обработки</summary><pre>'+escape(case['recipe'])+'</pre></details>')
            selected = [case['items'][0],case['items'][1] if case['key']=='5-01-quality' else case['items'][-1]]
            for item in selected:
                body.append('<h3>'+escape(item['role'])+'</h3>')
                body.extend(figures[item['id']])
            if case.get('observations'):
                body.append('<p><b>Слуховая оценка:</b></p><pre>'+escape(case['observations'])+'</pre>')
            body.append('</section>')
        archive.writestr('manifest.json', json.dumps({"lab": lab, "notes": storage.notes(lab),
                                                    "experiments": experiments, "clips": manifest}, ensure_ascii=False, indent=2))
        html = ('<!doctype html><html lang="ru"><meta charset="utf-8"><title>' + escape(title) + '</title>'
                '<style>body{font:16px/1.5 system-ui;max-width:1000px;margin:40px auto;padding:20px;color:#172a32}'
                'svg{width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-top:1px solid #ccc;margin-top:30px}'
                'table{width:100%;border-collapse:collapse;font-size:13px}td,th{border:1px solid #ccd8db;padding:7px;text-align:left}'
                'audio{width:180px;height:32px;display:block}'
                '@media print{audio,details{display:none}svg{break-inside:avoid}body{margin:0}}</style>' + ''.join(body) + '</html>')
        archive.writestr('report.html', html)
    return out.getvalue()
