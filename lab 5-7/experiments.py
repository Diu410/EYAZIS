"""Repeatable experiments on the recorded session, without overwriting sources.

Run with the project virtualenv: python -m speech.experiments
The session JSON records known prompts/order. Envelope segmentation and DTW are
approximations, not speech recognition; their provenance stays in every result.
"""
from functools import lru_cache
import itertools
import json
from pathlib import Path

import numpy as np

from . import audio, storage


def detect_segments(x, rate, gap=.18, threshold=.012, minimum=.08):
    size, hop = round(rate * .025), round(rate * .01)
    if len(x) < size:
        return [(0, len(x) / rate)]
    frames = np.lib.stride_tricks.sliding_window_view(x, size)[::hop]
    energy = np.sqrt(np.mean(frames ** 2, axis=1))
    groups = []
    for i in np.flatnonzero(energy > threshold):
        if groups and i - groups[-1][1] <= round(gap / .01):
            groups[-1][1] = int(i)
        else:
            groups.append([int(i), int(i)])
    return [(max(0, a * .01 - .04), min(len(x) / rate, b * .01 + .075))
            for a, b in groups if (b - a) * .01 >= minimum]


def spectral_features(x, rate):
    """Cepstral envelope features for approximate alignment of known words."""
    x = audio.resample(x, max(1, round(len(x) * 16000 / rate)))
    x = np.concatenate(([x[0]], x[1:] - .97 * x[:-1]))
    x = np.pad(x, (0, max(0, 400 - len(x))))
    frames = np.lib.stride_tricks.sliding_window_view(x, 400)[::160]
    spectrum = abs(np.fft.rfft(frames * np.hanning(400), n=512)) ** 2
    # 32 triangular filters on a mel-frequency grid, followed by a DCT.
    mel = np.linspace(2595 * np.log10(1 + 80 / 700), 2595 * np.log10(1 + 7600 / 700), 34)
    edges = 700 * (10 ** (mel / 2595) - 1)
    freqs = np.fft.rfftfreq(512, 1 / 16000)
    filters = np.array([np.maximum(0, np.minimum((freqs - a) / (b - a), (c - freqs) / (c - b)))
                        for a, b, c in zip(edges[:-2], edges[1:-1], edges[2:])])
    logs = np.log(np.maximum(spectrum @ filters.T, 1e-12))
    dct = np.cos(np.pi / 32 * (np.arange(32) + .5)[None, :] * np.arange(1, 14)[:, None])
    features = logs @ dct.T
    return features / np.maximum(np.linalg.norm(features, axis=1, keepdims=True), 1e-9)


def align_words(templates, target, rate):
    """DTW of the supplied word order; return relative approximate word bounds."""
    features = [spectral_features(x, rate) for x in templates]
    a = np.concatenate(features)
    b = spectral_features(target, rate)
    distance = 1 - a @ b.T
    n, m = distance.shape
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i, j] = distance[i - 1, j - 1] + min(cost[i - 1, j - 1],
                                                    cost[i - 1, j] + .06, cost[i, j - 1] + .06)
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        step = int(np.argmin([cost[i - 1, j - 1], cost[i - 1, j] + .06, cost[i, j - 1] + .06]))
        if step in (0, 1): i -= 1
        if step in (0, 2): j -= 1
    bounds = [0.0]
    for border in np.cumsum([len(f) for f in features])[:-1]:
        matched = [j for i, j in path if abs(i - border) <= 1]
        value = np.median(matched) * .01 if matched else len(target) / rate * border / n
        bounds.append(float(value))
    bounds.append(len(target) / rate)
    # Prevent an alignment collapse; retain the known word order.
    if any(b - a < .08 for a, b in zip(bounds[:-1], bounds[1:])):
        bounds = [0] + [len(target) / rate * v / n for v in np.cumsum([len(f) for f in features])[:-1]] + [len(target) / rate]
    return list(zip(bounds[:-1], bounds[1:]))


