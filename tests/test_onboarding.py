import base64
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import boflow as b
import onboarding as o

KEY = 'ssh-ed25519 ' + base64.b64encode(struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(range(32))).decode()


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = b.App(Path(self.temp.name) / 'state')
        self.app.settings.update(repo='owner/home', label='test-account')
        (self.app.state / 'deploy-key.pub').write_text(KEY + ' optional comment')

    def test_request_contains_only_public_enrollment_information(self):
        data, fingerprint = o.decode_request(o.request(self.app))
        self.assertEqual(set(data), {'schema', 'repo', 'label', 'key'})
        self.assertEqual(data['key'], KEY)
        self.assertTrue(fingerprint.startswith('SHA256:'))

    def test_url_normalization_and_invalid_repository(self):
        self.assertEqual(o.repository('https://github.com/owner/home.git'), 'owner/home')
        for value in ('https://evil.test/owner/home', 'owner/home/keys', 'owner/home?token=x'):
            with self.assertRaises(b.Error): o.repository(value)

    def test_malformed_requests_rejected(self):
        for value in ('secret', 'boflow1:!!', 'boflow1:' + base64.b64encode(b'[]').decode()):
            with self.assertRaises(b.Error): o.decode_request(value)
        with self.assertRaises(b.Error): o.key_data('ssh-ed25519 YQ==')

    def test_approval_rejects_cross_household_before_auth(self):
        request = o.request(self.app)
        self.app.settings['repo'] = 'owner/other'
        with patch.object(o, 'ensure_gh') as auth:
            with self.assertRaises(b.Error): o.approve(self.app, request)
            auth.assert_not_called()

    def test_approval_is_read_only_and_private(self):
        with patch.object(o, 'consent'), patch.object(o, 'ensure_gh'), \
                patch.object(o, 'output', return_value=json.dumps({'private': True})), \
                patch.object(o, 'deploy_keys', return_value=[]) as deploy_keys, \
                patch.object(o, 'run') as run:
            o.approve(self.app, o.request(self.app))
            deploy_keys.assert_called_once_with('owner/home')
            args, kwargs = run.call_args
            self.assertIn('--input', args[0])
            self.assertIs(json.loads(kwargs['input'])['read_only'], True)
        with patch.object(o, 'consent'), patch.object(o, 'ensure_gh'), \
                patch.object(o, 'output', return_value=json.dumps({'private': False})), \
                patch.object(o, 'run') as run:
            with self.assertRaises(b.Error): o.approve(self.app, o.request(self.app))
            run.assert_not_called()

    def test_repeat_approval_does_not_duplicate_and_refuses_write_access(self):
        for read_only in (True, False):
            keys = '\n'.join(json.dumps(key) for key in (
                {'key': 'ssh-rsa unrelated', 'read_only': True},
                {'key': KEY, 'read_only': read_only},
            ))
            with patch.object(o, 'consent'), patch.object(o, 'ensure_gh'), \
                    patch.object(o, 'output', return_value='{"private":true}'), \
                    patch.object(o, 'deploy_keys', return_value=[json.loads(line) for line in keys.splitlines()]), \
                    patch.object(o, 'run') as run:
                if read_only: o.approve(self.app, o.request(self.app))
                else:
                    with self.assertRaises(b.Error): o.approve(self.app, o.request(self.app))
                run.assert_not_called()

    def test_deploy_key_listing_falls_back_when_jq_flag_is_unsupported(self):
        failure = __import__('subprocess').CompletedProcess(
            [], 2, '', 'unknown flag: --jq')
        pages = json.dumps([{'key': 'first'}]) + '\n' + json.dumps([{'key': 'second'}])
        with patch.object(o.subprocess, 'run', return_value=failure) as run, \
                patch.object(o, 'output', return_value=pages) as output:
            self.assertEqual(o.deploy_keys('owner/home'), [{'key': 'first'}, {'key': 'second'}])
            self.assertEqual(run.call_args.args[0][3:], ['--paginate', '--jq', '.[]'])
            self.assertEqual(output.call_args.args[0],
                             ['gh', 'api', 'repos/owner/home/keys', '--paginate'])

    def test_deploy_key_listing_does_not_hide_api_errors_as_compatibility(self):
        failure = __import__('subprocess').CompletedProcess(
            [], 1, '', 'HTTP 401: Bad credentials')
        with patch.object(o.subprocess, 'run', return_value=failure), \
                patch.object(o, 'output') as output:
            with self.assertRaisesRegex(b.Error, 'Command failed: gh'):
                o.deploy_keys('owner/home')
            output.assert_not_called()

    def test_existing_member_resumes_without_enrollment_questions(self):
        self.app.settings['registered'] = True
        self.app.save()
        with patch.object(o.platform, 'system', return_value='Darwin'), \
                patch.object(o.os, 'getuid', return_value=501), patch.object(o, 'run'), \
                patch.object(o, 'ask', side_effect=AssertionError('unexpected question')), \
                patch.object(o, 'wait_access'), patch.object(o, 'native_setup'), \
                patch.object(self.app, 'register') as register, patch.object(self.app, 'status'), \
                patch.object(self.app, 'landing', return_value=self.app.state / 'index.html'), \
                patch.object(o.webbrowser, 'open'):
            o.setup(self.app)
            register.assert_called_once()

    def test_occupied_preferred_port_uses_free_block(self):
        import socket
        with socket.socket() as listener, patch.object(b.os, 'getuid', return_value=501):
            try: listener.bind(('127.0.0.1', 11880))
            except OSError: self.skipTest('preferred port already occupied by host')
            ports = b.App.allocate_ports()
            self.assertNotIn(11880, ports.values())
            self.assertEqual(len(set(ports.values())), 3)

    def test_join_saves_identity_before_wait_and_never_authenticates_member(self):
        self.app.settings = {}
        def enroll(repo, quiet=False):
            self.app.settings['repo'] = repo
            self.app.save()
        with patch.object(o.platform, 'system', return_value='Darwin'), \
                patch.object(o.os, 'getuid', return_value=501), patch.object(o, 'run'), \
                patch.object(o, 'ask', side_effect=['join', 'https://github.com/owner/home', 'member']), \
                patch.object(self.app, 'enroll', side_effect=enroll), \
                patch.object(o, 'wait_access', side_effect=b.Error('approval pending')), \
                patch.object(o, 'ensure_gh') as auth, patch.object(self.app, 'register') as register:
            with self.assertRaises(b.Error): o.setup(self.app)
            auth.assert_not_called()
            register.assert_not_called()
        saved = json.loads(self.app.settings_path.read_text())
        self.assertEqual(saved['repo'], 'owner/home')
        self.assertEqual(saved['label'], 'member')

    def test_homebrew_nonowner_requires_handoff_only_for_missing_packages(self):
        cfg = {'native': {'macos': ['cmake', 'pkg-config']}}
        with patch.object(o.platform, 'system', return_value='Darwin'), \
                patch.object(o.os, 'getuid', return_value=501), patch.object(o, 'config', return_value=cfg), \
                patch.object(o, 'run'), patch.object(o, 'brew') as brew, \
                patch.object(o, 'output', return_value='cmake\npkg-config'), \
                patch.object(self.app, 'native') as native:
            brew.return_value.stat.return_value.st_uid = 502
            o.native_setup(self.app)
            native.assert_not_called()
        with patch.object(o.platform, 'system', return_value='Darwin'), \
                patch.object(o.os, 'getuid', return_value=501), patch.object(o, 'config', return_value=cfg), \
                patch.object(o, 'run'), patch.object(o, 'brew') as brew, \
                patch.object(o, 'output', return_value='pkg-config'), \
                patch.object(self.app, 'native') as native:
            brew.return_value.stat.return_value.st_uid = 502
            with self.assertRaisesRegex(b.Error, 'brew install cmake'): o.native_setup(self.app)
            native.assert_not_called()

    def test_access_timeout_retains_enrollment_and_does_not_register(self):
        self.app.save()
        with patch.object(self.app, 'fetch', side_effect=b.Error('offline')), \
                patch.object(o.time, 'monotonic', side_effect=[0, 601]), patch.object(o.time, 'sleep') as sleep:
            with self.assertRaisesRegex(b.Error, 'rerun make setup'): o.wait_access(self.app)
            sleep.assert_not_called()
        self.assertEqual(json.loads(self.app.settings_path.read_text())['repo'], 'owner/home')

    def test_create_flow_orders_private_creation_before_key_approval_and_registration(self):
        self.app.settings = {}
        calls = []
        def enroll(repo, quiet=False):
            calls.append('enroll')
            self.app.settings['repo'] = repo
            self.app.save()
        def create(repo, directory): calls.append('create')
        with patch.object(o.platform, 'system', return_value='Darwin'), \
                patch.object(o.os, 'getuid', return_value=501), patch.object(o, 'run'), \
                patch.object(o, 'ask', side_effect=['create', 'owner/home', self.temp.name + '/author', 'admin']), \
                patch.object(o, 'ensure_gh'), patch.object(o, 'consent'), \
                patch.object(o.subprocess, 'run', return_value=__import__('subprocess').CompletedProcess([], 0)), \
                patch.object(o, 'init_home', side_effect=create), \
                patch.object(self.app, 'enroll', side_effect=enroll), \
                patch.object(o, 'approve', side_effect=lambda *args: calls.append('approve')), \
                patch.object(o, 'wait_access', side_effect=lambda *args: calls.append('fetch')), \
                patch.object(o, 'native_setup', side_effect=lambda *args: calls.append('native')), \
                patch.object(self.app, 'register', side_effect=lambda: calls.append('register')), \
                patch.object(self.app, 'status'), \
                patch.object(self.app, 'landing', return_value=self.app.state / 'index.html'), \
                patch.object(o.webbrowser, 'open'):
            o.setup(self.app)
        self.assertEqual(calls, ['create', 'enroll', 'approve', 'fetch', 'native', 'register'])
        self.assertTrue(self.app.settings['setup_approved'])
