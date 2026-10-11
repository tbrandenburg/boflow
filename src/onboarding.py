"""Interactive first-run journeys; never imported by login or update."""
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.request
import webbrowser

from boflow import Error, config, init_home, output, repo_name, run


def ask(prompt, default=None):
    answer = input(prompt + (f' [{default}]' if default is not None else '') + ': ').strip()
    return answer or default or ''


def consent(prompt):
    if ask(prompt + ' (y/n)', 'n').lower() not in ('y', 'yes'):
        raise Error('Setup paused. Rerun make setup when ready; existing data is retained.')


def repository(value):
    value = value.strip()
    if value.startswith('https://github.com/'):
        value = value[len('https://github.com/'):].rstrip('/')
    if value.endswith('.git'):
        value = value[:-4]
    return repo_name(value)


def key_data(key):
    if not isinstance(key, str):
        raise Error('Invalid public key.')
    parts = key.split()
    if len(parts) < 2 or parts[0] != 'ssh-ed25519':
        raise Error('Enrollment requires an Ed25519 public key.')
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except ValueError as exc:
        raise Error('Invalid public key.') from exc
    expected = struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32)
    if len(raw) != 51 or not raw.startswith(expected):
        raise Error('Invalid Ed25519 public key.')
    return ' '.join(parts[:2]), 'SHA256:' + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')


def request(app):
    key, _ = key_data((app.state / 'deploy-key.pub').read_text())
    data = {'schema': 1, 'repo': app.settings['repo'], 'label': app.settings['label'], 'key': key}
    return 'boflow1:' + base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_request(value):
    if len(value) > 4096 or not value.startswith('boflow1:'):
        raise Error('Paste the one-line boflow1 enrollment request.')
    try:
        data = json.loads(base64.b64decode(value[8:], altchars=b'-_', validate=True))
        if set(data) != {'schema', 'repo', 'label', 'key'} or data['schema'] != 1:
            raise ValueError()
        data['repo'] = repo_name(data['repo'])
        if not isinstance(data['label'], str) or not data['label'].strip() or len(data['label']) > 100 or any(ord(c) < 32 for c in data['label']):
            raise ValueError()
        data['key'], fingerprint = key_data(data['key'])
    except (ValueError, TypeError, KeyError) as exc:
        raise Error('Invalid enrollment request.') from exc
    return data, fingerprint


def deploy_keys(repo):
    endpoint = f'repos/{repo}/keys'
    command = ['gh', 'api', endpoint, '--paginate', '--jq', '.[]']
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=600)
    if result.returncode == 0:
        return [json.loads(line) for line in result.stdout.splitlines()]
    if 'unknown flag: --jq' not in result.stderr:
        raise Error('Command failed: gh (see update log)')

    pages = output(['gh', 'api', endpoint, '--paginate'])
    decoder = json.JSONDecoder()
    keys = []
    while pages.strip():
        pages = pages.lstrip()
        page, end = decoder.raw_decode(pages)
        if not isinstance(page, list):
            raise Error('GitHub CLI returned an invalid deploy-key response.')
        keys.extend(page)
        pages = pages[end:]
    return keys


def official_installer(url, interpreter):
    # Caller obtains consent. Download to a file rather than piping into a shell.
    with tempfile.TemporaryDirectory() as temp:
        script = Path(temp) / 'install.sh'
        with urllib.request.urlopen(url, timeout=30) as response:
            script.write_bytes(response.read())
        run([interpreter, script], timeout=1800)


def brew():
    for path in ('/opt/homebrew/bin', '/usr/local/bin'):
        if Path(path, 'brew').exists():
            os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
            break
    if not shutil.which('brew'):
        consent('Install Homebrew using its official installer as this machine’s package owner?')
        official_installer('https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh', '/bin/bash')
        for path in ('/opt/homebrew/bin', '/usr/local/bin'):
            if Path(path, 'brew').exists():
                os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
                break
        if not shutil.which('brew'):
            raise Error('Homebrew installation did not finish. Complete its instructions and rerun setup.')
    return Path(output(['brew', '--repository']))


