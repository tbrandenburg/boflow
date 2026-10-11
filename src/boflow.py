#!/usr/bin/env python3
"""Account-local orchestration. Native package changes are always explicit."""
import argparse
import contextlib
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
import webbrowser

import yaml

SOURCE = Path(__file__).resolve().parents[1]
PRODUCT_URL = 'https://github.com/tbrandenburg/boflow.git'
ROLES = ('managed', 'personal', 'jupyter')
STARTER_FILES = ('home.yml', '.gitignore', 'AGENTS.md', 'node-red/package.json',
                 'node-red/package-lock.json', 'node-red/flows.json',
                 'jupyter/pyproject.toml', 'jupyter/uv.lock',
                 'tools/npm/package.json', 'tools/npm/package-lock.json',
                 'tools/python-tools.txt')


class Error(Exception):
    pass


def run(args, **kwargs):
    """No shell interpolation; bounded network and process operations."""
    try:
        return subprocess.run([str(a) for a in args], check=True, text=True,
                              timeout=kwargs.pop('timeout', 600), **kwargs)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise Error(f'Command failed: {args[0]} (see update log)') from exc


def output(args, **kwargs):
    return run(args, stdout=subprocess.PIPE, **kwargs).stdout.strip()


def write(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(data)
    tmp.chmod(mode)
    tmp.replace(path)


def load_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def link(target, path):
    tmp = path.with_name(path.name + '.next')
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target, target_is_directory=True)
    tmp.replace(path)


def repo_name(value):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value):
        raise Error('Repository must be OWNER/NAME, without credentials or a URL.')
    return value


def config(directory, overrides=None):
    cfg = yaml.safe_load((directory / 'home.yml').read_text())
    if not isinstance(cfg, dict) or cfg.get('schema') != 1:
        raise Error('Unsupported home.yml schema; expected schema: 1.')
    if overrides and overrides.exists():
        local = yaml.safe_load(overrides.read_text()) or {}
        if not isinstance(local, dict) or set(local) - {'native'}:
            raise Error('local.yml supports only native package overrides in v1.')
        cfg['native'] = {**cfg.get('native', {}), **local.get('native', {})}
    if not re.fullmatch(r'[0-9a-f]{40}', str(cfg.get('product_ref', ''))):
        raise Error('product_ref must be a full product commit SHA.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', str(cfg.get('node', ''))):
        raise Error('node must be an exact Node.js version.')
    if cfg.get('python') != '3.12':
        raise Error('V1 supports Python 3.12; changing it needs product support.')
    native = cfg.get('native', {})
    for os_name in ('ubuntu', 'macos'):
        if not isinstance(native.get(os_name), list) or any(
                not re.fullmatch(r'[A-Za-z0-9@+_.-]+', str(p)) for p in native[os_name]):
            raise Error(f'native.{os_name} must be a list of package names.')
    for folder in ('node-red', 'tools/npm'):
        manifest = load_json(directory / folder / 'package.json')
        lockfile = load_json(directory / folder / 'package-lock.json')
        if not manifest or not lockfile:
            raise Error(f'{folder}: commit package.json and package-lock.json.')
        if manifest.get('dependencies', {}) != lockfile['packages'][''].get('dependencies', {}):
            raise Error(f'{folder}: lockfile does not match package.json; run lock.')
        if any(not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', str(v))
               for v in manifest.get('dependencies', {}).values()):
            raise Error(f'{folder}: use exact dependency versions.')
    if 'node-red' not in load_json(directory / 'node-red/package.json')['dependencies']:
        raise Error('The node-red manifest must include node-red.')
    flows = load_json(directory / 'node-red/flows.json')
    if not isinstance(flows, list):
        raise Error('flows.json must be an array.')
    ids = [n.get('id') for n in flows]
    if any(not i for i in ids) or len(ids) != len(set(ids)):
        raise Error('Flow node IDs must be present and unique.')
    if any('credentials' in n for n in flows):
        raise Error('Keep inline credentials out of exported flows.')
    if not (directory / 'jupyter/uv.lock').is_file():
        raise Error('Commit jupyter/uv.lock; run lock.')
    python_tools(directory)
    return cfg


def python_tools(directory):
    specs = []
    for line in (directory / 'tools/python-tools.txt').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==\d+(?:\.\d+)+(?:[a-z0-9.]*)', line):
            raise Error('Python CLI tools require one package==version per line.')
        specs.append(line)
    return specs


