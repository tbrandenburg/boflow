"""Disposable Ubuntu roundtrip using real Git, runtimes and systemd user services."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('boflow', ROOT / 'src/boflow.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def run(args, cwd=None, env=None):
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=1800)
    if result.returncode:
        errors = [line for line in result.stderr.splitlines() if line.startswith('boflow:')]
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): ' + '; '.join(errors))
    return result.stdout.strip()


def commit(directory, message):
    run(['git', '-C', directory, 'add', '.'])
    run(['git', '-C', directory, '-c', 'user.name=Acceptance', '-c',
         'user.email=acceptance@example.test', 'commit', '-m', message])
    return run(['git', '-C', directory, 'rev-parse', 'HEAD'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port-base', type=int, default=11880)
    args = parser.parse_args()
    if os.getuid() == 0 or platform.system() != 'Linux' or platform.freedesktop_os_release().get('ID') != 'ubuntu':
        raise RuntimeError('Run native acceptance as a non-root Ubuntu account.')
    ports = dict(zip(b.ROLES, range(args.port_base, args.port_base + 3)))
    b.App.validate_ports(ports)
    units = [Path.home() / '.config/systemd/user' / f'boflow-{role}.service' for role in b.ROLES]
    startup = Path.home() / '.config/autostart/boflow.desktop'
    if any(path.exists() for path in [*units, startup]):
        raise RuntimeError('Existing boflow service files; use a disposable account.')
    for role in b.ROLES:
        result = subprocess.run(['systemctl', '--user', 'show', f'boflow-{role}.service',
                                 '--property=LoadState', '--value'], capture_output=True, text=True, timeout=10)
        if result.returncode or result.stdout.strip() != 'not-found':
            raise RuntimeError('User manager unavailable or an existing boflow unit is loaded.')
    with tempfile.TemporaryDirectory(prefix='boflow-acceptance-') as temporary:
        root = Path(temporary)
        product = root / 'product-source'
        product.mkdir()
        for name in ('src', 'examples', 'ansible'):
            shutil.copytree(ROOT / name, product / name,
                            ignore=shutil.ignore_patterns('node_modules', '.venv', '__pycache__'))
        for name in ('bootstrap.sh', 'Makefile', 'pyproject.toml', 'uv.lock', '.gitignore'):
            shutil.copy2(ROOT / name, product / name)
        run(['git', 'init', '-b', 'main', product])
        product_sha = commit(product, 'Acceptance product fixture')
        household = root / 'household-source'
        shutil.copytree(product / 'examples/household', household)
        home = household / 'home.yml'
        home.write_text(home.read_text().replace('REPLACE_WITH_PRODUCT_COMMIT', product_sha))
        run(['git', 'init', '-b', 'main', household])
        commit(household, 'Acceptance household fixture')
        state = root / 'state'
        env = {**os.environ, 'BOFLOW_STATE': str(state), 'GIT_CONFIG_COUNT': '2',
               'GIT_CONFIG_KEY_0': f'url.{household}.insteadOf',
               'GIT_CONFIG_VALUE_0': 'git@github.com:acceptance/household.git',
               'GIT_CONFIG_KEY_1': f'url.{product}.insteadOf',
               'GIT_CONFIG_VALUE_1': b.PRODUCT_URL}
        registered = False
        try:
            run(['bash', 'bootstrap.sh'], cwd=product, env=env)
            launcher = state / 'bin/boflow'
            run([launcher, 'status'], env=env)
            run([launcher, 'doctor'], env=env)
            run([launcher, 'enroll', '--repo', 'acceptance/household'], env=env)
            registered = True  # Cleanup even if registration fails halfway.
            try:
                run([product / '.venv/bin/python', product / 'src/boflow.py', 'register-user', '--port-base', str(args.port_base)], cwd=product, env=env)
            except RuntimeError:
                for role in b.ROLES:
                    print(role + ': ' + run(['systemctl', '--user', 'show', f'boflow-{role}.service',
                          '--property=ActiveState,SubState,Result,ExecMainStatus,MainPID']))
                raise
            print('Bootstrap, enrollment, pinned-product registration: passed')

            def pids():
                return {role: run(['systemctl', '--user', 'show', f'boflow-{role}.service',
                                  '--property=MainPID', '--value']) for role in b.ROLES}

            def check():
                app = b.App(state)
                app.health()
                assert app.settings['ports'] == ports
                assert app.settings['applied_product'] == product_sha
                token = (state / 'jupyter-token').read_text().strip()
                with urllib.request.urlopen(f'http://127.0.0.1:{ports["jupyter"]}/api/kernelspecs?token={token}', timeout=5) as response:
                    assert 'python3' in json.load(response)['kernelspecs']
                for role in ('managed', 'personal'):
                    with urllib.request.urlopen(f'http://127.0.0.1:{ports[role]}/nodes', timeout=5) as response:
                        nodes = response.read().decode()
                    assert all(name in nodes for name in ('telegram receiver', 'ui-button', 'agent-server'))

            check()
            print('Three HTTP endpoints, Node-RED palettes, authenticated Jupyter kernel: passed')
            personal = state / 'personal/flows.json'
            personal.write_text('[{"id":"acceptance-personal","type":"tab","label":"Personal"}]')
            notebook = state / 'notebooks/acceptance.ipynb'
            notebook.write_text('{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}')
            preserved = {path: path.read_bytes() for path in
                         (personal, notebook, state / 'personal/credential-key', state / 'jupyter-token')}
            before = pids()
            run([product / '.venv/bin/python', product / 'src/boflow.py', 'register-user', '--port-base', str(args.port_base)], cwd=product, env=env)
            run([launcher, 'update'], env=env)
            check()
            assert before == pids(), 'Unchanged update restarted a service'
            assert all(path.read_bytes() == data for path, data in preserved.items())
            print('Repeat registration/update preserves PIDs, ports, data and secrets: passed')
            (household / 'node-red/flows.json').write_text('[{"id":"acceptance-managed","type":"tab","label":"Managed"}]')
            flow_sha = commit(household, 'Change managed flow')
            run([launcher, 'update'], env=env)
            check()
            after = pids()
            assert after['managed'] != before['managed']
            assert after['personal'] == before['personal'] and after['jupyter'] == before['jupyter']
            assert b.load_json(state / 'account.json')['applied_commit'] == flow_sha
            print('Managed flow update restarts managed service only: passed')
            offline = {**env, 'GIT_CONFIG_KEY_0': f'url.{root / "absent"}.insteadOf'}
            result = subprocess.run([str(launcher), 'login'], env=offline, capture_output=True,
                                    text=True, timeout=120)
            assert result.returncode != 0
            check()
            assert after == pids()
            assert b.load_json(state / 'attempt.json')['stage'] == 'failed'
            print('Offline login retains live services and records failure: passed')
            run([launcher, 'update'], env=env)
            run([product / '.venv/bin/python', product / 'src/boflow.py', 'remove-user'], cwd=product, env=env)
            assert not b.load_json(state / 'account.json')['registered']
            assert all(path.read_bytes() == data for path, data in preserved.items())
            assert not any(path.exists() for path in [*units, startup])
            b.App.validate_ports(ports)
            print('Removal removes startup/services, frees ports and preserves data: passed')
            registered = False
        finally:
            if registered:
                run([product / '.venv/bin/python', product / 'src/boflow.py', 'remove-user'], cwd=product, env=env)
            for role in b.ROLES:
                subprocess.run(['systemctl', '--user', 'reset-failed', f'boflow-{role}.service'],
                               capture_output=True, text=True, timeout=10)
            b.App.validate_ports(ports)
            assert not any(path.exists() for path in [*units, startup])
    print('Disposable repositories, runtime caches and test data cleaned up')


if __name__ == '__main__':
    main()
