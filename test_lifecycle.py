"""Exercise real port and child-process cleanup without loading a model."""
from contextlib import contextmanager, nullcontext
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import app


WORKER = r'''
import _thread, subprocess, sys, threading
import app
from lab4 import server
from lifecycle import ChildProcessJob
app.initialize = lambda: None
app.lab2.initialize = lambda: None
app.lab3_store.initialize = lambda: None
app.lab4.initialize = lambda: None
app.speech_storage.initialize = lambda: None
def model():
    server._job = ChildProcessJob()
    server._process = subprocess.Popen([sys._base_executable, '-B', '-c', 'import time; time.sleep(120)'])
    server._job.add(server._process)
    print('MODEL:' + str(server._process.pid), flush=True)
app.lab4_server.start = model
def stop_on_input():
    if sys.stdin.readline().strip() == 'stop':
        _thread.interrupt_main()
threading.Thread(target=stop_on_input, daemon=True).start()
app.run(0)
'''


@contextmanager
def worker(*, launcher=False):
    code = WORKER
    if launcher:
        code = ("import subprocess,sys,time; "
                f"p=subprocess.Popen([sys._base_executable,'-B','-u','-c',{WORKER!r}],stdin=subprocess.PIPE); "
                "print('OWNER:'+str(p.pid),flush=True); time.sleep(120)")
    environment = dict(os.environ, PYTHONIOENCODING='utf-8')
    process = subprocess.Popen([sys._base_executable, '-B', '-u', '-c', code],
                               cwd=Path(__file__).parent, env=environment,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8')
    lines = queue.Queue()

    def read_output():
        for line in process.stdout:
            lines.put(line.strip())
        lines.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        details = {'owner': process.pid}
        while 'port' not in details:
            line = lines.get(timeout=10)
            if line is None:
                raise AssertionError('Worker failed: ' + process.stderr.read())
            if line.startswith('MODEL:'):
                details['model'] = int(line.split(':')[1])
            elif line.startswith('OWNER:'):
                details['owner'] = int(line.split(':')[1])
            elif 'http://127.0.0.1:' in line:
                details['port'] = int(line.rsplit(':', 1)[1])
        yield process, details
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


@contextmanager
def process_handle(pid):
    from lifecycle import _windows_api
    api = _windows_api()
    handle = api.OpenProcess(0x00100000, False, pid)
    if not handle:
        raise AssertionError(f'Cannot monitor process {pid}')
    try:
        yield lambda: api.WaitForSingleObject(handle, 5000) == 0
    finally:
        api.CloseHandle(handle)


class ApplicationLifecycle(unittest.TestCase):
    def assert_port_released(self, port):
        with app.ApplicationServer(('127.0.0.1', port), app.Handler):
            pass

    def test_startup_failure_releases_port_and_cleans_model(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with patch.object(app, 'watch_parent', nullcontext), \
             patch.object(app, 'initialize', side_effect=RuntimeError('startup failed')), \
             patch.object(app.lab4_server, 'stop') as stop:
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                app.run(port)
            stop.assert_called_once()
        self.assert_port_released(port)

    @unittest.skipUnless(os.name == 'nt', 'Windows process ownership')
    def test_normal_stop_releases_model_and_port(self):
        with worker() as (process, details), process_handle(details['model']) as model_exited:
            process.stdin.write('stop\n')
            process.stdin.flush()
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertTrue(model_exited(), 'Model survived normal application stop')
            self.assert_port_released(details['port'])

    @unittest.skipUnless(os.name == 'nt', 'Windows process ownership')
    def test_forced_stop_kills_model_and_releases_port(self):
        with worker() as (process, details), process_handle(details['model']) as model_exited:
            process.kill()
            process.wait(timeout=5)
            self.assertTrue(model_exited(), 'Model survived forced application stop')
            self.assert_port_released(details['port'])

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher monitoring')
    def test_stopping_launcher_also_stops_app_and_model(self):
        with worker(launcher=True) as (process, details), \
             process_handle(details['owner']) as owner_exited, \
             process_handle(details['model']) as model_exited:
            process.kill()
            process.wait(timeout=5)
            self.assertTrue(owner_exited(), 'Application survived its launcher')
            self.assertTrue(model_exited(), 'Model survived its launcher')
            self.assert_port_released(details['port'])


if __name__ == '__main__':
    unittest.main()