def ensure_gh():
    if not shutil.which('gh'):
        if platform.system() == 'Darwin':
            prefix = brew()
            if prefix.stat().st_uid != os.getuid():
                raise Error('Homebrew owner must run brew install gh, then rerun this command.')
            consent('Install GitHub CLI with Homebrew?')
            run(['brew', 'install', 'gh'], timeout=1800)
        else:
            consent('Install GitHub CLI through apt (requires administrator permission)?')
            run(['sudo', 'apt-get', 'update'], timeout=1800)
            run(['sudo', 'apt-get', 'install', '-y', 'gh'], timeout=1800)
    probe = subprocess.run(['gh', 'auth', 'status', '--hostname', 'github.com'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if probe.returncode:
        print('Sign in as the household administrator in GitHub’s browser/device flow.')
        run(['gh', 'auth', 'login', '--hostname', 'github.com', '--git-protocol', 'https', '--web'])


def approve(app, value=None):
    data, fingerprint = decode_request(value or ask('Paste member enrollment request'))
    if not app.settings.get('repo') or data['repo'] != app.settings['repo']:
        raise Error('Request household differs from this account. Run make setup to select the intended household.')
    print(f"Household: {data['repo']}\nAccount label: {data['label']}\nPublic key: {fingerprint}")
    consent('Confirm this request came from the intended household member and grant read-only access?')
    ensure_gh()
    visibility = json.loads(output(['gh', 'api', f"repos/{data['repo']}"]))
    if not visibility.get('private'):
        raise Error('Refusing enrollment into a public household repository.')
    for key in deploy_keys(data['repo']):
        if key['key'].split()[:2] == data['key'].split():
            if not key['read_only']:
                raise Error('Existing deploy key has write access. Revoke it and retry.')
            print('This read-only key is already approved.')
            return
    payload = json.dumps({'title': 'Boflow ' + data['label'], 'key': data['key'], 'read_only': True})
    run(['gh', 'api', f"repos/{data['repo']}/keys", '--method', 'POST', '--input', '-'],
        input=payload, stdout=subprocess.DEVNULL)
    print('Approved. Member setup can now continue. Keep the administrator’s gh authorization active.')


def wait_access(app):
    print('Checking household access. Ctrl-C pauses safely; rerun make setup to resume.')
    # Ten minutes, bounded SSH attempts. No new server or member GitHub login.
    deadline = time.monotonic() + 600
    while True:
        try:
            with app.locked():
                app.fetch('git@github.com:' + app.settings['repo'] + '.git',
                          app.state / 'household', 'main', private=True)
            return
        except Error:
            if time.monotonic() >= deadline:
                raise Error('Approval/access not available yet. Admin checks the request; rerun make setup later.')
            print('Not accessible yet; waiting for approval or network access…')
            time.sleep(10)


def native_setup(app):
    cfg = config(app.state / 'household', app.state / 'local.yml')
    if platform.system() == 'Darwin':
        run(['xcode-select', '-p'])
        prefix = brew()
        installed = output(['brew', 'list', '--formula', '-1']).splitlines()
        missing = [p for p in cfg['native']['macos'] if p not in installed]
        if not missing:
            return
        if prefix.stat().st_uid != os.getuid():
            raise Error('Homebrew owner must run: brew install ' + ' '.join(missing) +
                        '. Then rerun make setup in this account; do not use sudo or change ownership.')
    else:
        missing = []
        for package in cfg['native']['ubuntu']:
            result = subprocess.run(['dpkg-query', '-W', '-f=${Status}', package], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
            if result.returncode or result.stdout.strip() != 'install ok installed':
                missing.append(package)
        if not missing:
            return
    consent('Install missing native packages: ' + ', '.join(missing) + '?')
    app.native()


def setup(app):
    if os.getuid() == 0:
        raise Error('Run setup as the participating account, never root.')
    if platform.system() == 'Darwin':
        run(['launchctl', 'print', f'gui/{os.getuid()}'], stdout=subprocess.DEVNULL)
    elif platform.system() == 'Linux' and platform.freedesktop_os_release().get('ID') == 'ubuntu':
        if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            raise Error('Run setup in this account’s graphical desktop session.')
    else:
        raise Error('Setup supports macOS and Ubuntu only.')
    if not app.settings.get('repo'):
        choice = ask('Create a household or join one? (create/join)', 'join').lower()
        if choice not in ('create', 'join'):
            raise Error('Choose create or join; rerun make setup.')
        repo = repository(ask('Household GitHub URL or OWNER/NAME'))
        if choice == 'create':
            ensure_gh()
            directory = Path(ask('Household working directory', str(Path.home() / 'my-household'))).expanduser()
            consent(f'Create/resume PRIVATE repository {repo} from starter files in {directory}?')
            # Authenticate HTTPS Git only on the administrator’s machine.
            run(['gh', 'auth', 'setup-git', '--hostname', 'github.com'])
            directory.mkdir(parents=True, exist_ok=True)
            if not (directory / '.git').exists():
                run(['git', 'init', '-b', 'main', directory])
            for name in ('user.name', 'user.email'):
                probe = subprocess.run(['git', '-C', directory, 'config', '--get', name],
                                       stdout=subprocess.DEVNULL, timeout=10)
                if probe.returncode:
                    identity = json.loads(output(['gh', 'api', 'user']))
                    value = identity['login'] if name == 'user.name' else f"{identity['id']}+{identity['login']}@users.noreply.github.com"
                    run(['git', '-C', directory, 'config', '--local', name, value])
            init_home(repo, directory)
            app.settings['setup_admin'] = True
            app.settings['household_directory'] = str(directory.resolve())
        app.enroll(repo, quiet=True)
    if not app.settings.get('label'):
        label = ask('Label for this account', f'{platform.node()}-{os.getuid()}')
        if not label or len(label) > 100 or any(ord(c) < 32 for c in label):
            raise Error('Use a short, single-line account label.')
        app.settings['label'] = label
    app.save()
    value = request(app)
    if app.settings.get('setup_admin') and not app.settings.get('setup_approved'):
        approve(app, value)
        app.settings['setup_approved'] = True
        app.save()
    elif not app.settings.get('registered'):
        print('\nShare this PUBLIC enrollment request with your administrator (make approve):\n' + value + '\n')
    wait_access(app)
    native_setup(app)
    app.register()
    app.status()
    webbrowser.open(app.landing().as_uri())
    print('Setup complete. Your tools start and check for updates after graphical login.')
