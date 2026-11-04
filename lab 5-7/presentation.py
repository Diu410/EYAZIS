"""Laboratory terminology and concise presentation of the experimental results."""
from contextlib import closing
import json

from db import connect
from . import storage


SYNTHESIS_CONCLUSION = (
    'Фонемная компиляция характеризуется прерывистым и роботизированным звучанием. '
    'Сглаживание стыков уменьшает разрывы, но полностью не устраняет роботизированность. '
    'Слоговая компиляция звучит значительно естественнее и наиболее близка к эталону. '
    'Применённая обработка просодии не улучшила звучание: её результат по слуховой оценке '
    'сопоставим с фонемной сборкой и уступает необработанной слоговой компиляции.'
)


def parameter_text(value):
    """Convert stored processing parameters to units and stage names."""
    try:
        stages = json.loads(value)
    except (ValueError, TypeError):
        return value
    if not isinstance(stages, dict) or 'pitch' not in stages:
        return value
    p, g, t = stages['pitch'], stages['gain'], stages['stretch']
    return (
        f'Участок изменения тона: {p["start"]:.3f}–{p["end"]:.3f} с.\n'
        f'Контур тона: {p.get("pitch_start",0):+g} → {p.get("pitch_mid",0):+g} → {p.get("pitch_end",0):+g} полутонов.\n'
        f'Контур усиления: {g["gain_start"]:+g} → {g["gain_mid"]:+g} → {g["gain_end"]:+g} дБ.\n'
        f'Множитель длительности: {t["factor"]:g}.'
    )


def clean_case(case):
    data = dict(case)
    key = data['key']
    descriptions = {
        '5-01-quality': ('Частоты дискретизации 4, 8, 16 и 32 кГц; разрядность PCM 8 и 16 бит.',
                         'Варианты получены ресемплингом единой записи и равномерным квантованием. '
                         'Размер PCM при постоянной длительности пропорционален частоте дискретизации и разрядности.'),
        '5-02-vowel-': ('Изолированная гласная, один период устойчивого участка и его циклическое повторение.',
                        'Длительность периода определена по оценке F₀. Циклический сигнал содержит 120 повторений выбранного периода.'),
        '5-03-iotated': ('Сочетания [йа], [йо], [йу] и [йэ].',
                         'Исследуются начальный переход [й] и последующий гласный участок. Внешние границы выделены по огибающей сигнала.'),
        '5-04-fricative-': ('Изолированный фрикативный согласный, слог, согласный участок слога и циклический фрагмент.',
                            'Повторение шумового участка длительностью 10 мс создаёт искусственную периодичность 100 Гц. '
                            'Внутрислоговая граница согласного приближённая.'),
        '5-05-coart-': ('Изолированный согласный, слог с гласным [а], начальный участок слога и его циклический фрагмент.',
                        'Переходные участки отражают совместную артикуляцию согласного и гласного. '
                        'Вырезанное начало слога сохраняет влияние контекста.'),
        '5-06-pairs': ('Твёрдые и мягкие согласные в слогах с гласными [а] и [и].',
                       'Материал различается как мягкостью согласных, так и гласным контекстом.'),
        '5-06-pair-': ('Твёрдый и мягкий согласные: целый слог, начальный участок и повтор фрагмента 10 мс.',
                       'Периодичность создана циклическим повторением выбранного участка. Границы согласных приближённые.'),
        '5-06-unpaired-': ('Непарный согласный и циклическое повторение его короткого участка.',
                           'Повтор фрагмента 10 мс формирует искусственный периодический сигнал.'),
        '5-07-speaker-': ('Сопоставление одной гласной у двух дикторов.',
                          'Показаны осциллограммы, оценки F₀ и RMS на общей временной шкале.'),
        '6-01-permutations': ('Шесть порядков слов «Саша», «кушал», «кашу», записанных раздельно.',
                              'Каждый компонент сохраняет просодические характеристики своей исходной записи. '
                              'Межсловная пауза составляет 90 мс.'),
        '6-02-stress': ('Цельные фразы с ударением на первом, втором и третьем слове и перестановкой ударного компонента.',
                        'После перестановки сохраняются исходные просодические характеристики фрагментов. '
                        'Границы слов приближённо определены DTW-выравниванием спектральных признаков.'),
        '6-03-intonation': ('Завершённость, незавершённость, вопрос и восклицание во фразе «Саша кушал кашу».',
                            'Контуры F₀ и RMS рассчитаны по естественным записям четырёх интонационных вариантов.'),
        '6-04-emotions': ('Монотонное произнесение, радость, гордость и огорчение.',
                          'Для четырёх вариантов одной фразы сопоставлены длительность, F₀ и RMS.'),
        '6-05-': ('Изменение тона, усиление и длительность ударного слова в нейтральной фразе «Студент писал реферат».',
                   'Pitch Bend изменяет тон и длительность; контур Pitch Shift сохраняет длину слова. '
                   'Усиление задано контуром 0 → +6 → 0 дБ; длительность ударного участка увеличена в 1,35 раза.'),
        '7-0': ('Естественный эталон, фонемная компиляция, обработка стыков, слоговая компиляция и обработка её просодии.',
                 'Учебная транскрипция использует шестигласную систему: безударные о/е переданы а/и, мягкость обозначена апострофом. '
                 'Слоги записаны независимо от эталонных фраз.'),
    }
    for prefix, (description, finding) in descriptions.items():
        if key == prefix or key.startswith(prefix):
            data['description'], data['finding'] = description, finding
            break
    data['recipe'] = parameter_text(data.get('recipe', ''))
    if key.startswith('6-05-word-'):
        data['recipe'] = ('Нейтральная фраза → контур тона → усиление 0/+6/0 дБ → растяжение ударного участка × 1,35.\n'
                          'Целевой контур утверждения: 0/+4/−3 полутона; вопроса: 0/+4/+4 полутона.\n'
                          'Промежуточные этапы сохранены в аудиоматериалах и измерениях отчёта.')
        data['metrics'] = []
    if key.startswith('7-0'):
        data['metrics'] = []
    return data


