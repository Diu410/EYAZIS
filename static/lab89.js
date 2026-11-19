(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const text = $('speech-text'), voice = $('voice'), status = $('tts-status');
  const textLanguage = $('text-language');
  const example = 'Un algorithme de recherche analyse les données et construit un index. Le système classe les documents selon leur pertinence.';
  try {
    text.value = localStorage.getItem('eyazis-lab89-text') || example;
    const savedLanguage = localStorage.getItem('eyazis-lab89-text-language');
    if (['fr', 'ru', 'en', 'de'].includes(savedLanguage)) textLanguage.value = savedLanguage;
    else if (/[а-яё]/i.test(text.value)) textLanguage.value = 'ru';
  } catch (_) { text.value = example; }
  function persist() { try { localStorage.setItem('eyazis-lab89-text', text.value); localStorage.setItem('eyazis-lab89-text-language', textLanguage.value); } catch (_) {} }
  text.addEventListener('input', () => { selectedExample = null; $('example-select').value = ''; persist(); });
  let examples = [];
  let selectedExample = null;
  async function loadExamples() {
    const select = $('example-select');
    try {
      const response = await fetch('/api/lab89/examples');
      if (!response.ok) throw new Error('Не удалось загрузить примеры.');
      examples = (await response.json()).examples;
      select.replaceChildren();
      if (!examples.length) { select.add(new Option('Примеры недоступны', '')); return; }
      select.add(new Option('Выберите учебный текст', ''));
      examples.forEach(item => select.add(new Option(`${item.title} · ${item.language.toUpperCase()}`, item.id)));
    } catch (_) { select.replaceChildren(new Option('Не удалось загрузить примеры', '')); }
  }
  $('example-select').addEventListener('change', () => {
    const selected = examples.find(item => item.id === $('example-select').value);
    selectedExample = selected || null;
    if (selected) { text.value = selected.text; textLanguage.value = selected.language; updateVoices(); persist(); }
  });
  loadExamples();
  if ($('translate')) $('translate').addEventListener('click', async () => {
    const source = $('russian-text').value.trim(), button = $('translate'), notice = $('translation-status');
    if (!source) { notice.textContent = 'Введите русский текст.'; return; }
    button.disabled = true; notice.textContent = 'Переводим через Groq…';
    try {
      const response = await fetch('/api/lab8/translate', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab8'}, body: JSON.stringify({text: source})});
      const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Ошибка перевода.');
      text.value = result.translation; selectedExample = null; $('example-select').value = ''; textLanguage.value = 'fr'; updateVoices(); persist(); notice.textContent = 'Перевод готов. Проверьте и при необходимости исправьте его перед озвучиванием.';
    } catch (error) { notice.textContent = 'Ошибка: ' + error.message; }
    finally { button.disabled = false; }
  });
  let player = null, audioUrl = null, generation = 0;
  const voiceOptions = {
    fr: [['Denise · fr-FR · Microsoft Edge онлайн', 'online:fr-FR-DeniseNeural'], ['Henri · fr-FR · Microsoft Edge онлайн', 'online:fr-FR-HenriNeural'], ['Siwis · fr-FR · Piper локально', 'local:piper-fr_FR-siwis-medium']],
    ru: [['Svetlana · ru-RU · Microsoft Edge онлайн', 'online:ru-RU-SvetlanaNeural']],
    en: [['Jenny · en-US · Microsoft Edge онлайн', 'online:en-US-JennyNeural']],
    de: [['Katja · de-DE · Microsoft Edge онлайн', 'online:de-DE-KatjaNeural']],
  };
  const chosenVoices = {};
  function updatePlayback() {
    const rate = Number($('rate').value), volume = Number($('volume').value);
    $('rate-value').textContent = rate; $('volume-value').textContent = volume;
    for (const audio of [player, $('saved-audio')]) if (audio) { audio.playbackRate = rate; audio.volume = volume; }
  }
  for (const name of ['rate', 'volume']) $(name).addEventListener('input', updatePlayback);
  function stopAudio() {
    generation++;
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    if (player) { player.pause(); player = null; }
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = null; }
  }
  function updateVoices() {
    const lang = textLanguage.value;
    voice.replaceChildren();
    voiceOptions[lang].forEach(([label, value]) => voice.add(new Option(label, value)));
    if ([...voice.options].some(option => option.value === chosenVoices[lang])) voice.value = chosenVoices[lang];
    $('voice-status').textContent = lang === 'fr' ? 'Denise и Henri работают через интернет, Siwis — локально через Piper.' : 'Голос Microsoft работает через интернет.';
    $('speak').disabled = false;
  }
  voice.addEventListener('change', () => { chosenVoices[textLanguage.value] = voice.value; });
  textLanguage.addEventListener('change', () => { updateVoices(); persist(); });
  updateVoices();
  async function speak(content = text.value, targetLanguage = null) {
    if (!content.trim()) { status.textContent = 'Введите текст для озвучивания.'; return false; }
    let selectedVoice = voice.value;
    const selectedLanguage = selectedVoice.startsWith('local:') ? 'fr' : selectedVoice.slice(7, 9).toLowerCase();
    const sampleLanguage = selectedExample && selectedExample.text.trim() === content.trim() ? selectedExample.language : null;
    const latinWithoutCyrillic = /[a-z]/i.test(content) && !/[а-яё]/i.test(content);
    const cyrillicWithoutLatin = /[а-яё]/i.test(content) && !/[a-z]/i.test(content);
    if (!targetLanguage && ((sampleLanguage && sampleLanguage !== selectedLanguage) ||
        (!sampleLanguage && selectedLanguage === 'ru' && latinWithoutCyrillic) ||
        (!sampleLanguage && selectedLanguage !== 'ru' && cyrillicWithoutLatin))) {
      window.alert('Язык текста и выбранного голоса не совпадает. Выберите подходящий язык текста.');
      status.textContent = 'Выберите голос, соответствующий языку текста.';
      return false;
    }
    if (targetLanguage && selectedLanguage !== targetLanguage) {
      selectedVoice = 'online:' + {fr:'fr-FR-DeniseNeural', ru:'ru-RU-SvetlanaNeural', en:'en-US-JennyNeural', de:'de-DE-KatjaNeural'}[targetLanguage];
    }
    stopAudio(); const current = generation;
    if (selectedVoice.startsWith('online:') || selectedVoice.startsWith('local:')) {
      status.textContent = selectedVoice.startsWith('local:') ? 'Создаём озвучку локально через Piper. При первом запуске скачивается голос…' : 'Создаём озвучку через Microsoft Edge TTS…';
      try {
        const response = await fetch('/api/lab8/synthesize', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab8'}, body: JSON.stringify({text: content.trim(), voice: selectedVoice.split(':')[1], rate: 1})});
        const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка синтеза.');
        if (current !== generation) return false;
        if ($('saved-recordings') && data.recording) await refreshRecordings(data.recording.id);
        if (current !== generation) return false;
        const bytes = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
        audioUrl = URL.createObjectURL(new Blob([bytes], {type: 'audio/mpeg'}));
        player = new Audio(audioUrl); updatePlayback();
        player.onended = () => { if (current === generation) status.textContent = 'Озвучивание завершено.'; };
        await player.play(); status.textContent = `Идёт озвучивание (${selectedVoice.split(':')[1]}). MP3 сохранён в коллекции лабораторной 9.`; return true;
      } catch (error) { if (current === generation) status.textContent = 'Ошибка озвучивания: ' + error.message; return false; }
    }
    status.textContent = 'Выберите доступный голос.';
    return false;
  }
  $('speak').addEventListener('click', () => speak());
  $('stop-speech').addEventListener('click', () => { stopAudio(); status.textContent = 'Озвучивание остановлено.'; });
  $('pause').addEventListener('click', () => {
    if (player) { if (player.paused) { player.play().catch(() => { status.textContent = 'Не удалось продолжить воспроизведение.'; }); status.textContent = 'Озвучивание продолжено.'; } else { player.pause(); status.textContent = 'Пауза.'; } return; }
    if (!('speechSynthesis' in window)) return;
    if (speechSynthesis.paused) { speechSynthesis.resume(); status.textContent = 'Озвучивание продолжено.'; }
    else if (speechSynthesis.speaking) { speechSynthesis.pause(); status.textContent = 'Пауза.'; }
  });
  if (!$('record')) return;
  const stt = $('stt-status'), transcript = $('transcript'), action = $('action');
  let savedItems = [], recordingGroups = [];
  const textKey = item => (item.text || '').normalize('NFC').replace(/\s+/g, ' ').trim();
  function activeRecordingId() { return $('recording-variants').value; }
  function variantLabel(item) {
    const date = item.created_at ? new Date(item.created_at).toLocaleString() : '';
    return [item.voice || 'Голос неизвестен', item.rate ? `скорость ${item.rate}` : '', date].filter(Boolean).join(' · ');
  }
  function closeRecordingMenu() {
    $('recordings-menu').hidden = true;
    $('recordings-toggle').setAttribute('aria-expanded', 'false');
  }
  function renderRecordingMenu() {
    const list = $('recordings-list'); list.replaceChildren();
    if (!recordingGroups.length) {
      const empty = document.createElement('li'); empty.className = 'voice-recording-empty'; empty.textContent = 'Сохранённых записей пока нет'; list.append(empty); return;
    }
    function row(item, group, label, variant, removable) {
      const li = document.createElement('li'), line = document.createElement('div'), choice = document.createElement('button');
      line.className = 'voice-recording-row'; choice.type = 'button'; choice.className = 'voice-recording-choice' + (variant ? ' voice-recording-variant' : '');
      choice.dataset.recordingId = item.id;
      choice.textContent = label; choice.title = label;
      choice.setAttribute('aria-pressed', String(variant ? activeRecordingId() === item.id : group.some(entry => entry.id === activeRecordingId())));
      choice.addEventListener('click', () => {
        $('saved-recordings').value = group[0].id; updateRecordingGroup(item.id); closeRecordingMenu(); $('recordings-toggle').focus();
      });
      line.append(choice);
      if (removable) {
        const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'voice-delete'; remove.textContent = '×';
        remove.dataset.recordingId = item.id;
        remove.setAttribute('aria-label', 'Удалить озвучку: ' + item.title + (variant ? ', ' + label : ''));
        remove.title = 'Удалить эту озвучку'; remove.addEventListener('click', () => deleteRecording(item.id, remove)); line.append(remove);
      }
      li.append(line); list.append(li);
    }
    recordingGroups.forEach(group => {
      row(group[0], group, group[0].title + (group.length > 1 ? ` (вариантов: ${group.length})` : ''), false, group.length === 1);
      if (group.length > 1) group.forEach(item => row(item, group, variantLabel(item), true, true));
    });
  }
  async function refreshRecordings(selectedId) {
    try {
      const response = await fetch('/api/lab89/recordings'); if (!response.ok) throw new Error('Не удалось загрузить записи.');
      savedItems = (await response.json()).recordings;
      const groups = new Map();
      savedItems.forEach(item => {
        const key = textKey(item) || item.id;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(item);
      });
      recordingGroups = [...groups.values()];
      const select = $('saved-recordings'); select.replaceChildren();
      select.add(new Option(savedItems.length ? 'Выберите запись' : 'Сохранённых записей пока нет', ''));
      recordingGroups.forEach(group => select.add(new Option(group[0].title, group[0].id)));
      const group = typeof selectedId === 'string' && recordingGroups.find(items => items.some(item => item.id === selectedId));
      if (group) select.value = group[0].id;
      updateRecordingGroup(selectedId);
    } catch (error) { $('saved-source').textContent = error.message; }
  }
  function updateRecordingGroup(selectedId) {
    const group = recordingGroups.find(items => items[0].id === $('saved-recordings').value) || [];
    const select = $('recording-variants'); select.replaceChildren();
    group.forEach(item => {
      select.add(new Option(variantLabel(item), item.id));
    });
    if (typeof selectedId === 'string' && group.some(item => item.id === selectedId)) select.value = selectedId;
    $('recording-variants-wrap').hidden = group.length < 2;
    updateRecording();
  }
  function updateRecording() {
    const item = savedItems.find(entry => entry.id === activeRecordingId()), player = $('saved-audio'), link = $('download-recording');
    player.hidden = !item; link.hidden = !item;
    $('recordings-selected').textContent = item ? item.title : (savedItems.length ? 'Выберите запись' : 'Сохранённых записей пока нет');
    renderRecordingMenu();
    if (!item) { player.removeAttribute('src'); $('saved-source').textContent = ''; return; }
    const url = '/api/lab89/audio/' + encodeURIComponent(item.id);
    player.src = url; link.href = url; link.download = item.id + '.mp3';
    updatePlayback();
    $('saved-source').textContent = (item.source ? 'Источник: ' + item.source + ' · ' : '') + 'Исходный текст: ' + item.text;
  }
  $('saved-recordings').addEventListener('change', () => updateRecordingGroup());
  $('recording-variants').addEventListener('change', updateRecording);
  $('refresh-recordings').addEventListener('click', () => refreshRecordings(activeRecordingId()));
  $('recordings-toggle').addEventListener('click', () => {
    const open = $('recordings-menu').hidden;
    $('recordings-menu').hidden = !open; $('recordings-toggle').setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', event => { if (!$('recording-dropdown').contains(event.target)) closeRecordingMenu(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('recordings-menu').hidden) { closeRecordingMenu(); $('recordings-toggle').focus(); } });
  async function deleteRecording(id, button) {
    const current = activeRecordingId();
    const group = recordingGroups.find(items => items.some(item => item.id === id)) || [];
    const next = group.find(item => item.id !== id);
    button.disabled = true;
    try {
      const response = await fetch('/api/lab89/recordings/delete', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab9'}, body: JSON.stringify({id})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Не удалось удалить запись.');
      await refreshRecordings(current === id ? (next ? next.id : '') : current);
      stt.textContent = 'Озвучка удалена.';
    } catch (error) { stt.textContent = 'Ошибка удаления: ' + error.message; button.disabled = false; }
  }
  $('transcribe-saved').addEventListener('click', async () => {
    const id = activeRecordingId();
    if (!id) { stt.textContent = 'Выберите сохранённую запись.'; return; }
    try { const response = await fetch('/api/lab89/audio/' + encodeURIComponent(id)); if (!response.ok) throw new Error('Запись не найдена.'); await enqueueTranscription(await response.blob(), 'mp3', false); }
    catch (error) { stt.textContent = 'Ошибка: ' + error.message; }
  });
  refreshRecordings();
  let busy = false, capture = null, transcriptParts = [], transcribeQueue = Promise.resolve(), queuedSegments = 0, lastSpoken = null;
  const cancelledSessions = new Set();
  const languages = ['fr', 'ru', 'en', 'de'], languageSelect = $('recognition-language');
  function normalize(value) { return value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim(); }
  const commandDefaults = {
    fr: [
      {id:'read', label:'Прочитать последнюю фразу', phrases:'lis; lire le texte; lisez le texte; lis le texte', enabled:true},
      {id:'stop', label:'Остановить озвучивание', phrases:'arrête; arrêter la lecture; arrêtez la lecture; arrête la lecture', enabled:true},
      {id:'clear', label:'Очистить распознанный текст', phrases:'efface; effacer le texte; effacez le texte; efface le texte', enabled:true},
      {id:'show', label:'Показать список команд', phrases:'commandes; afficher les commandes; affichez les commandes; affiche les commandes', enabled:true},
      {id:'change', label:'Следующий язык', phrases:'change de langue; langue suivante', enabled:true},
      {id:'stop-listening', label:'Остановить микрофон', phrases:'arrête le micro; arrêter le micro', enabled:true},
    ],
    ru: [
      {id:'read', label:'Прочитать последнюю фразу', phrases:'читай; прочитай; прочитай текст', enabled:true},
      {id:'stop', label:'Остановить озвучивание', phrases:'стоп звук; останови озвучку; останови чтение', enabled:true},
      {id:'clear', label:'Очистить распознанный текст', phrases:'очисти; очисти текст', enabled:true},
      {id:'show', label:'Показать список команд', phrases:'команды; покажи команды', enabled:true},
      {id:'change', label:'Следующий язык', phrases:'смени язык; поменяй язык; следующий язык', enabled:true},
      {id:'stop-listening', label:'Остановить микрофон', phrases:'стоп запись; останови запись; останови распознавание', enabled:true},
    ],
    en: [
      {id:'read', label:'Прочитать последнюю фразу', phrases:'read; read text; read the text', enabled:true},
      {id:'stop', label:'Остановить озвучивание', phrases:'stop reading; stop speech', enabled:true},
      {id:'clear', label:'Очистить распознанный текст', phrases:'clear; clear text; clear the text', enabled:true},
      {id:'show', label:'Показать список команд', phrases:'commands; show commands', enabled:true},
      {id:'change', label:'Следующий язык', phrases:'change language; next language', enabled:true},
      {id:'stop-listening', label:'Остановить микрофон', phrases:'stop listening; stop recording', enabled:true},
    ],
    de: [
      {id:'read', label:'Прочитать последнюю фразу', phrases:'lies; lies den text; text vorlesen', enabled:true},
      {id:'stop', label:'Остановить озвучивание', phrases:'stopp vorlesen; hör auf zu lesen', enabled:true},
      {id:'clear', label:'Очистить распознанный текст', phrases:'löschen; text löschen; lösche den text', enabled:true},
      {id:'show', label:'Показать список команд', phrases:'befehle; befehle anzeigen; zeig die befehle', enabled:true},
      {id:'change', label:'Следующий язык', phrases:'sprache wechseln; nächste sprache', enabled:true},
      {id:'stop-listening', label:'Остановить микрофон', phrases:'aufnahme stoppen; mikrofon stoppen', enabled:true},
    ],
  };
  const defaultsFor = lang => commandDefaults[lang].map(item => ({...item}));
  let commandsByLanguage = Object.fromEntries(languages.map(lang => [lang, defaultsFor(lang)]));
  try {
    const saved = JSON.parse(localStorage.getItem('eyazis-lab89-commands-v2') || 'null');
    const legacy = JSON.parse(localStorage.getItem('eyazis-lab89-commands') || 'null');
    for (const lang of languages) {
      const records = saved && Array.isArray(saved[lang]) ? saved[lang] : lang === 'fr' && Array.isArray(legacy) ? legacy : [];
      commandsByLanguage[lang] = defaultsFor(lang).map(item => {
        const found = records.find(entry => entry && entry.id === item.id && typeof entry.phrases === 'string' && typeof entry.enabled === 'boolean');
        return found ? {...item, phrases: found.phrases, enabled: found.enabled} : item;
      });
    }
  } catch (_) {}
  function renderCommands() {
    const container = $('command-settings'); container.replaceChildren();
    commandsByLanguage[languageSelect.value].forEach(command => {
      const row = document.createElement('div'), label = document.createElement('label'), enabled = document.createElement('input'), phrases = document.createElement('input');
      enabled.type = 'checkbox'; enabled.checked = command.enabled; enabled.dataset.command = command.id; enabled.dataset.field = 'enabled';
      label.append(enabled, document.createTextNode(' ' + command.label));
      phrases.type = 'text'; phrases.value = command.phrases; phrases.maxLength = 500; phrases.dataset.command = command.id; phrases.dataset.field = 'phrases';
      phrases.setAttribute('aria-label', 'Фразы: ' + command.label); row.append(label, phrases); container.append(row);
    });
  }
  $('save-commands').addEventListener('click', () => {
    const lang = languageSelect.value;
    const next = commandsByLanguage[lang].map(item => ({...item, enabled: document.querySelector(`[data-command="${item.id}"][data-field="enabled"]`).checked, phrases: document.querySelector(`[data-command="${item.id}"][data-field="phrases"]`).value.trim()}));
    const seen = new Set();
    for (const item of next.filter(item => item.enabled)) {
      const phrases = item.phrases.split(';').map(normalize).filter(Boolean);
      if (!phrases.length) { $('command-status').textContent = 'Укажите хотя бы одну фразу для каждого включённого действия.'; return; }
      for (const phrase of phrases) {
        if (seen.has(phrase)) { $('command-status').textContent = 'Одинаковую фразу нельзя назначить нескольким действиям.'; return; }
        seen.add(phrase);
      }
    }
    const updated = {...commandsByLanguage, [lang]: next};
    try { localStorage.setItem('eyazis-lab89-commands-v2', JSON.stringify(updated)); }
    catch (_) { $('command-status').textContent = 'Не удалось сохранить настройки в браузере.'; return; }
    commandsByLanguage = updated; $('command-status').textContent = 'Команды сохранены для выбранного языка в этом браузере.';
  });
  $('reset-commands').addEventListener('click', () => {
    const lang = languageSelect.value, updated = {...commandsByLanguage, [lang]: defaultsFor(lang)};
    try { localStorage.setItem('eyazis-lab89-commands-v2', JSON.stringify(updated)); }
    catch (_) { $('command-status').textContent = 'Не удалось сохранить настройки в браузере.'; return; }
    commandsByLanguage = updated;
    renderCommands(); $('command-status').textContent = 'Стандартные команды восстановлены.';
  });
  languageSelect.addEventListener('change', () => { renderCommands(); $('command-status').textContent = ''; });
  renderCommands();
  async function execute(value, language) {
    const phrase = normalize(value);
    const options = commandsByLanguage[language];
    const findCommand = candidate => options.find(item => item.enabled && item.phrases.split(';').some(variant => normalize(variant) === candidate));
    // Whisper can transcribe short French commands as similarly sounding words.
    // Respect explicit user phrases first, then use these aliases only when the
    // corresponding canonical command is still enabled in the settings.
    const aliases = language === 'fr' ? {'lise': 'lis', 'command this': 'commandes'} : {};
    const match = findCommand(phrase) || (aliases[phrase] && findCommand(aliases[phrase]));
    switch (match && match.id) {
      case 'read':
        action.textContent = 'Подготовка озвучивания…'; action.textContent = await speak(lastSpoken ? lastSpoken.text : text.value, lastSpoken ? lastSpoken.language : null) ? 'Озвучивается последняя фраза.' : 'Не удалось запустить озвучивание.'; break;
      case 'stop':
        $('stop-speech').click(); action.textContent = 'Озвучивание остановлено.'; break;
      case 'clear':
        transcriptParts = []; transcript.textContent = '—'; lastSpoken = null; action.textContent = 'Распознанный текст очищен.'; break;
      case 'show':
        $('commands').open = true; action.textContent = 'Список голосовых команд открыт.'; break;
      case 'change':
        languageSelect.value = languages[(languages.indexOf(languageSelect.value) + 1) % languages.length];
        languageSelect.dispatchEvent(new Event('change'));
        action.textContent = 'Язык распознавания: ' + languageSelect.selectedOptions[0].textContent + '.'; break;
      case 'stop-listening':
        if (capture) {
          const id = capture.id; cancelledSessions.add(id);
          stopCapture('Микрофон остановлен голосовой командой.', true);
          transcribeQueue.finally(() => cancelledSessions.delete(id));
          action.textContent = 'Микрофон остановлен.';
        }
        else action.textContent = 'Микрофон уже выключен.';
        break;
      default: lastSpoken = {text: value, language}; action.textContent = 'Текст распознан; голосовая команда не обнаружена.';
    }
  }
  async function send(blob, format, append = false, engine = $('stt-engine').value, language = languageSelect.value) {
    if (busy) return;
    if (!blob.size || blob.size > 10 * 1024 * 1024) { stt.textContent = 'Аудио должно быть непустым и не превышать 10 МБ.'; return; }
    busy = true; $('transcribe-file').disabled = true; $('transcribe-saved').disabled = true;
    if (!append) { transcriptParts = []; transcript.textContent = '—'; }
    action.textContent = '—'; stt.textContent = engine === 'local' ? 'Распознаём локально через Whisper…' : 'Отправляем аудио в Groq и ждём распознавание…';
    try {
      const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('Не удалось прочитать аудио.')); reader.readAsDataURL(blob); });
      const response = await fetch('/api/lab9/transcribe', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab9'}, body: JSON.stringify({format, audio: dataUrl.split(',')[1], engine, language})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Ошибка распознавания.');
      if (result.text) transcriptParts.push(result.text);
      transcript.textContent = transcriptParts.join('\n') || 'Речь не распознана';
      stt.textContent = result.text ? 'Распознавание завершено.' : 'Попробуйте записать команду ещё раз.';
      if (result.text) await execute(result.text, language);
    } catch (error) { stt.textContent = 'Ошибка: ' + error.message; }
    finally { busy = false; $('transcribe-file').disabled = false; $('transcribe-saved').disabled = false; }
  }
  function enqueueTranscription(blob, format, append, sessionId = null) {
    const engine = $('stt-engine').value;
    const task = transcribeQueue.then(() => sessionId && cancelledSessions.has(sessionId) ? undefined : send(blob, format, append, engine, languageSelect.value));
    transcribeQueue = task.catch(error => { stt.textContent = 'Ошибка: ' + error.message; });
    return task;
  }
  function pcmWav(chunks) {
    const samples = chunks.reduce((n, chunk) => n + chunk.length, 0), buffer = new ArrayBuffer(44 + samples * 2), view = new DataView(buffer);
    const put = (at, str) => [...str].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
    put(0, 'RIFF'); view.setUint32(4, 36 + samples * 2, true); put(8, 'WAVE'); put(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    put(36, 'data'); view.setUint32(40, samples * 2, true);
    let offset = 44; chunks.forEach(chunk => { for (const value of chunk) { view.setInt16(offset, value, true); offset += 2; } });
    return new Blob([buffer], {type: 'audio/wav'});
  }
  function queueSegment(chunks, sessionId) {
    if (!chunks.length) return;
    if (queuedSegments >= 5) { stopCapture('Очередь распознавания заполнена. Дождитесь результатов и включите микрофон снова.'); return; }
    queuedSegments++;
    const wav = pcmWav(chunks);
    enqueueTranscription(wav, 'wav', true, sessionId).finally(() => { queuedSegments--; });
  }
  async function vadRequest(state, pcm, end = false) {
    const audio = pcm && btoa(String.fromCharCode(...new Uint8Array(pcm.buffer)));
    const response = await fetch('/api/lab9/vad', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Eyazis-Request': 'lab9'}, body: JSON.stringify({session: state.id, ...(end ? {end: true} : {audio})})});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка Silero VAD.');
    return data;
  }
  function finishSegment(state) {
    if (!state.discard && state.speech && state.parts.length) queueSegment(state.parts, state.id);
    state.speech = false; state.parts = []; state.silence = 0;
  }
  async function processAudio(state) {
    if (state.processing) return;
    state.processing = true;
    try {
      while (state.chunks.length) {
        const pcm = state.chunks.shift(), result = await vadRequest(state, pcm);
        if (state.discard) break;
        const speaking = result.probabilities.some(value => value >= 0.5);
        if (!state.speech) {
          state.pre.push(pcm); if (state.pre.length > 3) state.pre.shift();
          if (speaking) { state.speech = true; state.parts = state.pre; state.pre = []; state.silence = 0; $('mic-status').textContent = 'Речь обнаружена. Слушаем…'; }
        } else {
          state.parts.push(pcm); state.silence = speaking ? 0 : state.silence + 1;
          if (state.silence >= 8 || state.parts.length >= 156) {
            finishSegment(state); $('mic-status').textContent = 'Пауза: фраза отправлена. Микрофон продолжает слушать.';
          }
        }
      }
      if (state.stopped) { finishSegment(state); await vadRequest(state, null, true); }
    } catch (error) { stopCapture('Ошибка Silero VAD: ' + error.message); }
    finally { state.processing = false; }
  }
  function stopCapture(message, discard = false) {
    const state = capture;
    if (!state || state.stopped) return;
    state.stopped = true; state.discard = discard; capture = null;
    if (discard) { state.chunks.length = 0; state.parts = []; state.speech = false; }
    state.processor.disconnect(); state.source.disconnect(); state.gain.disconnect();
    state.stream.getTracks().forEach(track => track.stop()); state.context.close();
    $('record').disabled = false; $('record-stop').disabled = true; $('stt-engine').disabled = false;
    $('mic-status').textContent = message || 'Микрофон выключен. Завершаем обработку последней фразы.';
    processAudio(state);
  }
  $('record').addEventListener('click', async () => {
    if (!navigator.mediaDevices || !(window.AudioContext || window.webkitAudioContext)) { stt.textContent = 'Микрофон или Web Audio недоступен в браузере.'; return; }
    let stream, context;
    $('record').disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}, video: false});
      const Context = window.AudioContext || window.webkitAudioContext; context = new Context({sampleRate: 16000});
      if (context.sampleRate !== 16000) throw new Error('Браузер не поддерживает запись 16 кГц. Попробуйте Chrome или Edge.');
      await context.resume();
      const source = context.createMediaStreamSource(stream), processor = context.createScriptProcessor(2048, 1, 1), gain = context.createGain();
      gain.gain.value = 0; source.connect(processor); processor.connect(gain); gain.connect(context.destination);
      const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2, '0')).join('');
      const state = {id, stream, context, source, processor, gain, chunks: [], pre: [], parts: [], speech: false, silence: 0, stopped: false, processing: false};
      capture = state; transcriptParts = []; transcript.textContent = '—'; action.textContent = '—';
      $('record-stop').disabled = false; $('stt-engine').disabled = true; $('mic-status').textContent = 'Микрофон включён. Говорите на выбранном языке.';
      processor.onaudioprocess = event => {
        if (state.stopped) return;
        const data = event.inputBuffer.getChannelData(0), pcm = new Int16Array(data.length);
        for (let i = 0; i < data.length; i++) pcm[i] = Math.round(Math.max(-1, Math.min(1, data[i])) * (data[i] < 0 ? 32768 : 32767));
        state.chunks.push(pcm);
        if (state.chunks.length > 32) { stopCapture('Silero не успевает обработать звук. Включите микрофон снова.'); return; }
        processAudio(state);
      };
    } catch (error) {
      if (stream) stream.getTracks().forEach(track => track.stop()); if (context) context.close();
      $('record').disabled = false; $('mic-status').textContent = 'Микрофон недоступен: ' + error.message;
    }
  });
  $('record-stop').addEventListener('click', () => stopCapture());
  $('transcribe-file').addEventListener('click', () => {
    const file = $('audio-file').files[0];
    if (!file) { stt.textContent = 'Выберите аудиофайл.'; return; }
    const format = file.name.split('.').pop().toLowerCase();
    if (!['webm','wav','mp3','m4a','mp4','ogg','flac'].includes(format)) { stt.textContent = 'Поддерживаются webm, wav, mp3, m4a, mp4, ogg и flac.'; return; }
    enqueueTranscription(file, format, false);
  });
})();
