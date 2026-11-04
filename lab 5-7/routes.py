"""Speech routes, kept separate from the previous laboratory handlers."""
import base64
import json

from .tasks import NAMES


def binary(handler, data, content_type, filename=None):
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(data)


def get(handler, route, params, page):
    if not route.path.startswith(("/speech/", "/api/speech/")):
        return False
    from . import audio, report, service, storage, web
    try:
        parts = route.path.strip('/').split('/')
        if parts[0] == "speech" and len(parts) == 2:
            lab = int(parts[1])
            handler.send_html(page(NAMES[lab], web.content(lab), f"speech{lab}"))
        elif parts[:2] == ["speech", "report"] and len(parts) == 3:
            lab = int(parts[2])
            if lab not in NAMES:
                raise ValueError("Неверная лабораторная")
            binary(handler, report.build(lab), "application/zip", f"lab{lab}_speech.zip")
        elif parts[2:] == ["clips"]:
            lab = params.get("lab", [""])[0]
            handler.send_json({"clips": storage.list_clips(int(lab) if lab else None)})
        elif parts[2:] == ["notes"]:
            lab = int(params.get("lab", ["5"])[0])
            handler.send_json({"notes": storage.notes(lab)})
        elif parts[2:] == ["experiments"]:
            lab = int(params.get("lab", ["5"])[0])
            handler.send_json({"experiments": storage.experiments(lab)})
        elif len(parts) == 4:
            name, clip_id = parts[2], int(parts[3])
            row = storage.get(clip_id)
            if name == "clip":
                handler.send_json(service.public(row))
            elif name == "wav":
                binary(handler, row["wav"], "audio/wav", f"clip_{clip_id}.wav")
            elif name in ("analysis", "plot", "measurements"):
                x, rate, _ = audio.decode(row["wav"])
                data = audio.analyze(x, rate, params.get("start", [0])[0], params.get("end", [None])[0])
                if name == "analysis":
                    handler.send_json(data)
                elif name == "plot":
                    kind = params.get("kind", ["wave"])[0]
                    binary(handler, report.plot(data, kind, row["title"]).encode("utf-8"), "image/svg+xml", f"clip_{clip_id}_{kind}.svg")
                else:
                    binary(handler, report.measurements(data), "text/csv; charset=utf-8", f"clip_{clip_id}_measurements.csv")
            else:
                raise ValueError("Неизвестный адрес")
        else:
            raise ValueError("Неизвестный адрес")
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        handler.send_json({"error": str(exc)}, 400)
    return True


def post(handler):
    """Read this body here so the old 2 MB text upload limit stays unchanged."""
    from . import audio, service, storage
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        if not 0 < length <= 44_000_000:
            handler.send_json({"error": "Пустой запрос или данные больше 44 МБ"}, 413)
            return
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("Нужен JSON-объект")
        action = handler.path.removeprefix("/api/speech/")
        if action == "upload":
            data = base64.b64decode(payload.get("wav", ""), validate=True)
            result = service.upload(data, payload)
        elif action == "edit":
            result = service.edit(payload)
        elif action == "quality":
            result = service.quality(payload)
        elif action == "assemble":
            result = service.assemble(payload)
        elif action == "permutations":
            result = service.permutations(payload)
        elif action == "update":
            storage.update(int(payload["id"]), payload)
            result = {"ok": True}
        elif action == "delete":
            storage.delete(int(payload["id"]))
            result = {"ok": True}
        elif action == "notes":
            lab = int(audio.finite(payload.get("lab"), 5, 7, "Лабораторная"))
            storage.notes(lab, payload.get("notes", ""))
            result = {"ok": True}
        elif action == "observe":
            storage.observe_experiment(payload["key"], payload.get("observations", ""))
            result = {"ok": True}
        else:
            raise ValueError("Неизвестное действие")
        handler.send_json(result)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        handler.send_json({"error": str(exc)}, 400)
