"""Create laboratory reports using the existing Word report as a template."""
from functools import lru_cache
from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from . import audio, storage
from .presentation import SYNTHESIS_CONCLUSION

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'report'
ASSETS=OUT/'assets'
SESSION=json.loads(Path(__file__).with_name('session.json').read_text(encoding='utf-8'))
CASES={c['key']:c for c in storage.experiments()}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,
                     'axes.spines.right':False,'axes.grid':True,'grid.alpha':.22,
                     'savefig.facecolor':'white'})


@lru_cache(maxsize=220)
def signal(clip_id):
    row=storage.get(clip_id)
    x,r,_=audio.decode(row['wav'])
    return x,r,row


@lru_cache(maxsize=160)
def measured(clip_id):
    x,r,_=signal(clip_id)
    return audio.analyze(x,r)


def fmt(value,digits=3):
    return '—' if value is None else f'{value:.{digits}f}'.replace('.',',')


def image_path(name):return ASSETS/(name+'.png')


def savefig(fig,name):
    fig.tight_layout(pad=1.25)
    fig.savefig(image_path(name),dpi=190,bbox_inches='tight')
    plt.close(fig)
    return image_path(name)


def waves(name,items,columns=1,zoom=None):
    rows=(len(items)+columns-1)//columns
    fig,axes=plt.subplots(rows,columns,figsize=(7,1.55*rows),squeeze=False)
    for ax,(label,n) in zip(axes.flat,items):
        x,r,_=signal(n)
        if zoom:
            a,b=zoom;x=x[round(a*r):round(b*r)]
        t=np.arange(len(x))/r
        step=max(1,len(x)//3500)
        ax.plot(t[::step],x[::step],lw=.55,color='#087b89')
        ax.set_title(label,loc='left',fontsize=10)
        ax.set_xlabel('Время, с');ax.set_ylabel('Амплитуда PCM')
        ax.ticklabel_format(axis='y',style='plain',useOffset=False)
    for ax in list(axes.flat)[len(items):]:ax.set_visible(False)
    return savefig(fig,name)


def contours(name,items,columns=1):
    rows=(len(items)+columns-1)//columns
    fig,axes=plt.subplots(rows,columns,figsize=(7,1.8*rows),squeeze=False)
    for ax,(label,n) in zip(axes.flat,items):
        a=measured(n);f=np.array([np.nan if v is None else v for v in a['f0']])
        ax.plot(a['times'],f,lw=1.1,color='#087b89',label='F₀')
        right=ax.twinx();right.grid(False)
        right.plot(a['times'],a['energy'],lw=.85,color='#bd642c',alpha=.85,label='RMS')
        ax.set_ylim(60,500);ax.set_ylabel('F₀, Гц',color='#087b89')
        right.set_ylim(0,max(.01,max(a['energy'])*1.15));right.set_ylabel('RMS',color='#bd642c')
        ax.set_title(label,loc='left',fontsize=9);ax.set_xlabel('Время, с')
    for ax in list(axes.flat)[len(items):]:ax.set_visible(False)
    return savefig(fig,name)


def flow(name,labels):
    fig,ax=plt.subplots(figsize=(7,1.4));ax.set(xlim=(0,len(labels)),ylim=(0,1));ax.axis('off')
    for i,label in enumerate(labels):
        rect=FancyBboxPatch((i+.045,.2),.85,.6,boxstyle='round,pad=.015',facecolor='#eaf4f4',edgecolor='#41858b')
        ax.add_patch(rect);ax.text(i+.47,.5,label,ha='center',va='center',fontsize=9)
        if i<len(labels)-1:ax.annotate('',xy=(i+1.035,.5),xytext=(i+.91,.5),arrowprops={'arrowstyle':'->','color':'#345660'})
    return savefig(fig,name)


def parameter_chain(final_id):
    ids=[final_id]
    while len(ids)<4:
        p=signal(ids[-1])[2]['provenance']
        if 'source_id' not in p:break
        ids.append(p['source_id'])
    return list(reversed(ids))


def accented(phrase):
    vowels=set('аоуэыи');index=0;tokens=[]
    for token in phrase['phonemes'].split():
        if token in vowels:
            if index in phrase['stress']:token+='\u0301'
            index+=1
        tokens.append(token)
    return '[ '+' '.join(tokens)+' ]'


class Report:
    def __init__(self,number):
        self.number=number;self.figure=0;self.table_number=0;self.html=[]
        template=OUT/'Лабораторная работа 4.docx'
        self.doc=Document(template)
        # Preserve the actual title page, margins, footer and page numbering.
        body=self.doc._element.body;cut=False
        for child in list(body):
            text=''.join(child.xpath('.//w:t/text()'))
            if text=='Цель работы:':cut=True
            if cut and child.tag!=qn('w:sectPr'):body.remove(child)
        for p in self.doc.paragraphs:
            for run in p.runs:
                if '№4' in run.text:run.text=run.text.replace('№4',f'№{number}')
        for rid,rel in list(self.doc.part.rels.items()):
            if rel.reltype.endswith('/image'):self.doc.part.drop_rel(rid)
        self.doc.core_properties.title=f'Лабораторная работа №{number}'
        self.doc.core_properties.author='Батук Д.С.; Остров М.А.'
        self.doc.core_properties.subject='Естественно-языковой интерфейс интеллектуальных систем'
        # Matching cover for the printable PDF edition.
        cover=[]
        for p in self.doc.paragraphs:
            cover.append('<p>'+escape(' '.join(p.text.split()))+'</p>')
        self.cover='<section class="cover">'+''.join(cover)+'</section>'

    def heading(self,text):
        p=self.doc.add_paragraph();p.paragraph_format.keep_with_next=True
        p.paragraph_format.space_before=Pt(10);p.paragraph_format.space_after=Pt(6)
        p.add_run(text).bold=True
        self.html.append('<h2>'+escape(text)+'</h2>')

    def para(self,text):
        p=self.doc.add_paragraph(text)
        p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.first_line_indent=Cm(1.25)
        p.paragraph_format.line_spacing=1.0;p.paragraph_format.space_after=Pt(6)
        for r in p.runs:r.font.name='Times New Roman';r.font.size=Pt(14)
        self.html.append('<p>'+escape(text)+'</p>')

    def table(self,title,headers,rows,widths=None):
        self.table_number+=1
        label=f'Таблица {self.table_number} — {title}'
        p=self.doc.add_paragraph(label);p.paragraph_format.keep_with_next=True
        p.paragraph_format.first_line_indent=Cm(0)
        for r in p.runs:r.font.size=Pt(12)
        table=self.doc.add_table(rows=1,cols=len(headers));table.autofit=False
        borders=OxmlElement('w:tblBorders')
        for side in ['top','left','bottom','right','insideH','insideV']:
            edge=OxmlElement('w:'+side);edge.set(qn('w:val'),'single');edge.set(qn('w:sz'),'4');edge.set(qn('w:color'),'777777');borders.append(edge)
        table._tbl.tblPr.append(borders)
        if widths is None:widths=[15.8/len(headers)]*len(headers)
        for column,width in zip(table.columns,widths):column.width=Cm(width)
        for cell,width,text in zip(table.rows[0].cells,widths,headers):cell.width=Cm(width);cell.text=str(text)
        header=OxmlElement('w:tblHeader');table.rows[0]._tr.get_or_add_trPr().append(header)
        for values in rows:
            cells=table.add_row().cells
            for cell,width,value in zip(cells,widths,values):cell.width=Cm(width);cell.text=str(value)
        for index,row in enumerate(table.rows):
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after=Pt(3)
                    paragraph.paragraph_format.space_before=Pt(3)
                    paragraph.paragraph_format.first_line_indent=Cm(0)
                    paragraph.paragraph_format.line_spacing=1.0
                    for run in paragraph.runs:
                        run.font.name='Times New Roman';run.font.size=Pt(10.5);run.bold=index==0
        self.doc.add_paragraph().paragraph_format.space_after=Pt(0)
        self.html.append('<div class="table-label">'+escape(label)+'</div><table><thead><tr>'+''.join('<th>'+escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(v)).replace('\n','<br>')+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>')

    def fig(self,path,caption):
        self.figure+=1
        p=self.doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent=Cm(0);p.paragraph_format.keep_with_next=True
        p.add_run().add_picture(str(path),width=Cm(15.8))
        p=self.doc.add_paragraph(f'Рисунок {self.figure} — {caption}');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent=Cm(0);p.paragraph_format.space_after=Pt(8)
        for r in p.runs:r.font.size=Pt(11)
        self.html.append('<figure><img src="assets/'+escape(path.name)+'"><figcaption>'+escape(f'Рисунок {self.figure} — {caption}')+'</figcaption></figure>')

    def common(self,goal,assignment,algorithm):
        self.heading('Цель работы:');self.para(goal)
        self.heading('Задание:');self.para(assignment)
        self.heading('Структура разработанной системы:')
        self.para('Работа выполнена в локальном приложении EYAZIS на собственных записях речевого сигнала. '
                  'Код лабораторных 5–7 размещён в папке «lab 5-7». app.py обслуживает интерфейс; audio.py выполняет '
                  'обработку и измерения; experiments.py воспроизводит опыты; presentation.py группирует результаты; '
                  'report.py формирует архив материалов. Исходные записи, производные сигналы и параметры сохраняются в SQLite.')
        self.fig(flow(f'lab{self.number}_algorithm',algorithm),'Последовательность обработки речевого сигнала')
        self.heading('Структура базы данных:')
        self.table('Хранение исходников и результатов',['Таблица','Основные данные','Назначение'],[
            ['speech_clips','WAV, частота, разрядность, длительность, диктор, текст, разметка, происхождение','Исходные записи и каждый этап обработки'],
            ['speech_experiments','Ключ опыта, лабораторная, варианты, измерения, слуховая оценка','Группировка сравниваемых результатов'],
            ['speech_notes','Номер лабораторной, выводы','Итоговый анализ']],[3.5,6.7,5.6])
        self.heading('Основные алгоритмы:')
        self.para('Осциллограмма строится по отсчётам PCM, при уменьшении масштаба сохраняются минимумы и максимумы в каждом интервале. '
                  'Уровень сигнала характеризуется RMS = √(Σx²/N). Основной тон F₀ оценивается по максимумам автокорреляции '
                  'в окне Ханна длительностью 40 мс с поправкой на перекрытие. Диапазон поиска — 60–500 Гц; '
                  'неуверенные и изолированные оценки исключаются. В таблицах приведена медиана уверенных кадров, '
                  'поэтому она не является постоянной частотой всей фразы.')
        self.para('Внешние границы изолированных произнесений определены по огибающей энергии. Границы слов цельной фразы '
                  'приближённо оценены DTW-выравниванием спектральных признаков; границы согласного внутри слога — '
                  'по изменению спектральной огибающей. Для одиночного периода, который короче окна анализа, оценка F₀ '
                  'не вычисляется: частота его повтора определяется непосредственно как 1/T.')

    def end(self,analysis,improvements,conclusion):
        self.heading('Анализ полученных данных:')
        for text in analysis:self.para(text)
        self.heading('Предложения по улучшению:');self.para(improvements)
        self.heading('Используемые библиотеки и компоненты:')
        self.para('Python и NumPy — обработка отсчётов, преобразование Фурье и матричные операции; SQLite — хранение WAV и результатов; '
                  'стандартный модуль wave — PCM WAV; HTML и JavaScript — представление опытов; Matplotlib — графики отчёта; '
                  'python-docx — оформление документа. Обработка речевого сигнала выполняется локально.')
        self.heading('Вывод:');self.para(conclusion)
        self.heading('Источники:')
        self.para('1. «Лабораторные работы 5–7». Методические указания «Изучение фонетических, просодических и компиляционных закономерностей речевого сигнала», 19 с.')
        self.para('2. Лобанов Б. М., Елисеева О. Е. Речевой интерфейс интеллектуальных систем: учебное пособие / под науч. ред. В. В. Голенкова. Минск: БГУИР, 2006. 152 с.')
        self.para(f'Электронные материалы: lab{self.number}_materials.zip — аудио WAV, графики SVG, измерения CSV, разметка и параметры обработки в manifest.json.')

    def save(self):
        path=OUT/f'Лабораторная работа {self.number}.docx';self.doc.save(path)
        html='''<!doctype html><html lang="ru"><meta charset="utf-8"><style>
@page{size:A4;margin:25.4mm}body{font:14pt "Times New Roman";line-height:1.08;margin:0}p{text-align:justify;text-indent:12.5mm;margin:0 0 6pt}h2{font-size:14pt;margin:12pt 0 6pt;break-after:avoid}table{width:100%;border-collapse:collapse;font-size:10.5pt;margin-bottom:8pt}th,td{border:1px solid #777;padding:5pt;text-align:left;vertical-align:top}thead{display:table-header-group}tr{break-inside:avoid}.table-label{font-size:12pt;margin:8pt 0 5pt;break-after:avoid}figure{margin:9pt 0;break-inside:avoid}figure img{display:block;width:100%;max-height:205mm;object-fit:contain}figcaption{font-size:11pt;text-align:center;margin-top:5pt}.cover{height:246mm;break-after:page;display:flex;flex-direction:column;justify-content:flex-start}.cover p{text-align:center;text-indent:0;margin:0 0 6pt;min-height:14pt;white-space:pre-wrap}.cover p:nth-child(21),.cover p:nth-child(22),.cover p:nth-child(24){text-align:right;font-size:13pt}.cover p:last-child{margin-top:auto} </style>'''+self.cover+''.join(self.html)+'</html>'
        (OUT/f'lab{self.number}_report.html').write_text(html,encoding='utf-8')
        print(path.name,'tables',self.table_number,'figures',self.figure,flush=True)


def report5():
    r=Report(5)
    r.common('Выявить фонетические закономерности речевого сигнала, исследовать влияние параметров PCM, '
             'периодичность гласных, особенности согласных и коартикуляции.',
             'Сопоставить 4/8/16/32 кГц и 8/16 бит; исследовать гласные, йотированные сочетания, фрикативные, взрывные '
             'и носовые согласные, твёрдые и мягкие варианты; сформировать повторы коротких участков и сравнить двух дикторов.',
             ['Исходный\nPCM WAV','Сегментация\nзвуков','Период /\nкороткий участок','Цикл /\nресемплинг','Осциллограмма\nи измерения'])
    r.para('Снижение частоты дискретизации выполнено ресемплингом Фурье с удалением спектральных составляющих выше новой частоты Найквиста. '
           'Разрядность изменена равномерным квантованием. Эксперимент использует одну исходную запись, а не восемь независимых записей '
           'с различными аппаратными настройками АЦП.')
    r.heading('Результаты экспериментов:')
    r.heading('1.3. Частота дискретизации и разрядность')
    quality=CASES['5-01-quality'];rows=[]
    for item in quality['items']:
        m=item['measurement'];rows.append([item['role'],fmt(m['duration'],4),m['sample_rate'],m['bits'],fmt(m['size_bytes']/1024,2),fmt(m['rms'],4)])
    r.para('Исходная фраза: «Сегодня мы исследуем качество записи речевого сигнала». Запись №4: моно, 48 кГц, 16 бит. '
           'Результирующие длительности отличаются менее чем на один отсчёт целевой частоты вследствие округления числа отсчётов.')
    r.table('Сравнение параметров и объёма WAV',['Вариант','T, с','Гц','Бит','Размер, КиБ','RMS'],rows,[4.2,2.1,2,1.2,3,3.3])
    r.fig(waves('lab5_quality_wave',[(i['role'],i['id']) for i in [quality['items'][0],quality['items'][1],quality['items'][4]]]),
          'Исходник и два варианта с пониженной частотой дискретизации')
    r.para('Для моно PCM полезный объём данных описывается зависимостью V = T·fs·b/8. При одинаковой частоте переход '
           'от 16 к 8 бит уменьшает полезный объём вдвое; заголовок WAV сохраняет небольшой постоянный размер. '
           'Граница спектра составляет соответственно 2, 4, 8 и 16 кГц, а нормированный шаг квантования — 1/128 и 1/32768. '
           'Изменение RMS при снижении частоты объясняется удалением высокочастотных составляющих.')
    vowels=[CASES['5-02-vowel-'+v] for v in 'аоуэыи'];rows=[]
    for c,v in zip(vowels,'аоуэыи'):
        original,period,loop=c['items'];m=original['measurement'];t=period['measurement']['duration']
        rows.append([v,fmt(m['duration']),fmt(m['median_f0'],2),fmt(1000*t,3),fmt(1/t,2),fmt(loop['measurement']['median_f0'],2)])
    r.heading('1.4.1. Гласные и йотированные сочетания')
    r.table('Периоды гласных и частоты повторения',['Гласная','T записи, с','F₀, Гц','Период, мс','1/T, Гц','F₀ цикла, Гц'],rows,[1.7,2.8,2.8,2.9,2.8,2.8])
    r.fig(waves('lab5_vowels',[(f'[{v}]',SESSION['vowel_clips'][v]) for v in 'аоуэыи'],2),'Осциллограммы шести гласных')
    a=CASES['5-02-vowel-а']['items']
    r.fig(waves('lab5_period_a',[('Устойчивый участок [а]',a[0]['id'])],zoom=(.5,.55)), 'Периодическая структура гласной [а], увеличенный участок')
    r.fig(waves('lab5_period_loop',[(i['role'],i['id']) for i in a[1:]]),'Один период [а] и его 120-кратный повтор')
    r.para('Оценки F₀ шести гласных находятся приблизительно в диапазоне 103–111 Гц. Длительности выбранных периодов '
           'составляют около 9–10 мс. Частота искусственного цикла близка к медиане исходной гласной; небольшое отличие '
           'связано с округлением периода до целого числа отсчётов. Один короткий период не получает самостоятельную оконную оценку F₀.')
    iotated=CASES['5-03-iotated']
    r.fig(waves('lab5_iotated',[(i['role'],i['id']) for i in iotated['items']],2),'Сочетания [йа], [йо], [йу], [йэ]')
    r.para('Буквы я, ё, ю, е в изолированном произнесении представлены сочетанием [й] и гласного. '
           'В опыте сохранён начальный переход и последующий устойчивый участок. Это не четыре дополнительные простые гласные фонемы.')
    r.heading('1.4.2. Фрикативные согласные')
    rows=[]
    for v in 'фсшх':
        c=CASES['5-04-fricative-'+v];a,b,p,loop=c['items']
        rows.append([v,fmt(a['measurement']['duration']),fmt(b['measurement']['duration']),fmt(p['measurement']['duration']),fmt(loop['measurement']['duration'])])
    r.table('Изолированные и внутрислоговые фрикативные',['Звук','Отдельно, с','Слог, с','Начало, с','Цикл, с'],rows)
    c=CASES['5-04-fricative-с']['items']
    r.fig(waves('lab5_fricative_s',[(i['role'],i['id']) for i in [c[0],c[1],c[-1]]]),'Изолированный [с], слог «са» и искусственный цикл')
    r.para('Для каждого фрикативного согласного повторён участок 10 мс. Созданный сигнал имеет искусственный период '
           '100 Гц независимо от того, имел ли исходный шумовой участок устойчивый период. Поэтому наличие периодичности '
           'у результата цикла не является признаком периодичности исходного согласного.')
    r.heading('1.4.3. Взрывные, носовые и коартикуляция')
    r.para('Записи [б], [д], [м], [н] сопоставлены со слогами «ба», «да», «ма», «на» и их начальными участками. '
           'Для остальных согласных выполнены аналогичные опыты с коротким циклом. В записи твёрдых слогов последние два '
           'произнесения имели порядок «ща», «ча»; разметка соответствует этому фактическому порядку.')
    rows=[]
    for consonant in ['б','д','м','н','п','т','к','г','в','ф','з','с','х','л','р']:
        c=CASES['5-06-pair-'+consonant]['items'];h,s=c[0],c[3]
        rows.append([h['role'].replace('Слог ',''),fmt(h['measurement']['duration']),fmt(h['measurement']['rms'],4),
                     s['role'].replace('Слог ',''),fmt(s['measurement']['duration']),fmt(s['measurement']['rms'],4)])
    r.table('Твёрдые и мягкие согласные в слогах',['Слог','T, с','RMS','Слог','T, с','RMS'],rows)
    b=CASES['5-05-coart-б']['items'];m=CASES['5-05-coart-м']['items']
    r.fig(waves('lab5_coarticulation',[('Слог «ба»',b[1]['id']),('Начало «ба»',b[2]['id']),('Слог «ма»',m[1]['id']),('Начало «ма»',m[2]['id'])],2),
          'Целые слоги и приближённо выделенные согласные участки')
    r.para('Разделение слога не создаёт независимые артикуляции: на границе присутствуют переходные процессы. '
           'Для носовых и других звонких согласных также возможна квазипериодичность, поэтому отсутствие устойчивого звучания '
           'короткого вырезанного участка нельзя трактовать как полное отсутствие периодичности у всех согласных. '
           'Сопоставление «ба» и «би» изменяет одновременно мягкость согласного и гласный контекст.')
    r.heading('1.5. Сравнение дикторов')
    rows=[]
    for v in 'аоуэыи':
        a,b=CASES['5-07-speaker-'+v]['items'];m,n=a['measurement'],b['measurement']
        rows.append([v,fmt(m['median_f0'],2),fmt(n['median_f0'],2),fmt(m['rms'],4),fmt(n['rms'],4)])
    r.table('Показатели гласных двух дикторов',['Гласная','F₀ диктора 1','F₀ диктора 2','RMS 1','RMS 2'],rows)
    r.end(['Наибольшее изменение формата связано с частотой дискретизации и разрядностью; повышение частоты '
           'после понижения не восстанавливает удалённые составляющие спектра.',
           'Период гласного, повторённый многократно, образует устойчивый периодический сигнал. Повтор '
           'произвольного шумового участка также создаёт периодичность, но искусственно.',
           'Различия F₀ двух дикторов зависят от конкретной гласной. Относительный уровень PCM отражает также '
           'расстояние до микрофона и условия записи; RMS не является калиброванным уровнем звукового давления.'],
          'Уточнение границ по спектрограммам и ручной разметке, выравнивание условий записи дикторов, '
          'оценка шума и анализ формант. Для отдельного аппаратного эксперимента необходимы независимые записи с заданными параметрами АЦП.',
          'Исследованы параметры PCM и фонетические характеристики речевого сигнала. Для гласных подтверждено соответствие '
          'между оценкой F₀ и длительностью выделенного периода. Показано различие исходной и искусственно созданной периодичности. '
          'Сохранены согласные, слоги и переходные участки; коартикуляция ограничивает точность разделения слога на независимые фонемы.')
    r.save()


def report6():
    r=Report(6)
    r.common('Исследовать ударение, акцентные группы, интонацию и влияние мелодических, энергетических и ритмических преобразований на речевой сигнал.',
             'Сформировать шесть перестановок отдельных слов, сопоставить их с перестановкой слов цельных фраз; '
             'исследовать четыре интонации и эмоциональную окраску; обработать тон, усиление и длительность каждого слова нейтральной фразы.',
             ['Записи слов\nи фраз','Разметка\nслов','Перестановка /\nконтур F₀','Усиление /\nдлительность','Сравнение\nконтуров'])
    r.para('Изменение тона и длительности разделено на два режима. Pitch Bend применяет переменную скорость воспроизведения. '
           'Для контура Pitch Shift после изменения тона длина слова восстанавливается фазовым вокодером STFT: окно 1024 отсчёта, шаг 256. '
           'Отдельно применяются контур усиления 0 → +6 → 0 дБ и множитель длительности 1,35.')
    r.heading('Результаты экспериментов:')
    r.heading('2.2.1. Отдельные слова и фразовое ударение')
    perms=CASES['6-01-permutations']
    r.table('Шесть перестановок отдельных слов',['Последовательность','T, с','F₀, Гц','RMS'],
            [[i['role'],fmt(i['measurement']['duration']),fmt(i['measurement']['median_f0'],2),fmt(i['measurement']['rms'],4)] for i in perms['items']],
            [7.1,2.9,2.9,2.9])
    r.para('Во всех шести сборках использован один и тот же набор слов и две паузы по 90 мс. Длительность '
           'составляет 2,005 с, RMS практически одинаков. Небольшие различия медианы F₀ связаны с расположением '
           'кадров анализа относительно границ и пауз; они не означают изменения исходной мелодики каждого слова. '
           'Для раздельного произнесения рассматривается структура трёх акцентных групп (+) (+) (+).')
    stress=CASES['6-02-stress']
    r.table('Перестановка ударного компонента цельной фразы',['Вариант','T, с','F₀, Гц','RMS'],
            [[i['role'],fmt(i['measurement']['duration']),fmt(i['measurement']['median_f0'],2),fmt(i['measurement']['rms'],4)] for i in stress['items']],
            [7.1,2.9,2.9,2.9])
    r.para('Для исходных фраз заданы акцентные схемы (+ − −), (− + −), (− − +). В первом случае выделенное «Саша» '
           'перенесено в конец: «кушал кашу Саша»; во втором «кушал» — в конец: «Саша кашу кушал»; '
           'в третьем «кашу» — в начало: «кашу Саша кушал». Длина каждой цельной фразы после перестановки сохраняется. '
           'Реальная выразительность не определяется одной медианой F₀: существенна форма контура относительно ударного слога.')
    r.fig(contours('lab6_stress_contours',[(i['role'],i['id']) for i in stress['items'][:2]]),
          'Исходная фраза с ударением на «Саша» и перестановка ударного слова')
    r.heading('2.2.2. Интонационные и эмоциональные варианты')
    natural=CASES['6-03-intonation']
    r.table('Четыре естественные интонации',['Интонация','T, с','F₀, Гц','RMS'],
            [[i['role'],fmt(i['measurement']['duration']),fmt(i['measurement']['median_f0'],2),fmt(i['measurement']['rms'],4)] for i in natural['items']],
            [7.1,2.9,2.9,2.9])
    r.fig(contours('lab6_intonations',[(i['role'],i['id']) for i in natural['items']],2),
          'Контуры F₀ и RMS четырёх интонационных вариантов')
    r.para('Незавершённая фраза содержит продолжение «сегодня на обед», поэтому её длительность нельзя прямо '
           'сравнивать с длиной коротких вариантов. У вопросительной записи медиана F₀ выше, чем у завершённой; '
           'у восклицания выше RMS. Эти наблюдения относятся к данным записям, а не к универсальному правилу классификации интонации.')
    emotions=CASES['6-04-emotions']
    r.table('Эмоциональная окраска фразы',['Вариант','T файла, с','F₀, Гц','RMS'],
            [[i['role'],fmt(i['measurement']['duration']),fmt(i['measurement']['median_f0'],2),fmt(i['measurement']['rms'],4)] for i in emotions['items']],
            [7.1,2.9,2.9,2.9])
    r.para('Эмоциональные установки заданы при произнесении. Длительность этих файлов включает краевые паузы. '
           'У монотонного варианта медиана F₀ оказалась выше остальных; следовательно, одна эта величина не определяет '
           'эмоцию и не доказывает монотонность. Для анализа необходимы динамика F₀, энергетика, ритмика и слуховая оценка.')
    r.heading('2.3. Управление просодией')
    r.para('Исходная фраза «Студент писал реферат» после выделения речевого участка имеет длительность 1,920 с. '
           'Интервалы слов в исходной записи: «Студент» — 0,300–1,040 с; «писал» — 1,040–1,540 с; '
           '«реферат» — 1,540–2,220 с. После обрезки начало координат сдвинуто на 0,300 с.')
    r.table('Параметры преобразований',['Параметр','Утверждение','Вопрос'],[
        ['Тон: начало / середина / конец','0 / +4 / −3 полутона','0 / +4 / +4 полутона'],
        ['Усиление: начало / середина / конец','0 / +6 / 0 дБ','0 / +6 / 0 дБ'],
        ['Растяжение ударного участка','× 1,35','× 1,35'],
        ['Паузы и остальные слова','Сохраняются','Сохраняются']],[6.2,4.8,4.8])
    rows=[]
    for word in range(3):
        case=CASES[f'6-05-word-{word}']
        for item in case['items'][1:]:
            m=item['measurement'];rows.append([['Студент','писал','реферат'][word],item['role'],fmt(m['duration']),fmt(m['median_f0'],2),fmt(m['rms'],4)])
    r.table('Конечные варианты после тона, усиления и растяжения',['Ударное слово','Режим','T, с','F₀, Гц','RMS'],rows,[2.9,5.2,2.5,2.7,2.5])
    final=CASES['6-05-word-2']['items'][-1]['id'];chain=parameter_chain(final)
    stages=['Исходник','Контур Pitch Shift','Дополнительно усиление','Дополнительно растяжение']
    rows=[]
    for name,n in zip(stages,chain):
        m=measured(n);rows.append([name,fmt(m['duration'],4),fmt(m['median_f0'],2),fmt(m['rms'],4)])
    r.table('Промежуточные этапы: вопрос, ударение на «реферат»',['Этап','T, с','F₀, Гц','RMS'],rows,[7.1,2.9,2.9,2.9])
    r.fig(contours('lab6_processing_stages',list(zip(stages,chain)),2),'Изменение контуров на последовательных этапах обработки')
    r.para('Равенство длительностей исходника и этапа Pitch Shift проверено для всех трёх слов и двух целевых интонаций. '
           'Увеличение длины в итоговых вариантах Pitch Shift связано с последующим растяжением × 1,35, а не со сдвигом тона. '
           'Для Pitch Bend длина меняется уже на этапе изменения частоты. Дополнительный материал с другими текстами '
           'включает естественные эталонные фразы лабораторной 7.')
    r.end(['Перестановки сохраняют отсчёты отдельных фрагментов и меняют их положение относительно фразы; '
           'поэтому распределение общей энергии меняется мало, а временное положение акцента — существенно.',
           'В естественных записях различаются и F₀, и RMS, и длительности. Медиана по целой фразе не заменяет '
           'анализ предъядра, ударного ядра и заядра акцентной группы.',
           'Преобразования задают целевые интонационные варианты. Численные результаты подтверждают действие '
           'алгоритмов на параметры сигнала, но не являются самостоятельным доказательством убедительности вопроса или эмоции.'],
          'Уточнение границ слов и ударных гласных, построение контуров на уровне предъядра, ядра и заядра, '
          'более качественное изменение высоты тона с сохранением формант и независимая слуховая оценка.',
          'Исследованы словесное и фразовое ударение, интонация и эмоциональная окраска. Получены обязательные шесть '
          'перестановок и характерные перестановки цельных фраз. На нейтральной фразе раздельно изменены тон, громкость '
          'и длительность; различие Pitch Bend и Pitch Shift подтверждено сохранением или изменением длины на соответствующем этапе.')
    r.save()


def report7():
    r=Report(7)
    r.common('Исследовать компиляционный синтез речи из записанных фонем и слогов и влияние обработки стыков и просодии на естественность звучания.',
             'Подготовить пять эталонных фраз, их фонемные и слоговые представления; выполнить компиляцию из фонем, '
             'обработать стыки, повторить синтез из независимых слогов и сопоставить результаты с эталонами. '
             'В дополнительном опыте изменить мелодику, энергетику и длительности.',
             ['Текст и\nударения','Фонемная /\nслоговая запись','Выбор единиц\nиз базы','Склейка и\nпросодия','Сопоставление\nс эталоном'])
    r.para('Компиляционный метод использует фрагменты естественной речи и не моделирует физику речеобразования. '
           'В данной реализации орфографический текст преобразован в учебную транскрипцию вручную; '
           'автоматического определения ударений и неограниченного словаря нет. Единицы базы приведены к моно 32 кГц. '
           'Эталоны не использованы как источник слогов: слоговая база записана отдельно.')
    r.heading('Результаты экспериментов:')
    r.heading('3.2. Эталоны и рабочие материалы')
    r.table('Пять эталонных фраз',['№','Текст','Структура и интонация'],[
        [1,SESSION['phrases'][0]['text'],'Одна синтагма; утверждение'],
        [2,SESSION['phrases'][1]['text'],'Вопрос'],
        [3,SESSION['phrases'][2]['text'],'Восклицание'],
        [4,SESSION['phrases'][3]['text'],'Две синтагмы; сложная фраза'],
        [5,SESSION['phrases'][4]['text'],'Перечисление']],[.8,9.0,6.0])
    r.para('В учебных фонемных текстах использована шестигласная система методички. Безударные «о» и «е» '
           'переданы как [а] и [и]; мягкость обозначена апострофом, словесные ударения — знаком акцента. '
           'Знак / разделяет слова или группы слогов, // — синтагматическую паузу. Точная степень редукции '
           'и контекстные аллофоны в этой упрощённой записи не моделируются.')
    for i,phrase in enumerate(SESSION['phrases'],1):
        r.para(f'{i}. {phrase["text"]} Фонемный текст: {accented(phrase)}. Слоговые единицы: {phrase["syllables"]}.')
    r.heading('3.3.1–3.3.3. Фонетическая база и фонемная компиляция')
    r.para('Гласные извлечены из протяжных произнесений лабораторной 5. Фрикативные согласные взяты из изолированных записей; '
           'другие согласные — из начальных участков твёрдых и мягких слогов. Эти границы приближённые и сохраняют '
           'коартикуляционный контекст. Для сборки использованы гласные до 170 мс, согласные до 85 мс; '
           'межсловные и синтагматические паузы заданы как 70 и 220 мс.')
    r.heading('3.3.4. Обработка стыков')
    r.para('Для дополнительной обработки амплитуды единиц нормированы с ограничением пика 0,5. '
           'На краях применены линейные огибающие по 3 мс; соседние фонемные единицы склеены с перекрытием до 3 мс. '
           'Исходная фонемная сборка сохранена отдельно. Перекрытие немного уменьшает её суммарную длительность.')
    r.heading('3.3.5. Слоговая компиляция')
    r.para('Использованы независимо записанные слоги «ма», «ла», «ра», «са», «ша», «ка», «на», «ли», «пи», «ри», «фи», «ти», «га» '
           'и дополнительная запись «мы, му, ку, шал, шу, сту, дент, сал, рат, ста, ле, жат, кни, руч, традь». '
           'Для гласных слов «а» и «и» использованы соответствующие изолированные записи. '
           'Слоговые фрагменты собраны с перекрытием до 5 мс и с теми же межсловными и синтагматическими паузами.')
    r.heading('3.3.6*. Просодическая обработка')
    r.para('Длительности слогов ориентированы на активные участки эталона. Ударным единицам назначен '
           'множитель длительности 1,20, безударным — 0,85 относительно базового целевого значения. '
           'Амплитуды нормированы до пиков 0,55 и 0,38 соответственно. Применены упрощённые контуры Pitch Bend '
           'с подъёмом до +3 полутонов на ударных единицах и изменением окончания; после этого выполнена склейка до 5 мс.')
    rows=[]
    for i in range(1,6):
        c=CASES[f'7-0{i}-phrase']
        for item in c['items']:
            m=item['measurement'];rows.append([i,item['role'],fmt(m['duration']),fmt(m['median_f0'],2),fmt(m['rms'],4)])
    r.table('Измерения эталонов и четырёх методов компиляции',['Фраза','Вариант','T, с','F₀, Гц','RMS'],rows,[1.2,6.3,2.7,2.8,2.8])
    first=CASES['7-01-phrase']['items']
    r.fig(waves('lab7_phrase1_wave',[(i['role'],i['id']) for i in first]),'Осциллограммы пяти вариантов фразы «Мама мыла раму»')
    r.fig(contours('lab7_phrase1_prosody',[(i['role'],i['id']) for i in [first[0],first[3],first[4]]]),
          'Эталон, слоговая компиляция и результат просодической обработки первой фразы')
    r.table('Слуховое сравнение методов',['Метод','Наблюдаемое звучание'],[
        ['Фонемная компиляция','Прерывистое, роботизированное звучание'],
        ['Обработка фонемных стыков','Разрывы уменьшаются, роботизированность сохраняется'],
        ['Слоговая компиляция','Значительно естественнее; наиболее близка к эталону'],
        ['Слоги с обработкой просодии','Улучшения нет; по оценке звучания не лучше фонемной сборки']],[5.3,10.5])
    r.para(SYNTHESIS_CONCLUSION)
    r.para('Оценка качественная, без введения не измеренной балльной шкалы. Полные эталоны сохранены с краевыми '
           'паузами, тогда как длительности сборок определяются количеством и длинами единиц базы. '
           'Поэтому разность длительностей файлов не равна ошибке темпа и сама по себе не измеряет естественность.')
    r.end(['Слоговая база сохраняет внутрислоговые артикуляционные переходы, поэтому уменьшает число резких межфонемных стыков. '
           'Сглаживание фонемных границ не восстанавливает отсутствующий контекст и не устраняет роботизированность.',
           'После нормировки RMS обработанных сборок заметно выше исходных. Громкость и сходство медианы F₀ '
           'не являются показателями естественности. Для слухового сопоставления существенна согласованность уровня воспроизведения.',
           'Упрощённая просодическая обработка дала отрицательный результат по качественной оценке: '
           'изменённые длительности и частоты не приблизили звучание к эталону. Возможные причины — '
           'артефакты фазового вокодера, несогласованные контуры и разрывы контекста; данный опыт не выделяет вклад каждой причины отдельно.'],
          'Расширение базы аллофонами и дифонами, контекстный выбор единиц, ручная проверка границ, '
          'сохранение формант при изменении тона, моделирование просодии на уровне целой синтагмы и слуховая оценка при выровненной громкости.',
          'Реализован компиляционный синтез пяти фраз из фонем и независимо записанных слогов. '
          'Слоговая компиляция оказалась наиболее близкой к естественному эталону. Обработка стыков частично улучшила '
          'фонемную сборку, но её роботизированность сохранилась; выбранная обработка просодии улучшения не дала. '
          'Для полноценного синтезатора с неограниченным словарём необходимы нормализация текста, автоматические ударения и '
          'транскрипция, контекстный выбор единиц, полная фонетическая база и согласованная модель просодии.')
    r.save()


def main():
    ASSETS.mkdir(exist_ok=True)
    report5();report6();report7()


if __name__=='__main__':main()
