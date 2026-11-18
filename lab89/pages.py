"""Shared workspace for the French-language speech labs."""


def content(lab):
    return '''<link rel="stylesheet" href="/static/lab89.css?v=2">
<div class="voice-workspace">
<p class="voice-intro">Создайте французскую озвучку и сразу проверьте её распознавание. Вариант 4 · Computer Science</p>
<div class="voice-steps"><a href="#synthesis"><span>01</span> Озвучить текст</a><span aria-hidden="true">→</span><a href="#recognition"><span>02</span> Распознать запись</a></div>
<section id="synthesis" class="voice-card"><div class="voice-section-heading"><div><span class="voice-label">ЛАБОРАТОРНАЯ 08</span><h2>Создать озвучку</h2><p>Введите текст на французском или переведите с русского.</p></div><span class="voice-badge">FR · СИНТЕЗ</span></div>
<details class="voice-translate"><summary>Перевести текст с русского</summary>
<label for="russian-text">Русский текст</label><textarea id="russian-text" rows="4" maxlength="4000" placeholder="Введите текст на русском языке"></textarea>
<div class="voice-actions"><button id="translate" class="secondary" type="button">Перевести на французский</button><span id="translation-status" role="status" aria-live="polite">Перевод через Groq</span></div></details>
<label for="example-select">Учебный текст</label><select id="example-select"><option value="">Загрузка примеров…</option></select>
<div class="voice-label-row"><label for="speech-text">Французский текст</label><button id="example" class="voice-text-button" type="button" disabled>Загрузить пример</button></div>
<textarea id="speech-text" rows="5" maxlength="6000" placeholder="Введите текст на французском"></textarea>
<div class="voice-settings"><label>Голос<select id="voice"></select></label><label>Скорость <output id="rate-value">1</output><input id="rate" type="range" min="0.5" max="2" value="1" step="0.1"></label><label>Громкость <output id="volume-value">1</output><input id="volume" type="range" min="0" max="1" value="1" step="0.1"></label></div>
<p id="voice-status" class="voice-hint" role="status"></p>
<div class="voice-actions"><button id="speak" type="button">▶ &nbsp; Озвучить и сохранить</button><button id="pause" class="secondary" type="button">Пауза / продолжить</button><button id="stop-speech" class="secondary" type="button">Остановить</button></div>
<p id="tts-status" class="voice-status" role="status" aria-live="polite">Готово к озвучиванию.</p><p class="voice-hint">Piper и Microsoft Edge TTS сохраняют MP3 в коллекцию ниже. Браузерные голоса воспроизводятся без сохранения.</p></section>
<section id="recognition" class="voice-card"><div class="voice-section-heading"><div><span class="voice-label">ЛАБОРАТОРНАЯ 09</span><h2>Распознать речь</h2><p>Выберите готовую озвучку, загрузите файл или запишите голос.</p></div><span class="voice-badge">FR · WHISPER</span></div>
<div class="voice-subsection"><div class="voice-label-row"><label for="saved-recordings">Сохранённая озвучка</label><button id="refresh-recordings" class="voice-text-button" type="button">Обновить список</button></div>
<select id="saved-recordings"><option value="">Загрузка…</option></select><audio id="saved-audio" controls hidden></audio>
<p id="saved-source" class="voice-hint"></p><div class="voice-actions"><button id="transcribe-saved" type="button">Распознать запись</button><a id="download-recording" hidden>Скачать MP3</a></div></div>
<div class="voice-alternatives"><div class="voice-subsection"><h3>Загрузить аудио</h3><label for="audio-file" class="voice-hint">WAV, MP3, M4A, MP4, WEBM, OGG или FLAC · до 10 МБ</label><input id="audio-file" type="file" accept="audio/*,.webm,.wav,.mp3,.m4a,.ogg,.flac"><button id="transcribe-file" class="secondary" type="button">Распознать файл</button></div>
<div class="voice-subsection"><h3>Записать с микрофона</h3><p class="voice-hint">Произнесите текст или одну из команд на французском.</p><div class="voice-actions"><button id="record" class="secondary" type="button">Начать запись</button><button id="record-stop" class="secondary" type="button" disabled>Остановить и распознать</button></div></div></div>
<label for="stt-engine">Распознавание</label><select id="stt-engine"><option value="local">Whisper large-v3-turbo · локально в Docker</option><option value="groq">Whisper large-v3-turbo · Groq онлайн</option></select>
<label for="recognition-language">Язык распознавания</label><select id="recognition-language"><option value="fr">Французский (вариант 4)</option></select>
<div class="voice-result" aria-live="polite"><span class="voice-label">РЕЗУЛЬТАТ РАСПОЗНАВАНИЯ</span><p id="stt-status" role="status">Выберите запись или загрузите файл.</p><p id="transcript" class="voice-transcript">—</p><p class="voice-hint">Действие: <span id="action">—</span></p></div>
<details class="voice-commands"><summary>Голосовые команды</summary><p>При точном совпадении фразы выполняется действие:</p><ul><li><strong>lire le texte</strong> — озвучить текст</li><li><strong>arrêter la lecture</strong> — остановить озвучивание</li><li><strong>effacer le texte</strong> — очистить текст</li><li><strong>afficher les commandes</strong> — показать список команд</li></ul></details>
<p class="voice-hint">Piper и локальный Whisper обрабатывают данные на компьютере. При выборе Microsoft или Groq данные отправляются соответствующему сервису. Перевод с русского использует Groq.</p></section></div>
<script src="/static/lab89.js?v=4" defer></script>'''
