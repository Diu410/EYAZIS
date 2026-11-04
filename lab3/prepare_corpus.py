"""Build equal-length original educational documents offline, without truncation.

Complete supplementary sentences are selected to reach the common editorial
length. No whitespace padding or repeated paragraphs are used. The choice uses
only character count, never the summarizer or its scores.
"""
import json
from pathlib import Path

ROOT = Path(__file__).with_name('corpus')
TARGET_CHARACTERS = 4500
SUPPLEMENTS = {
    ('ru', 'computer science'): [
        'При оценке алгоритмов важно различать размер входа и величину самих чисел.',
        'Каждая проверка счётчика должна соответствовать одному обращению к элементу.',
        'Сравнение разных программ требует одинакового определения измеряемой операции.',
        'Границы массива включаются в текущий диапазон поиска.',
        'После неудачного сравнения средний элемент исключается из следующего диапазона.',
        'Это правило предотвращает зацикливание на диапазоне длиной один элемент.',
        'Пустой массив должен обрабатываться без обращения к несуществующему индексу.',
        'Повторяющиеся значения требуют отдельного соглашения о возвращаемой позиции.',
        'Поиск любого совпадения отличается от поиска первого совпадения.',
        'При изменении этого соглашения эксперимент необходимо повторить.',
        'Сортировка является свойством входных данных, а не результатом поиска.',
        'Успешный тест не доказывает корректность программы для всех возможных массивов.',
        'Инвариант диапазона позволяет объяснить сохранение всех допустимых кандидатов.',
        'После каждого шага длина непустого диапазона строго уменьшается.',
        'Поэтому число шагов конечно при любом допустимом входе.',
        'Счётчик операций следует обнулять перед каждым независимым запросом.',
        'Подготовка данных не должна включаться в число сравнений самого поиска.',
        'Для оценки полного сервиса затраты подготовки, напротив, необходимо учитывать.',
        'Распределение запросов определяет практическую значимость худшего случая.',
        'Преимущество метода не следует переносить на другие структуры хранения.',
        'Связный список не обеспечивает постоянную стоимость доступа к середине.',
        'Именно массив позволяет непосредственно обращаться к выбранной позиции.',
        'Результаты удобно представлять таблицей размеров и числа проверок.',
        'График дополняет таблицу и показывает различие темпов роста.',
        'Отдельный журнал проверок помогает обнаружить ошибку в обновлении границ.'
    ],
    ('de', 'computer science'): [
        'Die Größe der Eingabe ist von der Größe einzelner Zahlen zu unterscheiden.',
        'Jeder Zählerschritt muss genau einer Prüfung eines Elements entsprechen.',
        'Vergleichbare Programme benötigen dieselbe Definition einer gemessenen Operation.',
        'Beide Grenzen gehören zum aktuellen Suchbereich.',
        'Nach einem erfolglosen Vergleich wird das mittlere Element ausgeschlossen.',
        'Diese Regel verhindert eine Endlosschleife bei einem einzelnen Kandidaten.',
        'Ein leeres Feld darf keinen Zugriff auf einen ungültigen Index auslösen.',
        'Doppelte Werte verlangen eine Festlegung der zurückgegebenen Position.',
        'Die Suche nach irgendeinem Treffer unterscheidet sich von der Suche nach dem ersten.',
        'Bei einer Änderung dieser Festlegung muss das Experiment wiederholt werden.',
        'Die Sortierung ist eine Voraussetzung und kein Ergebnis der Suchoperation.',
        'Ein erfolgreicher Test beweist keine Korrektheit für sämtliche Eingaben.',
        'Die Bereichsinvariante erklärt den Erhalt aller möglichen Kandidaten.',
        'Nach jedem Schritt wird der nichtleere Suchbereich strikt kleiner.',
        'Damit endet die Suche für jede zulässige Eingabe nach endlich vielen Schritten.',
        'Vor jeder unabhängigen Anfrage wird der Operationszähler zurückgesetzt.',
        'Die Vorbereitung gehört nicht zur Zahl der Vergleiche während der Suche.',
        'Für einen vollständigen Dienst müssen Vorbereitungskosten dennoch erfasst werden.',
        'Die Verteilung der Anfragen bestimmt die Bedeutung des ungünstigsten Falls.',
        'Ein Vorteil darf nicht ohne Prüfung auf andere Speicherstrukturen übertragen werden.',
        'Eine verkettete Liste erlaubt keinen unmittelbaren Zugriff auf die Mitte.',
        'Ein Feld ermöglicht dagegen den direkten Zugriff auf eine gewählte Position.',
        'Eine Tabelle verbindet die Eingabegrößen mit den beobachteten Prüfungszahlen.',
        'Ein Diagramm ergänzt die Tabelle und verdeutlicht das unterschiedliche Wachstum.',
        'Ein Prüfprotokoll hilft dabei, fehlerhafte Änderungen der Grenzen zu erkennen.'
    ],
    ('ru', 'литература'): [
        'Нравственное испытание героя нельзя отделить от его отношений с окружающими.',
        'Читатель замечает расхождение между заявленным намерением и реальным действием.',
        'Это расхождение поддерживает напряжение на протяжении повествования.',
        'Психологическая деталь часто оказывается убедительнее общего рассуждения.',
        'Страх разоблачения показывает зависимость от оценки других людей.',
        'Но желание признания не сводится только к страху юридического наказания.',
        'Герою необходим собеседник, способный услышать его без оправдания насилия.',
        'Встреча с таким собеседником не снимает личной ответственности.',
        'Сочувствие и нравственная оценка оказываются совместимыми.',
        'Их соединение противопоставлено равнодушному делению людей на разряды.',
        'Название произведения связывает поступок с его длительными последствиями.',
        'Наказание существует не только как внешнее решение суда.',
        'Внутренний разлад проявляется ещё до окончательного признания.',
        'Поэтому последовательность переживаний имеет значение для понимания сюжета.',
        'Повторяющиеся встречи возвращают героя к вытесняемому вопросу о другом человеке.',
        'Диалог делает видимым то, что одиночное рассуждение пытается скрыть.',
        'Готового решения нельзя достичь простым повторением чужих слов.',
        'Необходим собственный выбор, подтверждённый последующим поведением.',
        'Человеческое достоинство в таком прочтении не зависит от социальной полезности.',
        'Именно поэтому теория исключительности обнаруживает нравственную несостоятельность.',
        'Образ будущего оставляет пространство для надежды и дальнейшего труда.',
        'Открытость финала требует осторожности при окончательной оценке героя.',
        'Сочинение предлагает интерпретацию, а не единственно возможное прочтение романа.',
        'Другие прочтения могут подробнее рассматривать социальные причины конфликта.',
        'Для проверки интерпретации следует возвращаться к поступкам и диалогам персонажей.'
    ],
    ('de', 'литература'): [
        'Die moralische Prüfung bleibt mit den Beziehungen des Helden verbunden.',
        'Der Leser erkennt den Abstand zwischen erklärter Absicht und wirklicher Handlung.',
        'Dieser Abstand erhält die Spannung innerhalb der Erzählung.',
        'Ein psychologisches Detail überzeugt oft stärker als eine allgemeine Behauptung.',
        'Die Angst vor Entdeckung zeigt die Abhängigkeit vom Urteil anderer Menschen.',
        'Das Bedürfnis nach Anerkennung geht aber über die Angst vor Strafe hinaus.',
        'Der Held braucht ein Gegenüber, das zuhört, ohne Gewalt zu rechtfertigen.',
        'Eine solche Begegnung hebt persönliche Verantwortung nicht auf.',
        'Mitgefühl und moralische Beurteilung schließen sich nicht gegenseitig aus.',
        'Ihre Verbindung widerspricht einer gleichgültigen Einteilung der Menschen.',
        'Der Titel verbindet eine Handlung mit ihren anhaltenden Folgen.',
        'Strafe besteht nicht allein in der äußeren Entscheidung eines Gerichts.',
        'Die innere Zerrissenheit wird schon vor dem endgültigen Geständnis sichtbar.',
        'Deshalb ist die Reihenfolge der Erfahrungen für das Verständnis bedeutsam.',
        'Wiederholte Begegnungen führen zur verdrängten Frage nach dem anderen zurück.',
        'Der Dialog zeigt, was ein einsames Gedankengebäude zu verbergen versucht.',
        'Eine Lösung entsteht nicht durch das bloße Wiederholen fremder Worte.',
        'Nötig ist eine eigene Entscheidung, die durch späteres Handeln bestätigt wird.',
        'Menschliche Würde hängt in dieser Lesart nicht von gesellschaftlichem Nutzen ab.',
        'Gerade deshalb scheitert die Theorie der außergewöhnlichen Berechtigung.',
        'Das Zukunftsbild lässt Raum für Hoffnung und weitere innere Arbeit.',
        'Das offene Ende verlangt Zurückhaltung bei einem abschließenden Urteil.',
        'Der Aufsatz bietet eine Deutung und beansprucht keine einzig mögliche Lesart.',
        'Andere Deutungen können die sozialen Ursachen des Konflikts stärker betonen.',
        'Eine Interpretation muss sich an Handlungen und Gesprächen der Figuren bewähren.'
    ],
}