class Runner:
    def __init__(self, session):
        storage.initialize()
        self.session = session
        self.records = session['recordings']
        self.vowels = session['vowel_clips'].copy()
        self.syllables = session['syllable_clips'].copy()
        self.existing = {r['provenance']['experiment_key']: r['id'] for r in storage.list_clips()
                         if 'experiment_key' in r['provenance']}

    @lru_cache(maxsize=200)
    def signal(self, clip_id):
        row = storage.get(clip_id)
        x, rate, bits = audio.decode(row['wav'])
        return x, rate, row

    def save(self, key, x, rate, lab, task, title, source=None, bits=16, kind='processed', text='', **provenance):
        if key in self.existing:
            return self.existing[key]
        recipe = {'operation': 'experiment', 'experiment_key': key, **provenance}
        if source is not None:
            recipe['source_id'] = int(source)
        clip_id = storage.save(audio.encode(x, rate, bits),
                               {'lab': lab, 'task': task, 'title': title, 'kind': kind, 'text': text,
                                'speaker': self.signal(source)[2]['speaker'] if source else 'Диктор 1'}, recipe)
        self.existing[key] = clip_id
        return clip_id

    def crop(self, source, a, b, key, title, lab, task, kind='processed', text=''):
        x, rate, _ = self.signal(source)
        left, right = audio.bounds(x, rate, a, b)
        return self.save(key, x[left:right], rate, lab, task, title, source=source, kind=kind, text=text,
                         params={'start': left / rate, 'end': right / rate})

    def split(self, source, labels, key, lab, task, kind='processed', gap=.18):
        x, rate, row = self.signal(source)
        spans = detect_segments(x, rate, gap=gap)
        if len(spans) != len(labels):
            raise ValueError(f'Запись #{source}: найдено {len(spans)} участков вместо {len(labels)}. Нужна проверка границ.')
        regions = [{'label': label, 'start': a, 'end': b} for label, (a, b) in zip(labels, spans)]
        storage.update(source, {'regions': regions})
        return [self.crop(source, a, b, f'{key}-{i}', label, lab, task, kind, label)
                for i, (label, (a, b)) in enumerate(zip(labels, spans))]

    @lru_cache(maxsize=300)
    def measurement(self, clip_id):
        x, rate, row = self.signal(clip_id)
        a = audio.analyze(x, rate)
        return {k: a[k] for k in ('duration', 'peak', 'rms', 'clipped_percent', 'median_f0')} | {
            'sample_rate': rate, 'bits': row['bits'], 'size_bytes': len(row['wav'])}

    def case(self, key, lab, title, description, items, finding='', metrics=None, recipe='', transcription=''):
        from .presentation import clean_case
        data=clean_case({'key':key, 'lab':lab, 'title': title, 'description': description,
            'items': [{'id': int(n), 'role': role, 'measurement': self.measurement(n)} for role, n in items],
            'finding': finding, 'metrics': metrics or [], 'recipe': recipe, 'transcription': transcription})
        storage.save_experiment(key, lab, {k:v for k,v in data.items() if k not in ('key','lab')})
        print(f'ЛР{lab}: {title}', flush=True)

    def normalize(self, x, peak=.65):
        return x * min(20, peak / max(float(np.max(abs(x))), 1e-9))

    def assemble(self, key, parts, lab, task, title, gap_ms=0, fade_ms=0, text=''):
        signals, recipe = [], []
        for clip_id in parts:
            if isinstance(clip_id, float):
                signals.append(np.zeros(round(32000 * clip_id)))
                recipe.append({'silence_ms': round(clip_id * 1000), 'label': 'Пауза'})
            else:
                x, rate, row = self.signal(clip_id)
                signals.append(audio.resample(x, round(len(x) * 32000 / rate)))
                recipe.append({'id': int(clip_id), 'title': row['title'], 'start': 0, 'end': len(x) / rate})
        joined = audio.join(signals, 32000, gap_ms, fade_ms)
        return self.save(key, joined, 32000, lab, task, title, kind='synthesis', text=text,
                         pieces=recipe, params={'gap_ms': gap_ms, 'fade_ms': fade_ms})

    def run5(self):
        source = self.records['quality']
        x, rate, _ = self.signal(source)
        variants = [('Исходная запись', source)]
        for target in (4000, 8000, 16000, 32000):
            y = audio.resample(x, round(len(x) * target / rate))
            for bits in (8, 16):
                n = self.save(f'quality-{target}-{bits}', y, target, 5, '5-quality',
                              f'{target} Гц · {bits} бит', source, bits, 'quality',
                              params={'resampling': 'Fourier', 'rate': target, 'bits': bits})
                variants.append((f'{target} Гц / {bits} бит', n))
        self.case('5-01-quality', 5, '1.3 · Частота дискретизации и разрядность',
                  'Одна фраза в восьми форматах: 4/8/16/32 кГц и 8/16 бит.', variants,
                  'Варианты получены пересчётом одного исходника. Это не независимые записи с разными настройками АЦП. '
                  'При одинаковой длительности размер PCM пропорционален частоте дискретизации и разрядности.',
                  ['8 вариантов', f'Длительность {len(x)/rate:.3f} с'],
                  'Ресемплинг Фурье с ограничением полосы; равномерное квантование PCM 8/16 бит. Без подавления шума.')
        for label, clip_id in self.vowels.items():
            x, rate, _ = self.signal(clip_id)
            f0 = self.measurement(clip_id)['median_f0']
            if f0 is None:
                raise ValueError(f'Не определён период гласной {label}')
            count = round(rate / f0)
            center = len(x) // 2
            crossings = np.flatnonzero((x[:-1] <= 0) & (x[1:] > 0))
            a = int(crossings[np.argmin(abs(crossings - center))] + 1) if len(crossings) else center
            period = self.crop(clip_id, a/rate, (a+count)/rate, f'period-{label}', f'{label}: один период', 5, '5-vowels')
            loop = self.save(f'period-loop-{label}', np.tile(x[a:a+count], 120), rate, 5, '5-vowels',
                             f'{label}: период × 120', period, params={'repeat': 120})
            self.case(f'5-02-vowel-{label}', 5, f'1.4.1 · Гласная [{label}]: один период и повтор',
                      'Исходная гласная, короткий одиночный участок и его циклическое повторение.',
                      [('Гласная целиком', clip_id), ('Один период', period), ('Повтор × 120', loop)],
                      'Длина периода выбрана по оценке F₀ на устойчивом участке. Один период слишком короток для распознавания на слух; '
                      'повтор формирует длительное периодическое колебание.',
                      [f'Период {1000*count/rate:.2f} мс', f'Частота повтора {rate/count:.1f} Гц'])
        iotated = self.split(self.records['iotated'], ['я', 'ё', 'ю', 'е'], 'iotated', 5, '5-iotated')
        self.case('5-03-iotated', 5, '1.4.1 · Йотированные гласные',
                  'Записи «я, ё, ю, е» и начальные переходы [й] к гласным.',
                  list(zip(['Я: [йа]', 'Ё: [йо]', 'Ю: [йу]', 'Е: [йэ]'], iotated)),
                  'Границы сегментов выделены по огибающей сигнала.')
        fricatives = self.split(self.records['fricatives'], ['ф', 'с', 'ш', 'х'], 'fricative', 5, '5-fricatives', 'phoneme')
        fric_syllables = self.split(self.records['fricative_syllables'], ['фа', 'са', 'ша', 'ха'],
                                    'fricative-syllable', 5, '5-fricative-syllables', 'syllable')
        self.syllables.update(dict(zip(['фа', 'са', 'ша', 'ха'], fric_syllables)))
        self.phonemes = self.vowels | dict(zip(['ф', 'с', 'ш', 'х'], fricatives))
        for label, sound_id, syllable_id in zip(['ф', 'с', 'ш', 'х'], fricatives, fric_syllables):
            x, rate, _ = self.signal(sound_id)
            a = len(x)//2
            fragment = self.crop(sound_id, a/rate, a/rate+.01, f'noise-fragment-{label}', f'{label}: участок 10 мс', 5, '5-fricatives')
            loop = self.save(f'noise-loop-{label}', np.tile(x[a:a+round(rate*.01)], 120), rate, 5, '5-fricatives',
                             f'{label}: участок × 120', fragment, params={'repeat': 120, 'length_ms': 10})
            prefix = self.consonant(syllable_id, label, 'fric-prefix-'+label, 5, '5-fricative-syllables')
            storage.update(prefix, {'title': label+' — начало слога'})
            self.case(f'5-04-fricative-{label}', 5, f'1.4.2 · [{label}]: отдельно, в слоге и в цикле',
                      'Шумовой звук, слог, согласный участок слога и повтор участка длительностью 10 мс.',
                      [('Изолированный звук', sound_id), ('Слог '+label+'а', syllable_id),
                       ('Начало слога: согласный участок', prefix), ('Короткий участок × 120', loop)],
                      'Повторенный шумовой фрагмент становится искусственно периодическим. Граница согласного в слоге приближённая.')
        isolated = self.split(self.records['isolated_consonants'], ['б отдельно', 'д отдельно', 'м отдельно', 'н отдельно'],
                              'isolated', 5, '5-consonants')
        for label, isolated_id in zip(['б', 'д', 'м', 'н'], isolated):
            syllable_id = self.syllables[label+'а']
            prefix = self.consonant(syllable_id, label, 'prefix-'+label, 5, '5-syllables')
            self.phonemes[label] = prefix
            x, rate, _ = self.signal(prefix)
            core = x[len(x)//2:len(x)//2+round(rate*.01)]
            loop = self.save('consonant-loop-'+label, np.tile(core, 120), rate, 5, '5-consonants',
                             f'{label}: короткий участок × 120', prefix, params={'length_ms': 10, 'repeat': 120})
            self.case('5-05-coart-'+label, 5, f'1.4.3 · Коартикуляция [{label}]',
                      'Изолированная запись, целый слог, его начало и повтор короткого участка согласного.',
                      [('Изолированное произнесение', isolated_id), ('Слог '+label+'а', syllable_id),
                       ('Начало слога', prefix), ('Короткий участок × 120', loop)],
                      'Разделение слога на согласный и гласный приближённое: переходные участки принадлежат совместной артикуляции. '
                      'Вырезанное начало слога сохраняет влияние гласного контекста.')
        hard = ['б','д','м','н','п','т','к','в','з','ж','л','р','ц','щ','ч']
        soft = ['б','д','м','н','п','т','к','г','в','ф','з','с','х','л','р']
        for label in hard + ['г']:
            symbol = label+"'" if label in ['щ','ч'] else label
            if symbol not in self.phonemes:
                self.phonemes[symbol] = self.consonant(self.syllables[label+'а'], symbol, 'base-'+symbol, 5, '5-syllables')
        for label in soft:
            self.phonemes[label+"'"] = self.consonant(self.syllables[label+'и'], label+"'", 'base-soft-'+label, 5, '5-syllables')
        y, rate, _ = self.signal(iotated[0])
        self.phonemes['й'] = self.crop(iotated[0], .03, min(.13, len(y)/rate), 'base-j', 'й: начальный переход', 5, '5-iotated', 'phoneme', 'й')
        pairs = [('Твёрдый: '+s, self.syllables[s+'а']) for s in soft if s+'а' in self.syllables]
        pairs += [('Мягкий: '+s, self.syllables[s+'и']) for s in soft]
        self.case('5-06-pairs', 5, '1.4.3 · Твёрдые и мягкие согласные в слогах',
                  'Полная коллекция записанных пар. Выберите две строки для сравнения, например «ба» и «би».', pairs,
                  'Сравниваются разные гласные и разные артикуляционные контексты. Различия нельзя приписывать только мягкости согласного.')
        for label in soft:
            variants=[]
            for symbol,vowel in [(label,'а'),(label+"'",'и')]:
                prefix=self.phonemes[symbol]
                x,rate,_=self.signal(prefix)
                left=max(0,len(x)//2-round(rate*.005));core=x[left:left+round(rate*.01)]
                loop=self.save('all-consonant-loop-'+symbol,np.tile(core,120),rate,5,'5-syllables',
                               f'[{symbol}]: участок × 120',prefix,params={'length_ms':10,'repeat':120})
                variants += [('Слог '+label+vowel,self.syllables[label+vowel]),
                             ('Начало слога ['+symbol+']',prefix),('Короткий участок ['+symbol+'] × 120',loop)]
            self.case('5-06-pair-'+label,5,f'1.4.3 · [{label}] и [{label}\']: слог, начало, повтор',
                      'Аналогичное исследование твёрдого и мягкого согласного: целый слог, вырезанное начало и цикл короткого участка.',
                      variants,'Периодичность искусственно создаётся повторением; это не означает наличия устойчивого периода в исходном согласном. '
                      'Приближённые границы не устраняют коартикуляцию.')
        for symbol in ['ж','ш','ц',"ч'","щ'",'й']:
            prefix=self.phonemes[symbol]
            x,rate,_=self.signal(prefix)
            left=max(0,len(x)//2-round(rate*.005));core=x[left:left+round(rate*.01)]
            loop=self.save('all-consonant-loop-'+symbol,np.tile(core,120),rate,5,'5-syllables',
                           f'[{symbol}]: участок × 120',prefix,params={'length_ms':10,'repeat':120})
            self.case('5-06-unpaired-'+symbol,5,f'1.4.3 · Непарный согласный [{symbol}]',
                      'Вырезанный согласный участок и циклическое повторение его короткой части.',
                      [('Согласный участок',prefix),('Участок × 120',loop)],
                      'Целый участок и искусственный периодический сигнал. Подпись согласного определяется известным текстом записи; '
                      'выделение границ автоматическое и приблизительное.')
        second = self.split(self.records['speaker2'], ['а','о','у','э','ы','и','Фраза диктора 2'],
                            'speaker2', 5, '5-speakers', gap=.3)
        for label, second_id in zip(['а','о','у','э','ы','и'], second):
            self.case('5-07-speaker-'+label, 5, f'1.5 · Два диктора: [{label}]',
                      'Сравнение гласной у двух дикторов.',
                      [('Диктор 1', self.vowels[label]), ('Диктор 2', second_id)],
                      'Медиана F₀ и огибающая представлены на общей временной шкале.')

    def consonant(self, syllable_id, label, key, lab, task):
        x, rate, _ = self.signal(syllable_id)
        # Detect the first stable spectral envelope resembling the last vowel.
        size, hop = round(rate*.02), round(rate*.005)
        frames = np.lib.stride_tricks.sliding_window_view(x, size)[::hop]
        power = abs(np.fft.rfft(frames*np.hanning(size), axis=1))
        freqs = np.fft.rfftfreq(size, 1/rate)
        bands = np.array([power[:, (freqs>=a)&(freqs<b)].sum(axis=1)
                          for a,b in zip([150,400,800,1500,2500,4000],[400,800,1500,2500,4000,7500])]).T
        norm = bands / np.maximum(np.linalg.norm(bands, axis=1, keepdims=True),1e-10)
        target = np.mean(norm[max(0,len(norm)*3//5):max(1,len(norm)*4//5)],axis=0)
        target /= max(np.linalg.norm(target),1e-10)
        scores = norm @ target
        start, end = .035, min(.15,len(x)/rate*.38)
        for i in range(round(.06/.005), min(len(scores)-3, round(.23/.005))):
            if np.min(scores[i:i+3])>.94:
                end = max(.07, i*.005);break
        return self.crop(syllable_id, start, max(start+.025,end), key, label, lab, task, 'phoneme', label)

    def run6(self):
        word_ids = self.split(self.records['words'], ['Саша','кушал','кашу'], 'word', 6, '6-words', 'word')
        word_signals = []
        for clip_id in word_ids:
            x, rate, _ = self.signal(clip_id)
            word_signals.append(audio.resample(x, round(len(x)*32000/rate)))
        permutations = []
        for number, order in enumerate(itertools.permutations(range(3)),1):
            names = [self.signal(word_ids[i])[2]['title'] for i in order]
            n = self.assemble('permutation-'+str(number), [word_ids[i] for i in order], 6, '6-words',
                              ' · '.join(names), gap_ms=90, text=' '.join(names))
            permutations.append((' '.join(names), n))
        self.case('6-01-permutations', 6, '2.2.1 · Шесть перестановок отдельных слов',
                  'Слова записаны раздельно и собраны во всех порядках; в исходниках каждого слова сохранена его собственная интонация.',
                  list(zip(['Отдельно: Саша','Отдельно: кушал','Отдельно: кашу'],word_ids))+permutations,
                  'Пауза между словами во всех сборках — 90 мс.',
                  ['6 перестановок','Пауза 90 мс'])
        stress_ids = self.split(self.records['stress'], ['САША кушал кашу','Саша КУШАЛ кашу','Саша кушал КАШУ'],
                                'stress-phrase',6,'6-stress',gap=.3)
        for group, phrase_id in enumerate(stress_ids):
            x, rate, _ = self.signal(phrase_id)
            at32 = audio.resample(x, round(len(x)*32000/rate))
            bounds = align_words(word_signals, at32, 32000)
            regions=[{'label':label,'start':a,'end':b} for label,(a,b) in zip(['Саша','кушал','кашу'],bounds)]
            storage.update(phrase_id,{'regions':regions})
            pieces=[self.crop(phrase_id,a,b,f'stress-word-{group}-{i}',label,6,'6-stress','word',label)
                    for i,(label,(a,b)) in enumerate(zip(['Саша','кушал','кашу'],bounds))]
            variants=[]
            for number,order in enumerate(itertools.permutations(range(3)),1):
                label=' '.join(['Саша','кушал','кашу'][i] for i in order)
                n=self.assemble(f'stress-order-{group}-{number}',[pieces[i] for i in order],6,'6-stress',
                                f'Ударение {group+1}: {label}',text=label)
                variants.append((label,n))
            self.case(f'6-02-stress-{group}',6,f'2.2.1 · Перестановки цельной фразы: ударение {group+1}',
                      'Фраза произнесена целиком; слова переставлены после записи. Исходная просодия каждого фрагмента сохранена.',
                      [('Исходная цельная фраза',phrase_id)]+variants,
                      'Границы слов оценены выравниванием с раздельно записанными словами (DTW по спектральным признакам). '
                      'Переходы на стыках приблизительны.',
                      [f'Исходное ударение: слово {group+1}','6 порядков слов'])
        intonation_ids=self.split(self.records['intonation'], ['Утверждение','Незавершённость','Вопрос','Восклицание'],
                                  'intonation',6,'6-intonation',gap=.5)
        self.case('6-03-intonation',6,'2.2.2 · Четыре естественные интонации',
                  'Естественные записи утверждения, незавершённой фразы, вопроса и восклицания.',
                  list(zip(['Завершённость','Незавершённость с продолжением','Вопрос','Восклицание'],intonation_ids)),
                  'Контуры получены из реального сигнала. Тип интонации указан по заданию записи, а не определён автоматически.')
        self.case('6-04-emotions',6,'2.2.2 · Эмоциональная окраска',
                  'Одна фраза, произнесённая с разными эмоциональными установками.',
                  list(self.session['emotions'].items()),
                  'Сопоставление F₀, энергии, длительности и пауз четырёх вариантов одной фразы.')
        self.case('6-04-own-phrases',6,'2.2.2 · Дополнительные фразы: вопрос, восклицание, перечисление',
                  'Другие естественные фразы из записанного материала: разные тексты и интонационные структуры.',
                  [(p['text'],p['source']) for p in self.session['phrases']],
                  'Кроме интонации здесь меняется сам текст. Сравнение служит дополнительным наблюдением, '
                  'а чистое сравнение четырёх интонаций выполнено на фразе «Саша кушал кашу».')
        source=self.records['neutral']
        regions=self.session['neutral_words']
        storage.update(source,{'regions':regions})
        x,rate,_=self.signal(source)
        # Keep a small leading margin to retain the weak [с] in «Студент».
        left,right=round(regions[0]['start']*rate),round(regions[-1]['end']*rate)
        neutral=self.crop(source,left/rate,right/rate,'neutral-trim','Студент писал реферат — исходник',6,'6-contours')
        base=x[left:right]
        for kind, ending in [('Утверждение',-3),('Вопрос',4)]:
            for word,region in enumerate(regions):
                a,b=round(region['start']*rate)-left,round(region['end']*rate)-left
                for mode in ['bend','pitch']:
                    if mode=='bend':
                        params={'start':a/rate,'end':b/rate,'pitch_start':0,'pitch_mid':4,'pitch_end':ending}
                    else:
                        params={'start':a/rate,'end':b/rate,'pitch_start':0,'pitch_mid':4,'pitch_end':ending}
                    y,_=audio.process(base,rate,'pitch_contour' if mode=='pitch' else mode,params)
                    pitch_id=self.save(f'prosody-{kind}-{word}-{mode}',y,rate,6,'6-contours',
                                       f'{kind} · {region["label"]} · {mode}',neutral,params=params)
                    # Recompute the selected word's duration after Pitch Bend.
                    length_change=len(y)-len(base)
                    new_b=b+length_change
                    gain={'start':a/rate,'end':new_b/rate,'gain_start':0,'gain_mid':6,'gain_end':0}
                    z,_=audio.process(y,rate,'gain',gain)
                    gain_id=self.save(f'prosody-gain-{kind}-{word}-{mode}',z,rate,6,'6-contours',
                                      f'{kind} · {region["label"]} · усиление',pitch_id,params=gain)
                    duration={'start':a/rate,'end':new_b/rate,'factor':1.35}
                    w,_=audio.process(z,rate,'stretch',duration)
                    time_id=self.save(f'prosody-time-{kind}-{word}-{mode}',w,rate,6,'6-contours',
                                      f'{kind} · {region["label"]} · длительность',gain_id,params=duration)
                    storage.update(time_id,{'regions':[{'label':region['label'], 'start':a/rate,
                                                       'end':(a+round((new_b-a)*1.35))/rate}]})
                    self.case(f'6-05-{kind}-{word}-{mode}',6,
                              f'2.3 · {kind}: «{region["label"]}» · {"Pitch Bend" if mode=="bend" else "Pitch Shift"}',
                              'Поэтапное изменение тона, громкости и длительности выделенного слова на копиях нейтральной фразы.',
                              [('Нейтральный исходник',neutral),('Изменён тон',pitch_id),
                               ('Добавлен контур громкости',gain_id),('Ударный участок удлинён',time_id)],
                              'Это обработка выбранного участка; название «вопрос»/«утверждение» обозначает целевой вариант опыта. '
                              'Оба способа задают переменный контур; '
                              'в варианте Pitch Shift длина слова восстановлена фазовым вокодером. Параметры и промежуточные результаты сохранены.',
                              ['Громкость: 0 → +6 → 0 дБ','Длительность × 1,35'],
                              json.dumps({'pitch':params,'gain':gain,'stretch':duration},ensure_ascii=False,indent=2))

    def run7(self):
        ids=self.split(self.records['extra_syllables'],self.session['extra_syllable_labels'],
                       'extra-syllable',7,'7-syllables','syllable')
        storage.update(self.records['extra_syllables'],
                       {'title':'Слоговая база','text':'… '.join(self.session['extra_syllable_labels'])+'…'})
        self.syllables.update(dict(zip(self.session['extra_syllable_labels'],ids)))
        self.syllables['а']=self.vowels['а']
        self.syllables['и']=self.vowels['и']
        for number,phrase in enumerate(self.session['phrases'],1):
            source=phrase['source']
            storage.update(source,{'text':phrase['text']})
            reference,rate,_=self.signal(source)
            # Preserve low-energy consonants; trim only outer recording margins.
            spans=detect_segments(reference,rate,gap=.7,threshold=.0105,minimum=.05)
            # The original reference must include quiet unvoiced onsets too.
            # Keep it complete; detected activity is used only as a rhythm hint.
            ref_id=self.crop(source,0,len(reference)/rate,f'reference-full-{number}',f'Эталон {number}: {phrase["text"]}',7,'7-reference','reference',phrase['text'])
            phoneme_parts=[]
            for index,token in enumerate(phrase['phonemes'].split()):
                if token in ['/','//']:
                    phoneme_parts.append(.07 if token=='/' else .22);continue
                prototype=self.phonemes[token]
                x,r,_=self.signal(prototype)
                duration=.17 if token in self.vowels else .085
                count=min(len(x),round(r*duration));left=max(0,(len(x)-count)//2)
                n=self.crop(prototype,left/r,(left+count)/r,'unit-'+token,f'Единица [{token}]',7,'7-phonemes','phoneme',token)
                phoneme_parts.append(n)
            raw=self.assemble(f'phoneme-phrase-{number}',phoneme_parts,7,'7-phonemes',
                              f'Фонемы {number}: {phrase["text"]}',text=phrase['text'])
            # Improve boundaries and loudness while using the same phonetic base.
            adjusted=[]
            for part in phoneme_parts:
                if isinstance(part,float):adjusted.append(part);continue
                x,r,row=self.signal(part)
                y=self.normalize(x,.5)
                ramp=min(round(r*.003),len(y)//3)
                if ramp:
                    y[:ramp]*=np.linspace(0,1,ramp);y[-ramp:]*=np.linspace(1,0,ramp)
                adjusted.append(self.save('smooth-unit-'+str(part),y,r,7,'7-edit',row['title']+' · обработка',part,
                                          kind='phoneme',params={'peak_normalization':.5,'edge_fade_ms':3}))
            improved=self.assemble(f'phoneme-improved-{number}',adjusted,7,'7-edit',
                                   f'Фонемы после обработки {number}',fade_ms=3,text=phrase['text'])
            syllable_parts=[]
            for token in phrase['syllables'].split():
                if token in ['/','//']:
                    syllable_parts.append(.07 if token=='/' else .22);continue
                syllable_parts.append(self.syllables[token])
            syllable=self.assemble(f'syllable-phrase-{number}',syllable_parts,7,'7-syllables',
                                   f'Слоги {number}: {phrase["text"]}',fade_ms=5,text=phrase['text'])
            shaped=[];syllable_index=0
            natural_duration=sum(b-a for a,b in spans) if spans else self.signal(ref_id)[2]['duration']
            target_duration=max(.14,min(.35,natural_duration/max(1,len([p for p in syllable_parts if isinstance(p,int)]))))
            for token,part in zip(phrase['syllables'].split(),syllable_parts):
                if isinstance(part,float):shaped.append(part);continue
                x,r,row=self.signal(part)
                # Shorten pauses inside isolated recordings before the time change.
                pad=round(r*.035);core=x[pad:-pad] if len(x)>pad*3 else x
                stressed=syllable_index in phrase['stress']
                target=target_duration*(1.2 if stressed else .85)
                y=audio.stretch(core,target*r/len(core))
                y=self.normalize(y,.55 if stressed else .38)
                end_tone=3 if phrase['intonation']=='question' else -2
                tones={'pitch_start':0,'pitch_mid':3 if stressed else 0,'pitch_end':end_tone if syllable_index>=phrase['stress'][-1] else 0}
                y,_=audio.process(y,r,'bend',tones)
                n=self.save(f'shaped-syllable-v2-{number}-{syllable_index}',y,r,7,'7-prosody',
                            f'{token} · просодия {number}',part,kind='syllable',params={'target_duration':target,
                             'stressed':stressed,**tones})
                shaped.append(n);syllable_index+=1
            prosody=self.assemble(f'prosody-syllable-phrase-v2-{number}',shaped,7,'7-prosody',
                                  f'Слоги с просодией {number}',fade_ms=5,text=phrase['text'])
            self.case(f'7-0{number}-phrase',7,f'3.3 · Фраза {number}: {phrase["text"]}',
                      'Сравнение естественного эталона с компиляцией из фонем, обработанной фонемной сборкой, '
                      'независимо записанными слогами и слоговой сборкой с просодией.',
                      [('Естественный эталон',ref_id),('Сборка из фонем',raw),('Фонемы: обработка стыков',improved),
                       ('Сборка из слогов',syllable),('Слоги: обработка просодии',prosody)],
                      'Транскрипция учебная, в шестигласной системе методички; безударные о/е переданы а/и, '
                      'мягкость обозначена апострофом. Слоги записаны отдельно от эталонов.',
                      ['5 вариантов','Склейка: 0 / 3 / 5 мс'],
                      'Фонемы: гласные до 170 мс, согласные до 85 мс; паузы 70/220 мс. '
                      'Обработка стыков: нормировка пика до 0,5, огибающие 3 мс. '
                      'Просодия слогов: разные длительности и амплитуды ударных/безударных участков; переменный Pitch Bend.',
                      '['+phrase['phonemes']+'] · слоги: '+phrase['syllables'])

    def finish(self):
        from .presentation import publish_results, conclusions
        publish_results()
        for lab, text in conclusions().items():
            if not storage.notes(lab):
                storage.notes(lab,text)
        print('Результаты опытов сохранены.',flush=True)


def run(path=None):
    path=Path(path) if path else Path(__file__).with_name('session.json')
    session=json.loads(path.read_text(encoding='utf-8'))
    runner=Runner(session)
    runner.run5();runner.run6();runner.run7();runner.finish()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Выполнить опыты на сохранённой записи сессии')
    parser.add_argument('--session',default=None)
    run(parser.parse_args().session)
