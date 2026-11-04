"""Store WAVs, provenance, manual segmentation and observations in SQLite."""
from contextlib import closing
import json

from db import connect


def initialize():
    with closing(connect()) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS speech_clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT, lab INTEGER NOT NULL,
            title TEXT NOT NULL, kind TEXT NOT NULL, speaker TEXT NOT NULL,
            task TEXT NOT NULL, text TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            regions TEXT NOT NULL DEFAULT '[]', provenance TEXT NOT NULL,
            sample_rate INTEGER NOT NULL, bits INTEGER NOT NULL,
            duration REAL NOT NULL, wav BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS speech_notes (
            lab INTEGER PRIMARY KEY, notes TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS speech_experiments (
            key TEXT PRIMARY KEY, lab INTEGER NOT NULL,
            data TEXT NOT NULL, observations TEXT NOT NULL DEFAULT ''
        );
        """)


def metadata(payload):
    from . import audio
    lab = int(audio.finite(payload.get("lab", 5), 5, 7, "Лабораторная"))
    result = {"lab": lab}
    for key, default, limit in (("title", "Запись", 180), ("kind", "recording", 40),
                                ("speaker", "Диктор 1", 100), ("task", "", 80),
                                ("text", "", 3000), ("notes", "", 10000)):
        result[key] = str(payload.get(key, default)).strip()[:limit]
    result["title"] = result["title"] or "Запись"
    return result


def save(wav, payload, provenance=None):
    from . import audio
    x, rate, bits = audio.decode(wav)
    info = metadata(payload)
    with closing(connect()) as db, db:
        cursor = db.execute("""INSERT INTO speech_clips
            (lab,title,kind,speaker,task,text,notes,provenance,sample_rate,bits,duration,wav)
            VALUES (:lab,:title,:kind,:speaker,:task,:text,:notes,:provenance,:rate,:bits,:duration,:wav)""",
            {**info, "provenance": json.dumps(provenance or {"operation": "import"}, ensure_ascii=False),
             "rate": rate, "bits": bits, "duration": len(x) / rate, "wav": wav})
        return cursor.lastrowid


def unpack(row):
    result = dict(row)
    for key in ("regions", "provenance"):
        result[key] = json.loads(result[key])
    return result


def get(clip_id):
    with closing(connect()) as db:
        row = db.execute("SELECT * FROM speech_clips WHERE id=?", (clip_id,)).fetchone()
    if row is None:
        raise ValueError("Аудиозапись не найдена")
    return unpack(row)


def list_clips(lab=None):
    with closing(connect()) as db:
        rows = db.execute("""SELECT id,lab,title,kind,speaker,task,text,notes,regions,provenance,
                          sample_rate,bits,duration,created_at,length(wav) AS size_bytes FROM speech_clips
                          WHERE (? IS NULL OR lab=?) ORDER BY id DESC""", (lab, lab)).fetchall()
    return [unpack(row) for row in rows]


def update(clip_id, payload):
    from . import audio
    old = get(clip_id)
    info = metadata({**old, **payload})
    regions = payload.get("regions", old["regions"])
    if not isinstance(regions, list) or len(regions) > 150:
        raise ValueError("Допустимо до 150 размеченных фрагментов")
    cleaned = []
    for region in regions:
        if not isinstance(region, dict):
            raise ValueError("Неверный формат разметки")
        start = audio.finite(region.get("start"), 0, old["duration"], "Начало фрагмента")
        end = audio.finite(region.get("end"), 0, old["duration"], "Конец фрагмента")
        if end <= start:
            raise ValueError("Конец фрагмента должен быть позже начала")
        cleaned.append({"start": start, "end": end, "label": str(region.get("label", ""))[:100]})
    with closing(connect()) as db, db:
        db.execute("""UPDATE speech_clips SET lab=:lab,title=:title,kind=:kind,speaker=:speaker,
            task=:task,text=:text,notes=:notes,regions=:regions WHERE id=:id""",
            {**info, "regions": json.dumps(cleaned, ensure_ascii=False), "id": clip_id})


def delete(clip_id):
    with closing(connect()) as db, db:
        db.execute("DELETE FROM speech_clips WHERE id=?", (clip_id,))


def notes(lab, value=None):
    with closing(connect()) as db, db:
        if value is not None:
            db.execute("INSERT INTO speech_notes VALUES (?,?) ON CONFLICT(lab) DO UPDATE SET notes=excluded.notes",
                       (lab, str(value)[:30000]))
        row = db.execute("SELECT notes FROM speech_notes WHERE lab=?", (lab,)).fetchone()
    return row[0] if row else ""


def save_experiment(key, lab, data):
    """Replace measured results while retaining the user's listening observations."""
    with closing(connect()) as db, db:
        db.execute("""INSERT INTO speech_experiments(key,lab,data) VALUES (?,?,?)
            ON CONFLICT(key) DO UPDATE SET lab=excluded.lab,data=excluded.data""",
            (key, lab, json.dumps(data, ensure_ascii=False)))


def experiments(lab=None):
    with closing(connect()) as db:
        rows = db.execute("SELECT * FROM speech_experiments WHERE (? IS NULL OR lab=?) ORDER BY key",
                          (lab, lab)).fetchall()
    return [{**json.loads(r['data']), 'key': r['key'], 'lab': r['lab'],
             'observations': r['observations']} for r in rows]


def observe_experiment(key, observations):
    with closing(connect()) as db, db:
        result = db.execute("UPDATE speech_experiments SET observations=? WHERE key=?",
                            (str(observations)[:10000], str(key)))
        if not result.rowcount:
            raise ValueError("Опыт не найден")
