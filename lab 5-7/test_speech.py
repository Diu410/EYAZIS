"""Numerical and HTTP regressions for the speech editor; no real microphone/DB."""
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave
import zipfile

import numpy as np

import app
import db
from . import audio, report, service, storage


def tone(hz=200, rate=16000, seconds=1):
    return .35 * np.sin(2 * np.pi * hz * np.arange(round(rate * seconds)) / rate)


def peak_frequency(x, rate):
    return np.fft.rfftfreq(len(x), 1 / rate)[np.argmax(abs(np.fft.rfft(x)))]


class SignalTests(unittest.TestCase):
    def test_pcm_8_and_16_round_trip(self):
        x = tone()
        for bits in (8, 16):
            y, rate, depth = audio.decode(audio.encode(x, 16000, bits))
            self.assertEqual((rate, depth, len(y)), (16000, bits, len(x)))
            self.assertLess(np.max(abs(y-x)), 1 / 2 ** (bits - 1))

    def test_stereo_24_bit_becomes_mono(self):
        values = np.array([0, 8388607, -8388608, 0], dtype=np.int32)
        raw = np.stack((values & 255, (values >> 8) & 255, (values >> 16) & 255), axis=1).astype(np.uint8).tobytes()
        out = io.BytesIO()
        with wave.open(out, 'wb') as w:
            w.setparams((2, 3, 16000, 0, 'NONE', 'not compressed'))
            w.writeframes(raw)
        y, rate, bits = audio.decode(out.getvalue())
        np.testing.assert_allclose(y, [.49999994, -.5], atol=1e-7)
        self.assertEqual(bits, 24)

    def test_resampling_removes_out_of_band_energy(self):
        x = tone(200) + tone(3500)
        y = audio.resample(x, 4000)
        self.assertAlmostEqual(peak_frequency(y, 4000), 200, delta=1)
        self.assertLess(np.max(abs(y-tone(200, 4000))), 1e-9)

    def test_pitch_and_duration_are_independent(self):
        x = tone()
        stretched, rate = audio.process(x, 16000, 'stretch', {'factor':1.5})
        shifted, _ = audio.process(x, 16000, 'pitch', {'semitones':12})
        bent, _ = audio.process(x, 16000, 'bend', {'pitch_start':12,'pitch_mid':12,'pitch_end':12})
        self.assertEqual(len(stretched), 24000)
        self.assertAlmostEqual(peak_frequency(stretched, rate), 200, delta=2)
        self.assertEqual(len(shifted), len(x))
        self.assertAlmostEqual(peak_frequency(shifted, rate), 400, delta=2)
        self.assertEqual(len(bent), 8000)
        self.assertAlmostEqual(peak_frequency(bent, rate), 400, delta=2)
        independent, _ = audio.process(x, 16000, 'pitch_contour',
                                      {'pitch_start':12,'pitch_mid':12,'pitch_end':12})
        self.assertEqual(len(independent), len(x))
        self.assertAlmostEqual(peak_frequency(independent,rate),400,delta=2)

    def test_processing_preserves_unselected_samples(self):
        x = tone()
        y, _ = audio.process(x, 16000, 'gain', {'start':.25,'end':.75,'gain_start':6,'gain_mid':6,'gain_end':6})
        np.testing.assert_array_equal(y[:4000], x[:4000])
        np.testing.assert_array_equal(y[12000:], x[12000:])
        np.testing.assert_allclose(y[4000:12000], x[4000:12000]*10**.3)

    def test_tone_f0_and_noise_rejection(self):
        for hz in (65, 80, 100, 200, 300, 450):
            self.assertAlmostEqual(audio.analyze(tone(hz), 16000)['median_f0'], hz, delta=3)
        noise = np.random.default_rng(71).normal(0, .2, 16000)
        self.assertIsNone(audio.analyze(noise, 16000)['median_f0'])
        self.assertIsNone(audio.analyze(np.zeros(16000), 16000)['median_f0'])

    def test_selection_limits_and_invalid_wavs(self):
        for start, end in [(1, .5), (-1, .5), (0, float('nan'))]:
            with self.assertRaises(ValueError):
                audio.bounds(tone(),16000,start,end)
        with self.assertRaises(ValueError):
            audio.decode(b'not a wave')
        with self.assertRaises(ValueError):
            audio.process(tone(),16000,'repeat',{'times':1000})
        with self.assertRaises(ValueError):
            audio.process(tone(),16000,'remove',{})

    def test_crossfade_and_gap_lengths(self):
        parts=[np.ones(1600),np.ones(1600)*.5]
        self.assertEqual(len(audio.join(parts,16000,100,0)),4800)
        self.assertEqual(len(audio.join(parts,16000,0,10)),3040)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.database=patch.object(db,'DB_PATH',Path(self.temp.name)/'speech.sqlite3')
        self.database.start();storage.initialize()
        self.first=storage.save(audio.encode(tone(),16000),{'lab':5,'title':'а','kind':'phoneme','task':'5-vowels'})

    def tearDown(self):
        self.database.stop();self.temp.cleanup()

    def test_quality_matrix_and_immutable_source(self):
        before=storage.get(self.first)['wav']
        ids=service.quality({'id':self.first})['ids']
        self.assertEqual(len(ids),8)
        for clip_id in ids:
            row=storage.get(clip_id)
            self.assertIn(row['sample_rate'],(4000,8000,16000,32000))
            self.assertIn(row['bits'],(8,16))
            self.assertAlmostEqual(row['duration'],1)
            self.assertEqual(row['provenance']['source_id'],self.first)
        self.assertEqual(storage.get(self.first)['wav'],before)

    def test_region_validation_and_persistence(self):
        storage.update(self.first,{'regions':[{'label':'а','start':.2,'end':.6}],'notes':'Периодичность видна.'})
        self.assertEqual(storage.get(self.first)['regions'][0]['label'],'а')
        self.assertEqual(storage.get(self.first)['notes'],'Периодичность видна.')
        with self.assertRaises(ValueError):
            storage.update(self.first,{'regions':[{'start':.6,'end':.2}]})
        self.assertEqual(len(storage.get(self.first)['regions']),1)

    def test_deleted_ids_are_not_reused_for_unrelated_audio(self):
        storage.delete(self.first)
        new_id=storage.save(audio.encode(tone(),16000),{'lab':5})
        self.assertGreater(new_id,self.first)

    def test_recipe_pause_and_report_include_cross_lab_sources(self):
        result=service.assemble({'lab':7,'pieces':[{'id':self.first,'start':.1,'end':.3},{'silence_ms':150},{'id':self.first,'start':.3,'end':.5}],
                                 'metadata':{'title':'Тестовая сборка','task':'7-phonemes'}})
        row=storage.get(result['id'])
        self.assertAlmostEqual(row['duration'],.55)
        storage.notes(7,'Наблюдение после опыта.')
        with zipfile.ZipFile(io.BytesIO(report.build(7))) as z:
            manifest=json.loads(z.read('manifest.json'))
            self.assertEqual({c['id'] for c in manifest['clips']},{self.first,result['id']})
            self.assertIn('Наблюдение после опыта.',z.read('report.html').decode())
            self.assertIn(f'clips/{self.first}.wav',z.namelist())
            self.assertIn('f0_hz',z.read(f'clips/{self.first}.csv').decode('utf-8-sig'))

    def test_six_permutations_are_distinct_recipes(self):
        pieces=[{'id':self.first,'start':i*.1,'end':(i+1)*.1,'label':str(i)} for i in range(3)]
        ids=service.permutations({'pieces':pieces})['ids']
        self.assertEqual(len(ids),6)
        recipes={tuple(p['label'] for p in storage.get(n)['provenance']['pieces']) for n in ids}
        self.assertEqual(len(recipes),6)

    def test_experiment_observations_survive_reprocessing_and_export(self):
        from .experiments import Runner
        runner=Runner({'recordings':{},'vowel_clips':{},'syllable_clips':{}})
        runner.case('5-example',5,'Контрольный опыт','Описание',[('Исходник',self.first)])
        storage.observe_experiment('5-example','Пользовательское наблюдение')
        runner.case('5-example',5,'Обновлённый опыт','Описание',[('Исходник',self.first)])
        self.assertEqual(storage.experiments(5)[0]['observations'],'Пользовательское наблюдение')
        with zipfile.ZipFile(io.BytesIO(report.build(5))) as z:
            self.assertIn('Пользовательское наблюдение',z.read('report.html').decode())
            self.assertEqual(len(json.loads(z.read('manifest.json'))['experiments']),1)

    def test_generated_clip_keys_are_idempotent(self):
        from .experiments import Runner
        runner=Runner({'recordings':{},'vowel_clips':{},'syllable_clips':{}})
        first=runner.save('control',tone(),16000,5,'5-vowels','Контроль',source=self.first)
        second=runner.save('control',tone(300),16000,5,'5-vowels','Контроль',source=self.first)
        self.assertEqual(first,second)
        self.assertEqual(len(storage.list_clips()),2)

    def test_segmentation_of_three_independent_utterances(self):
        from .experiments import detect_segments
        signal=np.concatenate([np.zeros(8000),tone(seconds=.3),np.zeros(16000),
                               tone(300,seconds=.4),np.zeros(16000),tone(400,seconds=.25),np.zeros(8000)])
        regions=detect_segments(signal,16000)
        self.assertEqual(len(regions),3)
        self.assertLess(regions[0][0],.51)
        self.assertGreater(regions[-1][1],3.44)

    def test_compact_prosody_keeps_required_comparisons_and_observations(self):
        from .presentation import compact_lab6
        item=lambda n:{'id':n,'role':str(n),'measurement':{}}
        cases=[{'key':'6-01-permutations','lab':6,'items':[item(n) for n in range(9)]}]
        for n in range(3):
            cases.append({'key':f'6-02-stress-{n}','lab':6,'title':str(n),
                          'items':[item(n*10+i) for i in range(7)],'observations':'оценка' if n==1 else ''})
        for key in ['6-03-intonation','6-04-emotions']:
            cases.append({'key':key,'lab':6,'items':[item(i) for i in range(4)]})
        for word in range(3):
            for kind in ['Утверждение','Вопрос']:
                for mode in ['bend','pitch']:
                    cases.append({'key':f'6-05-{kind}-{word}-{mode}','lab':6,'title':kind,
                                  'items':[item(i) for i in range(4)],'observations':''})
        result=compact_lab6(cases)
        self.assertEqual(len(result),7)
        self.assertEqual(len(result[0]['items']),6)
        self.assertEqual(len(result[1]['items']),6)
        self.assertIn('оценка',result[1]['observations'])
        self.assertEqual([len(c['items']) for c in result[-3:]],[5,5,5])

    def test_report_keeps_intermediate_processing_sources(self):
        from .experiments import Runner
        runner=Runner({'recordings':{},'vowel_clips':{},'syllable_clips':{}})
        middle=runner.save('middle',tone(),16000,6,'6-contours','Тон',source=self.first)
        final=runner.save('final',tone(),16000,6,'6-contours','Длительность',source=middle)
        runner.case('6-example',6,'Опыт','Описание',[('Результат',final)])
        with zipfile.ZipFile(io.BytesIO(report.build(6))) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual({c['id'] for c in manifest['clips']},{self.first,middle,final})

    def test_http_ui_upload_analysis_and_validation(self):
        with app.ApplicationServer(('127.0.0.1',0),app.Handler) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            origin=f'http://127.0.0.1:{server.server_port}'
            try:
                for lab in (5,6,7):
                    with urlopen(f'{origin}/speech/{lab}') as response:
                        html=response.read().decode()
                        self.assertIn('experiment-select',html)
                        self.assertNotIn('Запись с микрофона',html)
                        self.assertNotIn('advanced-tools',html)
                        self.assertNotIn('placeholder=',html)
                payload={'lab':6,'title':'Контрольный сигнал','wav':base64.b64encode(audio.encode(tone(),16000)).decode()}
                request=Request(origin+'/api/speech/upload',json.dumps(payload).encode(),{'Content-Type':'application/json'})
                with urlopen(request) as response:
                    clip_id=json.load(response)['id']
                with urlopen(f'{origin}/api/speech/analysis/{clip_id}?start=0.1&end=0.5') as response:
                    self.assertAlmostEqual(json.load(response)['median_f0'],200,delta=3)
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(origin+'/api/speech/edit',b'{"id":1,"operation":"invalid"}',{'Content-Type':'application/json'}))
                self.assertEqual(caught.exception.code,400)
                caught.exception.close()
            finally:
                server.shutdown();thread.join(timeout=3)


if __name__=='__main__':
    unittest.main()