def compact_lab6(cases):
    """Keep the required comparisons; retain intermediate WAVs through provenance."""
    by_key = {c['key']: c for c in cases}
    old_stress = [c for c in cases if c['key'].startswith('6-02-stress-')]
    old_prosody = [c for c in cases if c['key'].startswith('6-05-') and '-word-' not in c['key']]
    if not old_stress and not old_prosody:
        return cases
    output = []
    if '6-01-permutations' in by_key:
        case = dict(by_key['6-01-permutations'])
        if len(case['items']) == 9:
            case['items'] = case['items'][3:]
        output.append(case)
    if old_stress:
        items, comments = [], []
        for i, variant_index in enumerate([4, 2, 5]):
            case = by_key[f'6-02-stress-{i}']
            name = ['Саша', 'кушал', 'кашу'][i]
            items += [{**case['items'][0], 'role': f'Ударение «{name}»: исходник'},
                      {**case['items'][variant_index], 'role': f'Ударение «{name}»: перестановка'}]
            if case.get('observations'):
                comments.append(case['title']+'\n'+case['observations'])
        old = by_key.get('6-02-stress', {})
        output.append({'key':'6-02-stress', 'lab':6, 'title':'2.2.1 · Фразовое ударение и перестановка слов',
                       'items':items, 'description':'', 'finding':'', 'recipe':'', 'metrics':[],
                       'observations':old.get('observations') or '\n\n'.join(comments)})
    for key in ['6-03-intonation', '6-04-emotions']:
        if key in by_key:
            case = dict(by_key[key])
            if key == '6-03-intonation' and '6-04-own-phrases' in by_key:
                case['supporting_ids'] = [i['id'] for i in by_key['6-04-own-phrases']['items']]
            output.append(case)
    if old_prosody:
        for word in range(3):
            items = []
            comments = []
            for intonation in ['Утверждение', 'Вопрос']:
                for mode in ['bend', 'pitch']:
                    case = by_key[f'6-05-{intonation}-{word}-{mode}']
                    if not items:
                        items.append(case['items'][0])
                    items.append({**case['items'][-1], 'role': f'{intonation} · {"Pitch Bend" if mode=="bend" else "Pitch Shift"}'})
                    if case.get('observations'):
                        comments.append(case['title']+'\n'+case['observations'])
            key = f'6-05-word-{word}'
            old = by_key.get(key,{})
            output.append({'key':key, 'lab':6, 'title':f'2.3 · Просодия: ударение на «{["Студент","писал","реферат"][word]}»',
                           'items':items, 'description':'', 'finding':'', 'recipe':'', 'metrics':[],
                           'observations':old.get('observations') or '\n\n'.join(comments)})
    return output


