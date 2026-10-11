import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('boflow', Path(__file__).resolve().parents[1] / 'src/boflow.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
ROOT = Path(__file__).resolve().parents[1]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = b.App(self.root / 'state')
        shutil.copytree(ROOT / 'examples/household', self.app.state / 'household',
                        ignore=shutil.ignore_patterns('node_modules', '.venv', '__pycache__'))
        home = self.app.state / 'household/home.yml'
        home.write_text(home.read_text().replace('REPLACE_WITH_PRODUCT_COMMIT', 'a' * 40))
        self.app.settings.update(repo='owner/private', ports=dict(zip(b.ROLES, [21000, 21001, 21002])))
        self.app.save()
        self.node = self.root / 'node'
        (self.node / 'bin').mkdir(parents=True)
        self.calls = []

    def fake_run(self, args, **kwargs):
        self.calls.append([str(x) for x in args])
        cwd = Path(kwargs.get('cwd', self.root))
        if args[:2] == ['npm', 'ci']:
            (cwd / 'node_modules').mkdir(exist_ok=True)
        if args[:2] == ['npm', 'install']:
            manifest = json.loads((cwd / 'package.json').read_text())
            (cwd / 'package-lock.json').write_text(json.dumps({'lockfileVersion': 3,
                'packages': {'': {'dependencies': manifest['dependencies']}}}))
        if args[:2] == ['uv', 'sync']:
            (cwd / '.venv/bin').mkdir(parents=True)
        return subprocess.CompletedProcess(args, 0, '')

    def apply(self, sha='b' * 40):
        with patch.object(self.app, 'node', return_value=self.node), patch.object(b, 'run', side_effect=self.fake_run):
            self.app.apply(sha)


class ConfigurationTests(Fixture):
    def test_real_starter_locks_match_manifests(self):
        self.assertEqual(b.config(self.app.state / 'household')['schema'], 1)

    def test_unpinned_product_and_stale_lock_rejected(self):
        home = self.app.state / 'household/home.yml'
        home.write_text(home.read_text().replace('a' * 40, 'main'))
        with self.assertRaises(b.Error): b.config(self.app.state / 'household')
        home.write_text(home.read_text().replace('main', 'a' * 40))
        manifest = self.app.state / 'household/node-red/package.json'
        data = json.loads(manifest.read_text()); data['dependencies']['node-red'] = '1.2.3'
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(b.Error, 'lockfile'): b.config(self.app.state / 'household')

    def test_duplicate_node_ids_and_inline_credentials_rejected(self):
        flows = self.app.state / 'household/node-red/flows.json'
        for value in ([{'id': 'x'}, {'id': 'x'}], [{'id': 'x', 'credentials': {'token': 'secret'}}]):
            flows.write_text(json.dumps(value))
            with self.assertRaises(b.Error): b.config(self.app.state / 'household')

    def test_local_overrides_are_limited_and_do_not_mutate_household(self):
        local = self.app.state / 'local.yml'
        local.write_text('native:\n  ubuntu: [git]\n')
        cfg = b.config(self.app.state / 'household', local)
        self.assertEqual(cfg['native']['ubuntu'], ['git'])
        self.assertIn('build-essential', b.config(self.app.state / 'household')['native']['ubuntu'])
        local.write_text('product_ref: main\n')
        with self.assertRaises(b.Error): b.config(self.app.state / 'household', local)

    def test_repo_input_cannot_inject_commands(self):
        for value in ('', 'https://github.com/x/y', 'x/y;touch secret', 'x/y/z'):
            with self.assertRaises(b.Error): b.repo_name(value)


class UpdateTests(Fixture):
    def test_pinned_product_activation_state_survives_parent_registration_save(self):
        def child_activation(args, **kwargs):
            state = b.load_json(self.app.settings_path)
            state.update(node_path='/account/node', applied_commit='b' * 40,
                         applied_product='a' * 40, last_success=123)
            b.write(self.app.settings_path, json.dumps(state))
            return subprocess.CompletedProcess(args, 0)
        with patch.object(self.app, 'fetch', side_effect=['b' * 40, 'a' * 40]), patch.object(b, 'run', side_effect=child_activation):
            self.app.update()
        self.app.settings['registered'] = True
        self.app.save()
        saved = b.load_json(self.app.settings_path)
        self.assertEqual(saved['node_path'], '/account/node')
        self.assertEqual(saved['applied_commit'], 'b' * 40)

    def test_symlinked_state_path_is_canonical_and_idempotent(self):
        alias = self.root / 'state-alias'
        alias.symlink_to(self.app.state, target_is_directory=True)
        self.app = b.App(alias)
        self.assertEqual(self.app.state, alias.resolve())
        self.apply()
        self.calls.clear()
        self.apply()
        self.assertEqual(self.calls, [])

    def test_repeat_apply_preserves_data_and_never_reinstalls(self):
        self.apply()
        personal = self.app.state / 'personal'
        (personal / 'flows.json').write_text('[{"id":"mine"}]')
        (personal / 'flows_cred.json').write_text('encrypted')
        (self.app.state / 'notebooks/example.ipynb').write_text('notebook')
        key = (personal / 'credential-key').read_text()
        self.calls.clear()
        self.apply()
        self.assertEqual(self.calls, [])
        self.assertEqual((personal / 'flows.json').read_text(), '[{"id":"mine"}]')
        self.assertEqual((personal / 'flows_cred.json').read_text(), 'encrypted')
        self.assertEqual((personal / 'credential-key').read_text(), key)
        self.assertEqual((self.app.state / 'notebooks/example.ipynb').read_text(), 'notebook')

    def test_changed_flow_stops_only_managed(self):
        self.apply()
        self.app.settings['registered'] = True
        (self.app.state / 'household/node-red/flows.json').write_text('[{"id":"shared"}]')
        with patch.object(self.app, 'service') as service, patch.object(self.app, 'install_services'), patch.object(self.app, 'health'):
            self.apply()
        stops = [c.args[1] for c in service.call_args_list if c.args[0] == 'stop']
        self.assertEqual(stops, ['managed'])

    def test_initial_registration_does_not_stop_unloaded_services(self):
        with patch.object(self.app, 'service') as service:
            self.apply()
        service.assert_not_called()

    def test_unchanged_registered_account_has_no_stops(self):
        self.apply()
        self.app.settings['registered'] = True
        with patch.object(self.app, 'service') as service, patch.object(self.app, 'install_services'), patch.object(self.app, 'health'):
            self.apply()
        self.assertFalse(any(c.args[0] == 'stop' for c in service.call_args_list))

    def test_dependency_failure_happens_before_service_stop(self):
        self.app.settings.update(registered=True, applied_commit='old')
        with patch.object(self.app, 'node', return_value=self.node), patch.object(b, 'run', side_effect=b.Error('npm failed')), patch.object(self.app, 'service') as service:
            with self.assertRaises(b.Error): self.app.apply('new')
        service.assert_not_called()
        self.assertEqual(self.app.settings['applied_commit'], 'old')

    def test_health_failure_does_not_mark_commit_successful(self):
        self.apply('old')
        self.app.settings['registered'] = True
        with patch.object(self.app, 'service'), patch.object(self.app, 'install_services'), patch.object(self.app, 'health', side_effect=b.Error('unhealthy')):
            with self.assertRaises(b.Error): self.apply('new')
        self.assertEqual(self.app.settings['applied_commit'], 'old')

    def test_personal_palette_extras_survive_new_baseline(self):
        self.apply()
        personal_manifest = self.app.state / 'personal/package.json'
        desired = json.loads(personal_manifest.read_text())
        desired['dependencies']['my-extra-node'] = '1.2.3'
        personal_manifest.write_text(json.dumps(desired))
        self.apply()
        installed = json.loads(personal_manifest.read_text())
        self.assertEqual(installed['dependencies']['my-extra-node'], '1.2.3')
        self.assertIn('node-red', installed['dependencies'])

    def test_lock_rejects_concurrent_updater(self):
        with self.app.locked():
            with self.assertRaisesRegex(b.Error, 'already running'):
                with b.App(self.app.state).locked(): pass

    def test_offline_login_starts_services_before_fetch_failure(self):
        self.app.settings['registered'] = True
        events = []
        with patch.object(self.app, 'service', side_effect=lambda *a, **k: events.append(a)), patch.object(b, 'run'), patch.object(self.app, 'update', side_effect=b.Error('offline')):
            with self.assertRaises(b.Error): self.app.login()
        self.assertEqual(events, [('start', role) for role in b.ROLES])


class NativeAndAccessTests(Fixture):
    def test_namespaced_port_environment_and_cli_precedence(self):
        with patch.dict(b.os.environ, {'BOFLOW_PORT_BASE': '11880'}), patch.object(b, 'App', return_value=self.app), patch.object(self.app, 'register') as register:
            with patch.object(b.sys, 'argv', ['boflow', 'register-user']):
                b.main()
            register.assert_called_with(11880)
            with patch.object(b.sys, 'argv', ['boflow', 'register-user', '--port-base', '11980']):
                b.main()
            register.assert_called_with(11980)
            with patch.dict(b.os.environ, {'BOFLOW_PORT_BASE': 'invalid'}), patch.object(b.sys, 'argv', ['boflow', 'register-user']), patch.object(b.sys, 'stderr'):
                with self.assertRaises(SystemExit) as error:
                    b.main()
                self.assertEqual(error.exception.code, 2)

    def test_invalid_and_conflicting_ports_are_rejected_before_registration(self):
        self.app.settings.pop('ports')
        for base in (0, 1023, 65534):
            with self.assertRaises(b.Error):
                self.app.register(base)
        for ports in ({'managed': 11880}, dict(zip(b.ROLES, [11880, 11880, 11882])),
                      dict(zip(b.ROLES, [True, 11881, 11882]))):
            with self.assertRaises(b.Error):
                b.App.validate_ports(ports)
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            ports = dict(zip(b.ROLES, [sock.getsockname()[1], 11881, 11882]))
            with self.assertRaisesRegex(b.Error, 'occupied'):
                b.App.validate_ports(ports)

    def test_explicit_ports_are_preserved_and_cannot_change_on_rerun(self):
        self.app.settings.pop('ports')
        with patch.object(self.app, 'update'), patch.object(self.app, 'install_launcher'), patch.object(self.app, 'install_services'), patch.object(self.app, 'service'), patch.object(self.app, 'health'), patch.object(self.app, 'landing'), patch.object(b, 'write'):
            self.app.register(11880)
            self.app.register()
            self.assertEqual(self.app.settings['ports'], dict(zip(b.ROLES, [11880, 11881, 11882])))
            with self.assertRaisesRegex(b.Error, 'differ'):
                self.app.register(11980)

    def test_generated_node_red_settings_are_loopback_only_and_use_stable_secret(self):
        self.apply()
        with patch.object(b.os, 'execvpe') as execute:
            self.app.serve('personal')
        text = (self.app.state / 'personal/settings.js').read_text()
        self.assertIn('127.0.0.1', text)
        self.assertIn('credential-key', text)
        self.assertNotIn((self.app.state / 'personal/credential-key').read_text(), text)
        if shutil.which('node'):
            run = subprocess.run(['node', '-e', 'const s=require(process.argv[1]); if(s.uiHost!=="127.0.0.1"||!s.credentialSecret)process.exit(1)', str(self.app.state / 'personal/settings.js')])
            self.assertEqual(run.returncode, 0)
        execute.assert_called_once()

    def test_jupyter_token_is_private_and_not_in_process_arguments(self):
        self.apply()
        with patch.object(b.os, 'execvpe') as execute:
            self.app.serve('jupyter')
        token = (self.app.state / 'jupyter-token').read_text()
        self.assertNotIn(token, str(execute.call_args))
        home = self.root / 'home'
        home.mkdir()
        with patch.object(b.Path, 'home', return_value=home):
            page = self.app.landing()
        self.assertIn(token, page.read_text())
        self.assertEqual(page.stat().st_mode & 0o777, 0o600)
        self.assertEqual(page.parent, home / 'boflow')
        self.assertEqual(page.parent.stat().st_mode & 0o777, 0o700)

    def test_native_maintenance_is_only_explicit(self):
        with patch.object(self.app, 'fetch'), patch.object(b, 'run', side_effect=self.fake_run), patch.object(b.platform, 'system', return_value='Linux'):
            self.app.native()
        self.assertTrue(any('--ask-become-pass' in call for call in self.calls))
        self.calls.clear()
        self.apply()
        self.assertFalse(any('ansible-playbook' in call[0] or call[0] in ('brew', 'sudo', 'apt') for call in self.calls))

    def test_removal_preserves_state_and_data(self):
        self.apply()
        with patch.object(b.Path, 'home', return_value=self.root / 'home'), patch.object(self.app, 'service'), patch.object(b, 'run'):
            self.app.remove()
        self.assertFalse(self.app.settings['registered'])
        self.assertTrue((self.app.state / 'personal/flows.json').exists())
        self.assertTrue((self.app.state / 'personal/credential-key').exists())

    def test_default_ports_start_at_11880(self):
        self.assertEqual(b.App.allocate_ports(), dict(zip(b.ROLES, [11880, 11881, 11882])))


class GitCheckoutTests(Fixture):
    def test_actual_git_fetch_selects_commit_without_touching_authoring_checkout(self):
        repo = self.root / 'upstream'
        subprocess.run(['git', 'init', '-b', 'main', str(repo)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repo), 'config', 'user.email', 'test@example.test'], check=True)
        subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'Test'], check=True)
        (repo / 'file').write_text('first')
        subprocess.run(['git', '-C', str(repo), 'add', 'file'], check=True)
        subprocess.run(['git', '-C', str(repo), 'commit', '-m', 'initial'], check=True, capture_output=True)
        sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        (repo / 'file').write_text('unpublished work')
        checkout = self.root / 'deployment'
        self.assertEqual(self.app.fetch(str(repo), checkout, 'main'), sha)
        self.assertEqual((checkout / 'file').read_text(), 'first')
        self.assertEqual((repo / 'file').read_text(), 'unpublished work')
        with self.assertRaises(b.Error): self.app.fetch('https://different.invalid/repo', checkout, 'main')

    def test_public_household_repository_is_never_pushed(self):
        commands = []
        def fake_output(args, **kwargs):
            return 'a' * 40 if args[-1] == 'HEAD' else ''
        with patch.object(b, 'output', side_effect=fake_output), patch.object(b, 'run', side_effect=lambda args, **k: commands.append(args)), patch.object(b.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"visibility":"PUBLIC"}')):
            with self.assertRaisesRegex(b.Error, 'public'):
                b.init_home('owner/home', self.root / 'new-home')
        self.assertFalse(any('push' in args or 'create' in args for args in commands))
        self.assertEqual(set(p.relative_to(self.root / 'new-home').as_posix() for p in (self.root / 'new-home').rglob('*') if p.is_file()), set(b.STARTER_FILES))

    def test_dirty_existing_household_is_not_committed_or_pushed(self):
        directory = self.root / 'existing'
        (directory / '.git').mkdir(parents=True)
        commands = []
        def fake_output(args, **kwargs):
            return 'a' * 40 if args[-1] == 'HEAD' else ' M home.yml'
        with patch.object(b, 'output', side_effect=fake_output), patch.object(b, 'run', side_effect=lambda args, **k: commands.append(args)), patch.object(b.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(b.Error, 'changes'):
                b.init_home('owner/home', directory)
        self.assertFalse(any('commit' in args or 'push' in args for args in commands))


if __name__ == '__main__': unittest.main()
