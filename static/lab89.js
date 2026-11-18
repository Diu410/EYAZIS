(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const text = $('speech-text'), voice = $('voice'), status = $('tts-status');
  const example = 'Un algorithme de recherche analyse les données et construit un index. Le système classe les documents selon leur pertinence.';
  try { text.value = localStorage.getItem('eyazis-lab89-text') || example; } catch (_) { text.value = example; }
  function persist() { try { localStorage.setItem('eyazis-lab89-text', text.value); } catch (_) {} }
  text.addEventListener('input', persist);
  let examples = [];
  async function loadExamples() {
    const select = $('example-select');
    try {
      const response = await fetch('/api/lab89/examples');
      if (!response.ok) throw new Error('Не удалось загрузить примеры.');
      examples = (await response.json()).examples;
      select.replaceChildren();
      if (!examples.length) { select.add(new Option('Примеры недоступны', '')); return; }
      examples.forEach(item => select.add(new Option(item.title, item.id)));
      $('example').disabled = false;
    } catch (_) { select.replaceChildren(new Option('Не удалось загрузить примеры', '')); }
  }
  $('example').addEventListener('click', () => {
    const selected = examples.find(item => item.id === $('example-select').value);
    if (selected) { text.value = selected.text; persist(); }
  });
  loadExamples();
  if ($('translate')) $('translate').addEventListener('click', async () => {
    const source = $('russian-text').value.trim(), button = $('translate'), notice = $('translation-status');
    if (!source) { notice.textContent = 'Введите русский текст.'; return; }
    button.disabled = true; notice.textContent = 'Переводим через Groq…';
    try {
      const response = await fetch('/api/lab8/translate', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab8'}, body: JSON.stringify({text: source})});
      const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Ошибка перевода.');
      text.value = result.translation; persist(); notice.textContent = 'Перевод готов. Проверьте и при необходимости исправьте его перед озвучиванием.';
    } catch (error) { notice.textContent = 'Ошибка: ' + error.message; }
    finally { button.disabled = false; }
  });
  for (const name of ['rate', 'volume']) $(name).addEventListener('input', () => { $(name + '-value').textContent = $(name).value; });
  let voices = [], player = null, audioUrl = null, generation = 0;
  function stopAudio() {
    generation++;
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    if (player) { player.pause(); player = null; }
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = null; }
  }
  function updateVoices() {
    const previous = voice.value;
    voices = window.speechSynthesis ? speechSynthesis.getVoices().filter(v => /^fr(?:-|$)/i.test(v.lang)) : [];
    voice.replaceChildren();
    voice.add(new Option('Siwis · fr-FR · Piper локально', 'local:piper-fr_FR-siwis-medium'));
    voice.add(new Option('Denise · fr-FR · Microsoft Edge онлайн', 'online:fr-FR-DeniseNeural'));
    voice.add(new Option('Henri · fr-FR · Microsoft Edge онлайн', 'online:fr-FR-HenriNeural'));
    voices.forEach((v, i) => voice.add(new Option(`${v.name} · ${v.lang}${v.localService ? ' · локальный' : ' · сетевой'}`, 'browser:' + i)));
    if ([...voice.options].some(option => option.value === previous)) voice.value = previous;
    updateSpeakLabel();
    $('voice-status').textContent = 'Piper работает локально. Голоса Microsoft используют интернет; дополнительные голоса предоставляет браузер.';
    $('speak').disabled = false;
  }
  function updateSpeakLabel() { $('speak').textContent = !voice.value.startsWith('browser:') ? '▶  Озвучить и сохранить' : '▶  Озвучить'; }
  voice.addEventListener('change', updateSpeakLabel);
  if ('speechSynthesis' in window) speechSynthesis.addEventListener('voiceschanged', updateVoices);
  updateVoices();
  async function speak() {
    if (!text.value.trim()) { status.textContent = 'Введите текст для озвучивания.'; return false; }
    stopAudio(); const current = generation;
    if (!voice.value.startsWith('browser:')) {
      status.textContent = voice.value.startsWith('local:') ? 'Создаём озвучку локально через Piper. При первом запуске скачивается голос…' : 'Создаём озвучку через Microsoft Edge TTS…';
      try {
        const response = await fetch('/api/lab8/synthesize', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab8'}, body: JSON.stringify({text: text.value.trim(), voice: voice.value.split(':')[1], rate: Number($('rate').value)})});
        const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка синтеза.');
        if (current !== generation) return false;
        if ($('saved-recordings') && data.recording) await refreshRecordings(data.recording.id);
        if (current !== generation) return false;
        const bytes = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
        audioUrl = URL.createObjectURL(new Blob([bytes], {type: 'audio/mpeg'}));
        player = new Audio(audioUrl); player.volume = Number($('volume').value);
        player.onended = () => { if (current === generation) status.textContent = 'Озвучивание завершено.'; };
        await player.play(); status.textContent = 'Идёт озвучивание. MP3 сохранён в коллекции лабораторной 9.'; return true;
      } catch (error) { if (current === generation) status.textContent = 'Ошибка озвучивания: ' + error.message; return false; }
    }
    const selected = voices[Number(voice.value.slice(8))];
    if (!selected) { status.textContent = 'Выберите доступный французский голос.'; return false; }
    const utterance = new SpeechSynthesisUtterance(text.value.trim());
    utterance.lang = selected.lang; utterance.voice = selected;
    utterance.rate = Number($('rate').value); utterance.volume = Number($('volume').value);
    utterance.onstart = () => { status.textContent = 'Идёт озвучивание.'; };
    utterance.onend = () => { status.textContent = 'Озвучивание завершено.'; };
    utterance.onerror = e => { status.textContent = 'Озвучивание прервано: ' + e.error; };
    speechSynthesis.speak(utterance);
    return true;
  }
  $('speak').addEventListener('click', speak);
  $('stop-speech').addEventListener('click', () => { stopAudio(); status.textContent = 'Озвучивание остановлено.'; });
  $('pause').addEventListener('click', () => {
    if (player) { if (player.paused) { player.play().catch(() => { status.textContent = 'Не удалось продолжить воспроизведение.'; }); status.textContent = 'Озвучивание продолжено.'; } else { player.pause(); status.textContent = 'Пауза.'; } return; }
    if (!('speechSynthesis' in window)) return;
    if (speechSynthesis.paused) { speechSynthesis.resume(); status.textContent = 'Озвучивание продолжено.'; }
    else if (speechSynthesis.speaking) { speechSynthesis.pause(); status.textContent = 'Пауза.'; }
  });
  if (!$('record')) return;
  const stt = $('stt-status'), transcript = $('transcript'), action = $('action');
  let savedItems = [];
  async function refreshRecordings(selectedId) {
    try {
      const response = await fetch('/api/lab89/recordings'); if (!response.ok) throw new Error('Не удалось загрузить записи.');
      savedItems = (await response.json()).recordings;
      const select = $('saved-recordings'); select.replaceChildren();
      select.add(new Option(savedItems.length ? 'Выберите запись' : 'Сохранённых записей пока нет', ''));
      savedItems.forEach(item => select.add(new Option(item.title, item.id)));
      if (typeof selectedId === 'string' && savedItems.some(item => item.id === selectedId)) select.value = selectedId;
      updateRecording();
    } catch (error) { $('saved-source').textContent = error.message; }
  }
  function updateRecording() {
    const item = savedItems.find(entry => entry.id === $('saved-recordings').value), player = $('saved-audio'), link = $('download-recording');
    player.hidden = !item; link.hidden = !item;
    if (!item) { player.removeAttribute('src'); $('saved-source').textContent = ''; return; }
    const url = '/api/lab89/audio/' + encodeURIComponent(item.id);
    player.src = url; link.href = url; link.download = item.id + '.mp3';
    $('saved-source').textContent = (item.source ? 'Источник: ' + item.source + ' · ' : '') + 'Исходный текст: ' + item.text;
  }
  $('saved-recordings').addEventListener('change', updateRecording);
  $('refresh-recordings').addEventListener('click', refreshRecordings);
  $('transcribe-saved').addEventListener('click', async () => {
    const id = $('saved-recordings').value;
    if (!id) { stt.textContent = 'Выберите сохранённую запись.'; return; }
    try { const response = await fetch('/api/lab89/audio/' + encodeURIComponent(id)); if (!response.ok) throw new Error('Запись не найдена.'); await send(await response.blob(), 'mp3'); }
    catch (error) { stt.textContent = 'Ошибка: ' + error.message; }
  });
  refreshRecordings();
  let recorder, stream, chunks = [], busy = false;
  function normalize(value) { return value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z\s]/g, ' ').replace(/\s+/g, ' ').trim(); }
  async function execute(value) {
    switch (normalize(value)) {
      case 'lire le texte': action.textContent = 'Подготовка озвучивания…'; action.textContent = await speak() ? 'Запущено озвучивание.' : 'Не удалось запустить озвучивание.'; break;
      case 'arreter la lecture': $('stop-speech').click(); action.textContent = 'Озвучивание остановлено.'; break;
      case 'effacer le texte': text.value = ''; persist(); action.textContent = 'Текст очищен.'; break;
      case 'afficher les commandes': action.textContent = 'Список команд показан выше.'; break;
      default: action.textContent = 'Текст распознан; голосовая команда не обнаружена.';
    }
  }
  async function send(blob, format) {
    if (busy) return;
    if (!blob.size || blob.size > 10 * 1024 * 1024) { stt.textContent = 'Аудио должно быть непустым и не превышать 10 МБ.'; return; }
    busy = true; $('record').disabled = true; $('transcribe-file').disabled = true;
    transcript.textContent = '—'; action.textContent = '—'; stt.textContent = $('stt-engine').value === 'local' ? 'Распознаём локально через Whisper. При первом запуске скачивается модель; это может занять продолжительное время…' : 'Отправляем аудио в Groq и ждём распознавание…';
    try {
      const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('Не удалось прочитать аудио.')); reader.readAsDataURL(blob); });
      const response = await fetch('/api/lab9/transcribe', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab9'}, body: JSON.stringify({format, audio: dataUrl.split(',')[1], engine: $('stt-engine').value})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Ошибка распознавания.');
      transcript.textContent = result.text || 'Речь не распознана';
      stt.textContent = result.text ? 'Распознавание завершено.' : 'Попробуйте записать команду ещё раз.';
      if (result.text) await execute(result.text);
    } catch (error) { stt.textContent = 'Ошибка: ' + error.message; }
    finally { busy = false; $('record').disabled = false; $('transcribe-file').disabled = false; }
  }
  $('record').addEventListener('click', async () => {
    if (!navigator.mediaDevices || !window.MediaRecorder) { stt.textContent = 'Запись с микрофона не поддерживается этим браузером.'; return; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      if (!mime) { stream.getTracks().forEach(track => track.stop()); stt.textContent = 'Браузер не поддерживает подходящий формат записи.'; return; }
      recorder = new MediaRecorder(stream, {mimeType: mime}); chunks = [];
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => { stream.getTracks().forEach(track => track.stop()); $('record-stop').disabled = true; send(new Blob(chunks, {type: mime}), mime.includes('ogg') ? 'ogg' : mime.includes('mp4') ? 'mp4' : 'webm'); };
      recorder.onerror = () => { stream.getTracks().forEach(track => track.stop()); $('record').disabled = false; $('record-stop').disabled = true; stt.textContent = 'Ошибка записи микрофона.'; };
      recorder.start(); $('record').disabled = true; $('record-stop').disabled = false; stt.textContent = 'Идёт запись. Произнесите одну команду.';
    } catch (error) { if (stream) stream.getTracks().forEach(track => track.stop()); $('record').disabled = false; stt.textContent = 'Микрофон недоступен: ' + error.message; }
  });
  $('record-stop').addEventListener('click', () => { if (recorder && recorder.state === 'recording') { $('record-stop').disabled = true; recorder.stop(); } });
  $('transcribe-file').addEventListener('click', () => {
    const file = $('audio-file').files[0];
    if (!file) { stt.textContent = 'Выберите аудиофайл.'; return; }
    const format = file.name.split('.').pop().toLowerCase();
    if (!['webm','wav','mp3','m4a','mp4','ogg','flac'].includes(format)) { stt.textContent = 'Поддерживаются webm, wav, mp3, m4a, mp4, ogg и flac.'; return; }
    send(file, format);
  });
})();