def digest(*paths):
    h = hashlib.sha256()
    for path in paths:
        h.update(str(path.name).encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:20]


class App:
    def __init__(self, state=None):
        self.state = Path(state or os.environ.get('BOFLOW_STATE',
                         str(Path.home() / '.local/share/boflow'))).expanduser().resolve()
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state.chmod(0o700)
        self.settings_path = self.state / 'account.json'
        self.settings = load_json(self.settings_path, {})
        self.bin = self.state / 'bin/boflow'

    def save(self):
        write(self.settings_path, json.dumps(self.settings, indent=2) + '\n')

    @contextlib.contextmanager
    def locked(self):
        with (self.state / 'update.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Error('Another account update is already running; retry later.')
            yield

    def install_launcher(self):
        # Stable bootstrap checkout. Pinned product code is separate from it.
        pinned = self.state / 'product/src/boflow.py'
        text = '#!/bin/sh\nif [ -f ' + shlex.quote(str(pinned)) + ' ]; then\n'
        text += '  exec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(pinned)) + ' "$@"\nfi\n'
        text += 'exec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(SOURCE / 'src/boflow.py')) + ' "$@"\n'
        write(self.bin, text, 0o700)
        print(f'Command: {self.bin}')

    def git_env(self):
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        env['GIT_SSH_COMMAND'] = ' '.join([
            'ssh', '-i', shlex.quote(str(self.state / 'deploy-key')),
            '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + shlex.quote(str(self.state / 'known_hosts'))])
        return env

    def fetch(self, url, folder, ref, private=False):
        env = self.git_env() if private else {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
        if not (folder / '.git').exists():
            folder.mkdir(parents=True, exist_ok=True)
            run(['git', 'init', folder])
            run(['git', '-C', folder, 'remote', 'add', 'origin', url])
        actual = output(['git', '-C', folder, 'config', '--get', 'remote.origin.url'])
        if actual != url:
            raise Error('Deployment checkout has a different origin; inspect it first.')
        run(['git', '-C', folder, 'fetch', '--depth=1', 'origin', ref], env=env, timeout=90)
        sha = output(['git', '-C', folder, 'rev-parse', 'FETCH_HEAD'])
        run(['git', '-C', folder, 'checkout', '--detach', '--force', sha])
        return sha

    def enroll(self, repo, quiet=False):
        repo = repo_name(repo)
        if self.settings.get('repo') not in (None, repo):
            raise Error('Already enrolled in another household; remove enrollment first.')
        key = self.state / 'deploy-key'
        if not key.exists():
            run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-C',
                 f'boflow-{platform.node()}-{os.getuid()}', '-f', key])
        key.chmod(0o600)
        self.settings['repo'] = repo
        self.save()
        if not quiet:
            print('Admin: register this PUBLIC key as a read-only deploy key:')
            print(key.with_suffix('.pub').read_text())
            print(f'https://github.com/{repo}/settings/keys')
            print('Then run register-user. No private key needs to leave this account.')

    def node(self, version):
        system = platform.system()
        if system not in ('Linux', 'Darwin'):
            raise Error('Only Ubuntu and macOS are supported.')
        if system == 'Linux':
            os_release = platform.freedesktop_os_release()
            if os_release.get('ID') != 'ubuntu':
                raise Error('V1 Linux support is Ubuntu only.')
        arch = {'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine())
        if not arch:
            raise Error('Unsupported CPU architecture.')
        folder = self.state / 'runtimes' / f'node-{version}'
        if (folder / 'bin/node').exists():
            return folder
        name = f'node-v{version}-{"darwin" if system == "Darwin" else "linux"}-{arch}'
        base = f'https://nodejs.org/dist/v{version}/'
        with tempfile.TemporaryDirectory(dir=self.state) as temp:
            archive = Path(temp) / (name + '.tar.gz')
            with urllib.request.urlopen(base + 'SHASUMS256.txt', timeout=30) as response:
                sums = response.read().decode()
            expected = next((line.split()[0] for line in sums.splitlines()
                             if line.split()[-1] == archive.name), None)
            if not expected:
                raise Error('Node archive is absent from upstream checksum manifest.')
            with urllib.request.urlopen(base + archive.name, timeout=60) as response:
                archive.write_bytes(response.read())
            if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
                raise Error('Node archive checksum mismatch.')
            with tarfile.open(archive) as bundle:
                bundle.extractall(temp, filter='data')
            folder.parent.mkdir(exist_ok=True)
            shutil.move(str(Path(temp) / name), folder)
        return folder

    def env(self, node=None):
        env = os.environ.copy()
        paths = [self.state / 'tools-npm/node_modules/.bin', self.state / 'tools-python/bin']
        if node:
            paths.append(node / 'bin')
        elif self.settings.get('node_path'):
            paths.append(Path(self.settings['node_path']) / 'bin')
        paths += [Path.home() / '.local/bin', Path('/opt/homebrew/bin'), Path('/usr/local/bin')]
        env['PATH'] = os.pathsep.join(map(str, paths)) + os.pathsep + env.get('PATH', '')
        return env

    def release(self, component, key, prepare):
        dest = self.state / 'releases' / component / key
        if not (dest / '.ready').exists():
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            prepare(dest)
            write(dest / '.ready', 'ready\n')
        return dest

    def update(self):
        if not self.settings.get('repo'):
            raise Error('Run enroll first.')
        with self.locked():
            write(self.state / 'attempt.json', json.dumps({'time': time.time(), 'stage': 'fetching'}))
            household = self.state / 'household'
            sha = self.fetch('git@github.com:' + self.settings['repo'] + '.git', household,
                             'main', private=True)
            cfg = config(household, self.state / 'local.yml')
            product = self.state / 'products' / cfg['product_ref']
            if (product / '.git').exists():
                fetched_product = output(['git', '-C', product, 'rev-parse', 'HEAD'])
            else:
                fetched_product = self.fetch(PRODUCT_URL, product, cfg['product_ref'])
            if fetched_product != cfg['product_ref']:
                raise Error('Product fetch did not return the pinned commit.')
            # The stable launcher delegates updates to exactly the pinned product.
            if SOURCE != product.resolve():
                run([sys.executable, product / 'src/boflow.py', 'apply', '--commit', sha],
                    env={**os.environ, 'BOFLOW_STATE': str(self.state)}, timeout=1800)
            else:
                self.apply(sha)
            # A pinned-product subprocess owns activation and writes account state.
            # Reload before registration or any subsequent save in this process.
            self.settings = load_json(self.settings_path, {})
            write(self.state / 'attempt.json', json.dumps({'time': time.time(), 'stage': 'successful'}))

    def apply(self, sha):
        household = self.state / 'household'
        cfg = config(household, self.state / 'local.yml')
        node = self.node(cfg['node'])
        env = self.env(node)
        nr = household / 'node-red'
        runtime_key = digest(nr / 'package.json', nr / 'package-lock.json') + '-' + cfg['node']
        def npm_prepare(dest, source):
            for filename in ('package.json', 'package-lock.json'):
                shutil.copy2(source / filename, dest / filename)
            run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=dest, env=env)
        runtime = self.release('node-red', runtime_key, lambda d: npm_prepare(d, nr))
        tools_src = household / 'tools/npm'
        tools = self.release('npm-tools', digest(tools_src / 'package.json',
                             tools_src / 'package-lock.json') + '-' + cfg['node'],
                             lambda d: npm_prepare(d, tools_src))
        jup_src = household / 'jupyter'
        def jupyter_prepare(dest):
            for filename in ('pyproject.toml', 'uv.lock'):
                shutil.copy2(jup_src / filename, dest / filename)
            run(['uv', 'sync', '--locked', '--python', cfg['python']], cwd=dest, env=env)
        jupyter = self.release('jupyter', digest(jup_src / 'pyproject.toml', jup_src / 'uv.lock'),
                               jupyter_prepare)
        specs = python_tools(household)
        def python_prepare(dest):
            tool_env = {**env, 'UV_TOOL_DIR': str(dest / 'envs'), 'UV_TOOL_BIN_DIR': str(dest / 'bin')}
            (dest / 'bin').mkdir()
            for spec in specs:
                run(['uv', 'tool', 'install', '--python', cfg['python'], spec], env=tool_env)
        pytools = self.release('python-tools', digest(household / 'tools/python-tools.txt'), python_prepare)
        # Personal palette owns its manifest. Merge the baseline without removing extras.
        personal = self.state / 'personal'
        personal.mkdir(exist_ok=True)
        baseline = load_json(nr / 'package.json')
        desired = load_json(personal / 'package.json', baseline.copy())
        desired['dependencies'] = {**desired.get('dependencies', {}), **baseline['dependencies']}
        personal_key = hashlib.sha256(json.dumps(desired, sort_keys=True).encode()).hexdigest()[:20] + '-' + cfg['node']
        def personal_prepare(dest):
            write(dest / 'package.json', json.dumps(desired))
            old_lock = personal / 'package-lock.json'
            if old_lock.exists():
                shutil.copy2(old_lock, dest / 'package-lock.json')
            else:
                shutil.copy2(nr / 'package-lock.json', dest / 'package-lock.json')
            run(['npm', 'install', '--package-lock-only', '--no-audit', '--no-fund'], cwd=dest, env=env)
            run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=dest, env=env)
        personal_runtime = self.release('personal', personal_key, personal_prepare)
        pointers = {'managed-runtime': runtime, 'personal-runtime': personal_runtime,
                    'jupyter-runtime': jupyter, 'tools-npm': tools, 'tools-python': pytools}
        previous = {name: str((self.state / name).resolve()) if (self.state / name).exists() else None
                    for name in pointers}
        flow_hash = digest(nr / 'flows.json')
        changed = set()
        if previous['managed-runtime'] != str(runtime) or self.settings.get('flow_hash') != flow_hash:
            changed.add('managed')
        if previous['personal-runtime'] != str(personal_runtime):
            changed.add('personal')
        if previous['jupyter-runtime'] != str(jupyter):
            changed.add('jupyter')
        if self.settings.get('node_path') != str(node):
            changed.update(ROLES)
        # Stop before changing dependencies or flows. Preparation never stops working services.
        if self.settings.get('registered'):
            for role in changed:
                self.service('stop', role, required=False)
        for name, target in pointers.items():
            link(target, self.state / name)
        managed = self.state / 'managed'
        managed.mkdir(exist_ok=True)
        if self.settings.get('flow_hash') != flow_hash:
            shutil.copy2(nr / 'flows.json', managed / 'flows.json')
        for role, runtime_folder in (('managed', runtime), ('personal', personal_runtime)):
            user_dir = self.state / role
            if not (user_dir / 'credential-key').exists():
                write(user_dir / 'credential-key', secrets.token_hex(32))
            modules = user_dir / 'node_modules'
            if modules.exists() and not modules.is_symlink():
                raise Error('Existing node_modules directory: move it aside after backing up.')
            link(runtime_folder / 'node_modules', modules)
        for filename in ('package.json', 'package-lock.json'):
            shutil.copy2(personal_runtime / filename, personal / filename)
        if not (personal / 'flows.json').exists():
            write(personal / 'flows.json', '[]\n')
        (self.state / 'notebooks').mkdir(exist_ok=True)
        self.settings.update(node_path=str(node), flow_hash=flow_hash)
        self.save()
        link(SOURCE, self.state / 'product')
        if self.settings.get('registered'):
            self.install_services()
            for role in ROLES:
                # start is idempotent on systemd; launchd may already have loaded it.
                self.service('start', role, required=platform.system() != 'Darwin')
            self.health()
        self.settings.update(applied_commit=sha, applied_product=cfg['product_ref'],
                             last_success=time.time())
        self.save()
        print(f'Applied {sha}; restarted: {", ".join(sorted(changed)) or "none"}')

    def service(self, action, role, required=True):
        label = f'org.boflow.{role}'
        try:
            if platform.system() == 'Darwin':
                target = f'gui/{os.getuid()}/{label}'
                if action == 'stop':
                    run(['launchctl', 'bootout', target])
                else:
                    path = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
                    run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', path])
            else:
                run(['systemctl', '--user', action, f'boflow-{role}.service'])
        except Error:
            if required:
                raise

    def install_services(self):
        env = self.env()
        for role in ROLES:
            args = [str(self.bin), 'serve', role]
            if platform.system() == 'Darwin':
                folder = Path.home() / 'Library/LaunchAgents'
                folder.mkdir(parents=True, exist_ok=True)
                data = {'Label': f'org.boflow.{role}', 'ProgramArguments': args,
                        'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False},
                        'EnvironmentVariables': {'BOFLOW_STATE': str(self.state), 'PATH': env['PATH']},
                        'StandardOutPath': str(self.state / (role + '.log')),
                        'StandardErrorPath': str(self.state / (role + '.log'))}
                path = folder / f'org.boflow.{role}.plist'
                write(path, plistlib.dumps(data).decode())
            else:
                def quote(value):
                    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'
                text = ('[Unit]\nDescription=boflow ' + role + '\nPartOf=graphical-session.target\n'
                        '[Service]\nType=simple\nExecStart=' + ' '.join(map(quote, args)) + '\n'
                        'Environment=' + quote('BOFLOW_STATE=' + str(self.state)) + '\n'
                        'Environment=' + quote('PATH=' + env['PATH']) + '\n'
                        'Restart=on-failure\nRestartSec=5\nKillMode=control-group\n'
                        '[Install]\nWantedBy=graphical-session.target\n')
                write(Path.home() / '.config/systemd/user' / f'boflow-{role}.service', text)
        if platform.system() != 'Darwin':
            run(['systemctl', '--user', 'daemon-reload'])

    def register(self, port_base=None):
        if not self.settings.get('repo'):
            raise Error('Run enroll and authorize its deploy key first.')
        ports = (dict(zip(ROLES, range(port_base, port_base + 3)))
                 if port_base is not None else self.settings.get('ports'))
        if self.settings.get('ports') and ports != self.settings['ports']:
            raise Error('Existing ports differ; remove services, then edit account.json before retrying.')
        if ports is not None:
            self.validate_ports(ports, check_available=not self.settings.get('registered'))
        self.install_launcher()
        if not self.settings.get('ports'):
            self.settings['ports'] = ports if ports is not None else self.allocate_ports()
            self.save()
        # First setup prepares applications before installing login startup.
        self.update()
        self.settings['registered'] = True
        self.save()
        self.install_services()
        if platform.system() == 'Darwin':
            path = Path.home() / 'Library/LaunchAgents/org.boflow.login.plist'
            data = {'Label': 'org.boflow.login', 'ProgramArguments': [str(self.bin), 'login'],
                    'RunAtLoad': True, 'EnvironmentVariables': {'BOFLOW_STATE': str(self.state)},
                    'StandardOutPath': str(self.state / 'login.log'),
                    'StandardErrorPath': str(self.state / 'login.log')}
            write(path, plistlib.dumps(data).decode())
        else:
            # Desktop autostart supplies the real user's graphical session environment.
            command = '"' + str(self.bin).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '" login'
            write(Path.home() / '.config/autostart/boflow.desktop',
                  '[Desktop Entry]\nType=Application\nName=boflow\nExec=' + command + '\nTerminal=false\n')
        for role in ROLES:
            self.service('start', role, required=False)
        self.health()
        self.landing()
        print('Registration complete. Run boflow open to access your tools.')

    @staticmethod
    def validate_ports(ports, check_available=True):
        if (set(ports) != set(ROLES) or
                any(type(port) is not int or not 1024 <= port <= 65535 for port in ports.values()) or
                len(set(ports.values())) != len(ROLES)):
            raise Error('Choose three distinct unprivileged ports between 1024 and 65535.')
        if not check_available:
            return
        sockets = []
        try:
            for port in ports.values():
                sock = socket.socket()
                sockets.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(('127.0.0.1', port))
                except OSError as exc:
                    raise Error(f'Port {port} is occupied; choose another port block.') from exc
        finally:
            for sock in sockets:
                sock.close()

    @staticmethod
    def allocate_ports():
        # Prefer familiar default ports, then search without touching listeners.
        for base in range(11880, 50000, 3):
            with contextlib.ExitStack() as stack:
                try:
                    for port in range(base, base + 3):
                        sock = stack.enter_context(socket.socket())
                        sock.bind(('127.0.0.1', port))
                except OSError:
                    continue
                return dict(zip(ROLES, range(base, base + 3)))
        raise Error('No free three-port block available for this account.')


    def health(self):
        for role, port in self.settings['ports'].items():
            # Native palette/kernel startup can be slow on a busy target machine.
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.5)
            else:
                raise Error(f'{role} failed its HTTP startup check; run doctor/logs.')

    def serve(self, role):
        if role not in ROLES or not self.settings.get('ports'):
            raise Error('Register this account first.')
        port = self.settings['ports'][role]
        env = self.env()
        if role == 'jupyter':
            secret_file = self.state / 'jupyter-token'
            if not secret_file.exists():
                write(secret_file, secrets.token_urlsafe(32))
            cfg = self.state / 'jupyter-config.py'
            write(cfg, 'from pathlib import Path\n' +
                  'c.ServerApp.ip = "127.0.0.1"\nc.ServerApp.open_browser = False\n' +
                  f'c.ServerApp.port = {port}\nc.ServerApp.port_retries = 0\n' +
                  f'c.ServerApp.root_dir = {str(self.state / "notebooks")!r}\n' +
                  f'c.IdentityProvider.token = Path({str(secret_file)!r}).read_text().strip()\n')
            exe = self.state / 'jupyter-runtime/.venv/bin/jupyter'
            args = [str(exe), 'lab', '--config', str(cfg)]
        else:
            user_dir = self.state / role
            settings_file = user_dir / 'settings.js'
            write(settings_file, 'const fs = require("fs");\nmodule.exports = ' + json.dumps({
                'uiHost': '127.0.0.1', 'uiPort': port, 'flowFile': 'flows.json',
                'contextStorage': {'default': {'module': 'localfilesystem'}},
                'editorTheme': {'projects': {'enabled': False}},
                'externalModules': {'palette': {'allowInstall': role == 'personal'}}})[:-1] +
                ', credentialSecret: fs.readFileSync(' + json.dumps(str(user_dir / 'credential-key')) +
                ', "utf8").trim()};\n')
            exe = self.state / f'{role}-runtime/node_modules/node-red/red.js'
            args = [str(Path(self.settings['node_path']) / 'bin/node'), str(exe),
                    '--userDir', str(user_dir), '--settings', str(settings_file)]
        if (self.state / 'secrets.env').exists():
            # Deliberately not a shell script. KEY=value, no expansion or execution.
            for line in (self.state / 'secrets.env').read_text().splitlines():
                if line.strip() and not line.lstrip().startswith('#'):
                    key, sep, value = line.partition('=')
                    if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
                        raise Error('secrets.env requires uppercase KEY=value lines.')
                    if key in ('PATH', 'HOME', 'BOFLOW_STATE', 'NODE_OPTIONS', 'PYTHONPATH'):
                        raise Error('secrets.env cannot override runtime control variables.')
                    env[key] = value
        os.execvpe(args[0], args, env)

    def landing(self):
        ports = self.settings['ports']
        links = [('Managed Node-RED', f'http://127.0.0.1:{ports["managed"]}/'),
                 ('Personal Node-RED', f'http://127.0.0.1:{ports["personal"]}/'),
                 ('Dashboard', f'http://127.0.0.1:{ports["managed"]}/dashboard/')]
        token = (self.state / 'jupyter-token').read_text().strip()
        links.append(('JupyterLab', f'http://127.0.0.1:{ports["jupyter"]}/lab?token={token}'))
        page = '<!doctype html><meta charset="utf-8"><title>boflow</title><h1>Your household tools</h1>'
        page += ''.join(f'<p><a href="{html.escape(url, quote=True)}">{name}</a></p>' for name, url in links)
        page += '<p>Local account access. Remote administration uses SSH tunnels.</p>'
        directory = Path.home() / 'boflow'
        if directory.is_symlink():
            raise Error('Refusing to write the private tools page through a ~/boflow symlink.')
        directory.mkdir(mode=0o700, exist_ok=True)
        if not directory.is_dir() or directory.stat().st_uid != os.getuid():
            raise Error('The ~/boflow tools-page directory must be owned by this account.')
        path = directory / 'index.html'
        write(path, page)
        return path

    def login(self):
        if not self.settings.get('registered'):
            raise Error('Register this account first.')
        if platform.system() != 'Darwin':
            names = [name for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_CURRENT_DESKTOP',
                     'DBUS_SESSION_BUS_ADDRESS') if name in os.environ]
            if names:
                run(['systemctl', '--user', 'import-environment', *names])
        for role in ROLES:
            # launchd may already have loaded this job at login.
            self.service('start', role, required=False)
        self.update()

    def status(self):
        print(json.dumps({**self.settings, 'last_attempt': load_json(self.state / 'attempt.json')}, indent=2))
        for role, port in self.settings.get('ports', {}).items():
            with socket.socket() as sock:
                sock.settimeout(1)
                print(f'{role}: port {port}, ' + ('reachable' if sock.connect_ex(('127.0.0.1', port)) == 0 else 'stopped'))

    def native(self, upgrade=False):
        if not self.settings.get('repo'):
            raise Error('Run enroll and authorize its deploy key first.')
        with self.locked():
            self.fetch('git@github.com:' + self.settings['repo'] + '.git',
                       self.state / 'household', 'main', private=True)
        cfg = config(self.state / 'household', self.state / 'local.yml')
        args = [str(Path(sys.executable).parent / 'ansible-playbook'), str(SOURCE / 'ansible/native.yml'),
                '-i', 'localhost,', '-e', json.dumps({'native': cfg['native'], 'upgrade_native': upgrade})]
        if platform.system() == 'Linux':
            args.append('--ask-become-pass')
        run(args, env=self.env(), timeout=1800)

    def remove(self):
        for role in ROLES:
            self.service('stop', role, required=False)
            path = (Path.home() / f'Library/LaunchAgents/org.boflow.{role}.plist'
                    if platform.system() == 'Darwin' else
                    Path.home() / f'.config/systemd/user/boflow-{role}.service')
            path.unlink(missing_ok=True)
        if platform.system() == 'Darwin':
            with contextlib.suppress(Error):
                run(['launchctl', 'bootout', f'gui/{os.getuid()}/org.boflow.login'])
            (Path.home() / 'Library/LaunchAgents/org.boflow.login.plist').unlink(missing_ok=True)
        else:
            (Path.home() / '.config/autostart/boflow.desktop').unlink(missing_ok=True)
            run(['systemctl', '--user', 'daemon-reload'])
        self.settings['registered'] = False
        self.save()
        print('Startup removed; all data retained. Admin must revoke this account deploy key on GitHub.')


