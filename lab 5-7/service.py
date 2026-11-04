"""Operations exposed by the speech API; every edit produces a new clip."""
import itertools
import numpy as np

from . import audio, storage


def public(row):
    return {k: v for k, v in row.items() if k != "wav"}


def upload(data, payload):
    return {"id": storage.save(data, payload, {"operation": "microphone" if payload.get("source") == "microphone"
                                             else "import", "original_filename": str(payload.get("filename", ""))[:180]})}


def edit(payload):
    row = storage.get(int(payload["id"]))
    x, rate, _ = audio.decode(row["wav"])
    operation = str(payload.get("operation", ""))
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("Неверные параметры обработки")
    y, new_rate = audio.process(x, rate, operation, params)
    bits = int(audio.finite(params.get("bits", 16), 8, 16, "Разрядность"))
    wav = audio.encode(y, new_rate, bits)
    return {"id": storage.save(wav, {**row, **payload.get("metadata", {}), "notes": ""},
                               {"operation": operation, "source_id": row["id"], "params": params,
                                "peak_before_clipping": float(np.max(abs(y))),
                                "clipped_samples": int(np.sum(abs(y) > 1))})}


def quality(payload):
    row = storage.get(int(payload["id"]))
    x, rate, _ = audio.decode(row["wav"])
    ids = []
    for target_rate in (4000, 8000, 16000, 32000):
        y = audio.resample(x, round(len(x) * target_rate / rate))
        for bits in (8, 16):
            ids.append(storage.save(audio.encode(y, target_rate, bits),
                                    {**row, "lab": 5, "task": "5-quality", "kind": "quality", "notes": "",
                                     "title": f'{row["title"]} · {target_rate} Гц / {bits} бит'},
                                    {"operation": "quality_conversion", "source_id": row["id"],
                                     "rate": target_rate, "bits": bits}))
    return {"ids": ids}


def assemble(payload):
    pieces = payload.get("pieces", [])
    if not isinstance(pieces, list) or not 1 <= len(pieces) <= 150:
        raise ValueError("Добавьте от 1 до 150 фрагментов")
    rate = 32000
    parts, recipe = [], []
    duration = 0
    for piece in pieces:
        if "silence_ms" in piece:
            seconds = audio.finite(piece["silence_ms"], 1, 2000, "Пауза, мс") / 1000
            duration += seconds
            if duration > audio.MAX_SECONDS:
                raise ValueError("Суммарная длительность фрагментов больше 120 с")
            parts.append(np.zeros(round(seconds * rate)))
            recipe.append({"silence_ms": seconds * 1000, "label": "Пауза"})
            continue
        row = storage.get(int(piece["id"]))
        x, source_rate, _ = audio.decode(row["wav"])
        a, b = audio.bounds(x, source_rate, piece.get("start", 0), piece.get("end"))
        duration += (b - a) / source_rate
        if duration > audio.MAX_SECONDS:
            raise ValueError("Суммарная длительность фрагментов больше 120 с")
        parts.append(audio.resample(x[a:b], round((b - a) * rate / source_rate)))
        recipe.append({"id": row["id"], "title": row["title"], "start": a / source_rate,
                       "end": b / source_rate, "label": str(piece.get("label", row["title"]))[:180]})
    y = audio.join(parts, rate, payload.get("gap_ms", 0), payload.get("fade_ms", 0))
    info = {"lab": payload.get("lab", 7), "kind": "synthesis", "title": "Собранная фраза",
            **payload.get("metadata", {})}
    clip_id = storage.save(audio.encode(y, rate), info,
                           {"operation": "assemble", "pieces": recipe,
                            "gap_ms": payload.get("gap_ms", 0), "fade_ms": payload.get("fade_ms", 0)})
    return {"id": clip_id}


def permutations(payload):
    pieces = payload.get("pieces", [])
    if len(pieces) != 3:
        raise ValueError("Для шести перестановок добавьте ровно три слова в монтаж")
    ids = []
    for index, order in enumerate(itertools.permutations(pieces), 1):
        info = {**payload.get("metadata", {}), "lab": 6, "task": "6-words",
                "title": f'Перестановка {index}: ' + " · ".join(str(p.get("label", p["id"])) for p in order)}
        ids.append(assemble({**payload, "pieces": list(order), "metadata": info})["id"])
    return {"ids": ids}
