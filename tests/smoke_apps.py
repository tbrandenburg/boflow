"""Real application startup check, without installing OS services or touching user data."""
import importlib.util
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('boflow', ROOT / 'src/boflow.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

with tempfile.TemporaryDirectory() as temporary:
    app = b.App(Path(temporary) / 'state')
    sockets = []
    ports = {}
    for role in b.ROLES:
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        ports[role] = sock.getsockname()[1]
        sockets.append(sock)
    app.settings.update(ports=ports, node_path=str(Path(shutil.which('node')).resolve().parents[1]))
    app.save()
    runtime = ROOT / 'examples/household/node-red'
    for role in ('managed', 'personal'):
        user_dir = app.state / role
        user_dir.mkdir()
        (user_dir / 'flows.json').write_text('[]')
        (user_dir / 'credential-key').write_text(secrets.token_hex(32))
        (user_dir / 'node_modules').symlink_to(runtime / 'node_modules')
        (app.state / (role + '-runtime')).symlink_to(runtime)
    (app.state / 'jupyter-runtime').symlink_to(ROOT / 'examples/household/jupyter')
    (app.state / 'notebooks').mkdir()
    processes = []
    handles = []
    try:
        for sock in sockets:
            sock.close()
        for role in b.ROLES:
            with patch.object(b.os, 'execvpe') as execute:
                app.serve(role)
            exe, args, env = execute.call_args.args
            if role == 'jupyter' and os.getuid() == 0:
                args.append('--allow-root')  # container smoke test only, never product behavior
            log = (app.state / (role + '.log')).open('w')
            handles.append(log)
            processes.append(subprocess.Popen(args, env=env, stdout=log, stderr=log, start_new_session=True))
        for role, process in zip(b.ROLES, processes):
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f'{role} exited: ' + (app.state / (role + '.log')).read_text())
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{ports[role]}/', timeout=1) as response:
                        assert response.status == 200
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError(f'{role} failed to start')
            print(role + ': HTTP startup passed')
        for role in ('managed', 'personal'):
            with urllib.request.urlopen(f'http://127.0.0.1:{ports[role]}/nodes', timeout=5) as response:
                nodes = response.read().decode()
            for name in ('telegram receiver', 'ui-button', 'agent-server'):
                assert name in nodes, f'{role}: missing palette node {name}'
            print(role + ': selected modules loaded')
        token = (app.state / 'jupyter-token').read_text().strip()
        with urllib.request.urlopen(f'http://127.0.0.1:{ports["jupyter"]}/api/kernelspecs?token={token}') as response:
            kernels = __import__('json').load(response)
        assert 'python3' in kernels['kernelspecs']
        print('jupyter: authenticated API and Python kernel passed')
    finally:
        import signal
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for handle in handles:
            handle.close()