def init_home(repo, directory):
    repo = repo_name(repo)
    directory = Path(directory).expanduser().absolute()
    directory.mkdir(parents=True, exist_ok=True)
    version = output(['git', '-C', SOURCE, 'rev-parse', 'HEAD'])
    for filename in STARTER_FILES:
        source = SOURCE / 'examples/household' / filename
        dest = directory / filename
        if not dest.exists():
            text = source.read_text().replace('REPLACE_WITH_PRODUCT_COMMIT', version)
            write(dest, text)
    if not (directory / '.git').exists():
        run(['git', 'init', '-b', 'main', directory])
    if not output(['git', '-C', directory, 'status', '--porcelain']):
        print('Starter already initialized; no changes.')
    else:
        head = subprocess.run(['git', '-C', directory, 'rev-parse', '--verify', 'HEAD'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if head.returncode == 0:
            raise Error('Household working checkout has changes. Review and commit them before resuming init-home.')
        # Only starter paths. No git add . that might publish unrelated secrets.
        run(['git', '-C', directory, 'add', '--', *STARTER_FILES])
        run(['git', '-C', directory, 'commit', '-m', 'Initialize private boflow household'])
    probe = subprocess.run(['gh', 'repo', 'view', repo, '--json', 'visibility'], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if probe.returncode == 0:
        if json.loads(probe.stdout)['visibility'] != 'PRIVATE':
            raise Error('Refusing to push household configuration to a public repository.')
        expected = 'https://github.com/' + repo + '.git'
        remotes = output(['git', '-C', directory, 'remote'])
        if 'origin' not in remotes.splitlines():
            run(['git', '-C', directory, 'remote', 'add', 'origin', expected])
        actual = output(['git', '-C', directory, 'remote', 'get-url', 'origin'])
        if actual not in (expected, f'git@github.com:{repo}.git'):
            raise Error('Existing origin does not match household repository.')
        run(['git', '-C', directory, 'push', 'origin', 'main'])
    else:
        run(['gh', 'repo', 'create', repo, '--private', '--source', directory, '--remote', 'origin', '--push'])
    print(f'Household: https://github.com/{repo}. Keep this working checkout separate from deployment.')


def main():
    parser = argparse.ArgumentParser(description='boflow: account-local household tools')
    sub = parser.add_subparsers(dest='command', required=True)
    for cmd in ('setup', 'approve', 'install-launcher', 'update', 'login', 'status', 'doctor', 'logs', 'open', 'remove-user'):
        sub.add_parser(cmd)
    p = sub.add_parser('register-user')
    p.add_argument('--port-base', type=int, default=os.environ.get('BOFLOW_PORT_BASE'),
                   help='First of three consecutive loopback ports (BOFLOW_PORT_BASE); preserved on reruns')
    p = sub.add_parser('init-home'); p.add_argument('--repo', required=True); p.add_argument('--directory', required=True)
    p = sub.add_parser('enroll'); p.add_argument('--repo', required=True)
    p = sub.add_parser('native'); p.add_argument('--upgrade', action='store_true')
    p = sub.add_parser('serve'); p.add_argument('role', choices=ROLES)
    p = sub.add_parser('apply'); p.add_argument('--commit', required=True)
    for cmd in ('lock', 'export-managed-flows'):
        p = sub.add_parser(cmd); p.add_argument('--directory', required=True)
    args = parser.parse_args()
    if args.command == 'init-home':
        init_home(args.repo, args.directory); return
    if args.command == 'lock':
        directory = Path(args.directory).expanduser().absolute()
        for folder in ('node-red', 'tools/npm'):
            run(['npm', 'install', '--package-lock-only', '--no-audit', '--no-fund'], cwd=directory / folder)
        run(['uv', 'lock'], cwd=directory / 'jupyter')
        return
    app = App()
    if args.command in ('setup', 'approve'):
        from onboarding import setup, approve
        (setup if args.command == 'setup' else approve)(app)
    elif args.command in ('update', 'login'):
        with (app.state / 'update.log').open('a') as log:
            # Capture dependencies' output; never print token-bearing Jupyter service logs.
            saved = (os.dup(1), os.dup(2))
            try:
                sys.stdout.flush(); sys.stderr.flush()
                os.dup2(log.fileno(), 1); os.dup2(log.fileno(), 2)
                try:
                    getattr(app, args.command)()
                except Exception:
                    write(app.state / 'attempt.json', json.dumps({'time': time.time(), 'stage': 'failed'}))
                    raise
                finally:
                    sys.stdout.flush(); sys.stderr.flush()
            finally:
                os.dup2(saved[0], 1); os.dup2(saved[1], 2)
                os.close(saved[0]); os.close(saved[1])
        print('Update complete; run status for details.')
    elif args.command == 'register-user': app.register(args.port_base)
    elif args.command == 'install-launcher': app.install_launcher()
    elif args.command == 'enroll': app.enroll(args.repo)
    elif args.command == 'apply': app.apply(args.commit)
    elif args.command == 'serve': app.serve(args.role)
    elif args.command == 'native': app.native(args.upgrade)
    elif args.command == 'remove-user': app.remove()
    elif args.command == 'open': webbrowser.open(app.landing().as_uri())
    elif args.command == 'status': app.status()
    elif args.command == 'doctor':
        app.status()
        print('Platform:', platform.platform(), platform.machine())
        for tool in ('git', 'uv', 'ssh', 'systemctl' if platform.system() == 'Linux' else 'launchctl'):
            print(tool, shutil.which(tool) or 'MISSING')
        print('Node runtime:', app.settings.get('node_path', 'NOT PREPARED'))
        print('Update log:', app.state / 'update.log')
    elif args.command == 'logs':
        if (app.state / 'update.log').exists():
            print('\n'.join((app.state / 'update.log').read_text().splitlines()[-100:]))
        print('Service logs may contain secrets. Inspect locally; do not paste them unredacted.')
    elif args.command == 'export-managed-flows':
        target = Path(args.directory).expanduser().absolute()
        flows = load_json(app.state / 'personal/flows.json')
        if not isinstance(flows, list): raise Error('No personal authoring flows found.')
        for node in flows: node.pop('credentials', None)
        write(target / 'node-red/flows.json', json.dumps(flows, indent=2) + '\n')
        print('Exported personal authoring flows. Review secret references and git diff before publishing.')


if __name__ == '__main__':
    sys.modules['boflow'] = sys.modules[__name__]
    try:
        main()
    except (Error, OSError, ValueError, KeyError, EOFError, KeyboardInterrupt) as exc:
        print(f'boflow: {exc}', file=sys.stderr)
        sys.exit(1)