def publish_results():
    """Update report language and grouping without changing audio or measurements."""
    cases = storage.experiments()
    grouped = [c for c in cases if c['lab'] != 6] + compact_lab6([c for c in cases if c['lab']==6])
    cleaned = [clean_case(c) for c in grouped]
    with closing(connect()) as db, db:
        db.execute('DELETE FROM speech_experiments')
        for case in cleaned:
            data = {k:v for k,v in case.items() if k not in ('key','lab','observations')}
            db.execute('INSERT INTO speech_experiments(key,lab,data,observations) VALUES (?,?,?,?)',
                       (case['key'],case['lab'],json.dumps(data,ensure_ascii=False),case.get('observations','')))
    for row in storage.list_clips():
        if row['notes'].startswith(('Фрагмент выделен по огибающей','Слог выделен по огибающей')):
            source = row['provenance'].get('source_id')
            storage.update(row['id'],{'notes':f'Сегмент исходной записи №{source}. Границы приближённо определены по огибающей сигнала.'})


def conclusions(synthesis_assessment=''):
    return {
        5: ('Частота дискретизации определяет полосу сохраняемых частот, разрядность — шаг квантования и объём PCM. '
            'Варианты качества получены пересчётом одной исходной записи.\n\n'
            'Для гласных выделены устойчивые периоды и сформированы циклические сигналы. '
            'Повторение участка согласного длительностью 10 мс создаёт искусственную периодичность 100 Гц.\n\n'
            'Разделение согласного и гласного внутри слога приближённое вследствие коартикуляции. '
            'В сопоставлении твёрдых и мягких согласных различается также гласный контекст. '
            'Голосовые характеристики двух дикторов сопоставлены по F₀, RMS и осциллограммам.'),
        6: ('Сформированы шесть перестановок отдельно записанных слов и варианты перестановки слов цельных фраз '
            'с ударением на разных компонентах. При перестановке сохраняется исходная просодия каждого фрагмента.\n\n'
            'Рассмотрены четыре интонационных и четыре эмоциональных варианта. '
            'Для нейтральной фразы изменены тон, громкость и длительность каждого из трёх ударных слов.\n\n'
            'Pitch Bend изменяет тон вместе с длительностью, контур Pitch Shift сохраняет число отсчётов. '
            'Максимум усиления составляет +6 дБ, множитель длительности — 1,35. '
            'Просодические характеристики определяются совместным действием мелодики, энергетики и ритмики.'),
        7: ((synthesis_assessment+'\n\n' if synthesis_assessment else '')+
            'Слоговые единицы сохраняют внутрислоговые артикуляционные переходы. '
            'Сглаживание стыков само по себе не восстанавливает утраченный контекст. '
            'Применённые преобразования тона и времени могут вносить дополнительные артефакты.\n\n'
            'Для синтеза с неограниченным словарём необходимы нормализация текста, определение ударений, '
            'автоматическая транскрипция, контекстный выбор аллофонов или дифонов, модель просодии и полная фонетическая база.')
    }
