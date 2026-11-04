"""Optional lifecycle manager for the local llama.cpp server."""
import os
import shutil
import subprocess
import time
import threading
import json
from urllib.request import urlopen
from urllib.parse import urlsplit
from pathlib import Path
from lifecycle import ChildProcessJob

_process = None
_job = None
_lock = threading.RLock()
_stopping = threading.Event()


def ensure_ready(timeout=180):
    """Wait for the managed server before accepting translation requests."""
    with _lock:
        base = os.environ.get('LLAMA_CPP_BASE_URL', 'http://127.0.0.1:8080/v1/chat/completions')
        parsed = urlsplit(base)
        health = f'{parsed.scheme}://{parsed.netloc}/health'
        deadline = time.monotonic() + timeout
        started = False
        while time.monotonic() < deadline:
            if _stopping.is_set():
                raise ValueError('Приложение останавливается.')
            try:
                with urlopen(health, timeout=2) as response:
                    if json.load(response).get('status') == 'ok':
                        return
            except (OSError, ValueError):
                pass
            if _process is not None and _process.poll() is not None:
                raise ValueError('Сервер модели завершился. Подробности: lab4/llama-server.log')
            if _process is None and not started:
                if not start():
                    raise ValueError('Не удалось запустить сервер Gemma. Проверьте настройки модели.')
                started = True
            _stopping.wait(0.25)
        raise ValueError('Модель ещё не загрузилась. Подробности: lab4/llama-server.log')

def _find_model():
    bundled = Path.home() / 'Documents' / 'RAG_Google_Drive_multiagent' / 'api' / 'models' / 'gemma-4-E4B_q4_0-it.gguf'
    if bundled.is_file():
        return str(bundled)
    candidates = [Path.home() / 'Documents' / 'RAG_Google_Drive_multiagent' / 'api' / 'data' / 'models',
                 Path.home() / 'Documents' / 'RAG_Google_Drive_multiagent' / 'api' / 'models',
                 Path.home() / 'Documents']
    for root in candidates:
        if root.exists():
            for pattern in ('*gemma*4*.gguf', '*Gemma*4*.gguf'):
                matches = sorted(root.rglob(pattern))
                if matches:
                    return str(matches[0])
    return None


def start():
    """Start llama-server when executable and a GGUF model are configured."""
    global _process, _job
    _stopping.clear()
    if _process is not None and _process.poll() is None:
        return True
    endpoint = os.environ.get('LLAMA_CPP_BASE_URL', 'http://127.0.0.1:8080/v1/chat/completions')
    parsed_endpoint = urlsplit(endpoint)
    try:
        with urlopen(f'{parsed_endpoint.scheme}://{parsed_endpoint.netloc}/health', timeout=2) as response:
            if json.load(response).get('status') == 'ok':
                os.environ.setdefault('LLAMA_CPP_MODEL', 'gemma-lab4')
                return True
    except (OSError, ValueError):
        pass
    executable = os.environ.get('LLAMA_CPP_EXECUTABLE') or shutil.which('llama-server')
    if not executable:
        bundled = Path.home() / 'Documents' / 'RAG_Google_Drive_multiagent' / 'runtime' / 'llama' / 'llama-server.exe'
        if bundled.is_file():
            executable = str(bundled)
    model = os.environ.get('LLAMA_CPP_MODEL_PATH') or _find_model()
    if not executable:
        print('ЛР4: llama-server не найден. Установите llama.cpp или задайте LLAMA_CPP_EXECUTABLE.')
        return False
    if not model or not Path(model).is_file():
        print('ЛР4: GGUF-модель не задана/не найдена. Задайте LLAMA_CPP_MODEL_PATH.')
        return False
    host = os.environ.get('LLAMA_CPP_HOST', '127.0.0.1')
    port = os.environ.get('LLAMA_CPP_PORT', '8080')
    try:
        port_number = int(port)
        if not 1 <= port_number <= 65535:
            raise ValueError
    except ValueError:
        print('ЛР4: LLAMA_CPP_PORT должен быть портом 1–65535.')
        return False
    url = os.environ.get('LLAMA_CPP_BASE_URL', f'http://{host}:{port_number}/v1/chat/completions')
    os.environ.setdefault('LLAMA_CPP_BASE_URL', url)
    args = [str(executable), '-m', str(Path(model).resolve()), '--host', host,
            '--port', str(port_number), '-c', os.environ.get('LLAMA_CPP_CONTEXT', '8192'),
            '--jinja', '--alias', 'gemma-lab4', '--parallel', '1']
    os.environ.setdefault('LLAMA_CPP_MODEL', 'gemma-lab4')
    extra = os.environ.get('LLAMA_CPP_ARGS', '').strip()
    if extra:
        import shlex
        args.extend(shlex.split(extra, posix=os.name != 'nt'))
    log = Path(__file__).with_name('llama-server.log').open('ab')
    kwargs = {'stdin': subprocess.DEVNULL, 'stdout': log, 'stderr': log}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    try:
        _job = ChildProcessJob()
        _process = subprocess.Popen(args, **kwargs)
        _job.add(_process)
    except OSError as exc:
        stop()
        print(f'ЛР4: не удалось запустить llama-server: {exc}')
        return False
    finally:
        log.close()
    print(f'ЛР4: llama-server запускается на {host}:{port_number}; модель {Path(model).name}')
    return True


def stop():
    global _process, _job
    _stopping.set()
    try:
        if _process is not None:
            if _process.poll() is None:
                _process.terminate()
                try:
                    _process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    _process.kill()
                    _process.wait(timeout=3)
            else:
                _process.wait()
    finally:
        if _job is not None:
            _job.close()
        _process = None
        _job = None
