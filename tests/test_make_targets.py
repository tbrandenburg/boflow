"""Execute Make recipes in a disposable checkout with side-effect tripwires."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ApprovalTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copyfile(ROOT / 'Makefile', self.root / 'Makefile')
        # Running bootstrap/setup is a regression even if it subsequently fails.
        for script in ('bootstrap.sh', 'setup.sh'):
            (self.root / script).write_text(
                '#!/bin/sh\nprintf "setup-side-effect\\n" >> events\nexit 99\n')
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKELEVEL', 'GNUMAKEFLAGS')}
        self.env.update(HOME=str(self.root), BOFLOW_STATE=str(self.root / 'account'))

    def approve(self):
        return subprocess.run(['make', '--no-print-directory', 'approve'],
                              cwd=self.root, env=self.env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

    def test_prepared_approval_enters_flow_without_setup(self):
        python = self.root / '.venv/bin/python'
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> events\n'
                          '[ "$#" = 2 ] && [ "$1" = src/boflow.py ] && [ "$2" = approve ]\n')
        python.chmod(0o700)
        result = self.approve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'events').read_text(), 'src/boflow.py approve\n')
        self.assertFalse((self.root / 'account').exists())

    def test_missing_environment_explains_repair_without_setup(self):
        result = self.approve()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('uv sync --locked', result.stderr)
        self.assertIn('then retry make approve', result.stderr)
        self.assertFalse((self.root / '.venv').exists())
        self.assertFalse((self.root / 'events').exists())
        self.assertFalse((self.root / 'account').exists())