def equal_length_text(item):
    text = '\n\n'.join(item['paragraphs'])
    remaining = TARGET_CHARACTERS - len(text) - 2
    # The last extra separator is removed by join, hence target remaining + 1.
    states = {0: []}
    for sentence in SUPPLEMENTS[(item['language'], item['subject_area'])]:
        length = len(sentence) + 1
        for count, chosen in list(states.items()):
            if count + length <= remaining + 1:
                states.setdefault(count + length, [*chosen, sentence])
    if remaining + 1 not in states:
        raise ValueError(f"Нельзя выровнять документ полными предложениями: {item['file']}")
    text += '\n\n' + ' '.join(states[remaining + 1])
    assert len(text) == TARGET_CHARACTERS and text.endswith('.')
    return text


def main():
    documents = json.loads((ROOT / 'documents.json').read_text(encoding='utf-8'))
    metadata, annotation = [], []
    for item in documents:
        text = equal_length_text(item)
        for directory in (ROOT, ROOT.parent / 'examples'):
            (directory / item['file']).write_text(text, encoding='utf-8', newline='\n')
        metadata.append({key: item[key] for key in ('file', 'language', 'subject_area', 'title', 'genre')} |
                        {'source_urls': [], 'characters': len(text), 'source': 'corpus/documents.json',
                         'author': 'Учебный авторский материал проекта, подготовлен с помощью ИИ; не внешняя публикация'})
        annotation.append({'file': item['file'], 'language': item['language'],
                           'summary_sentences': [item['paragraphs'][index].split('. ')[0] + '.'
                                                 for index in item['gold_paragraphs']],
                           'keywords': item['gold_keywords']})
    (ROOT / 'sources.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'reference_annotations.json').write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Подготовлены четыре полных документа по 4500 символов и эталонная разметка.')


if __name__ == '__main__':
    main()
