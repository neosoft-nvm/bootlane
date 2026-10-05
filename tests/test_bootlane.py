import contextlib
import io
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('bootlane', Path(__file__).parents[1] / 'bootlane.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class Tests(unittest.TestCase):
    def test_hidden_menu_preview_is_read_only(self):
        output = io.StringIO()
        with patch.object(b, 'detect', return_value='grub'), patch.object(b, 'hidden_menu_environment', return_value=('tool', Path('/fixture/grubenv'))), patch.object(b, 'apply_grub') as apply, contextlib.redirect_stdout(output):
            b.main(['--timeout', '20'])
        self.assertIn('disable automatic menu hiding', output.getvalue())
        self.assertIn('No changes made', output.getvalue())
        apply.assert_not_called()

    def exercise_environment_transaction(self, fail_after_unset=False):
        envtool = b.shutil.which('grub2-editenv') or b.shutil.which('grub-editenv')
        checker = b.shutil.which('grub2-script-check') or b.shutil.which('grub-script-check')
        if not envtool or not checker:
            self.skipTest('GRUB tools needed for integration test')
        with tempfile.TemporaryDirectory() as d:
            source, cfg, env = [Path(d) / name for name in ('defaults', 'grub.cfg', 'grubenv')]
            source.write_text('GRUB_TIMEOUT=5\n')
            cfg.write_text("menuentry 'Original' --id old {\n true\n}\n")
            b.run(envtool, str(env), 'create')
            b.run(envtool, str(env), 'set', 'menu_auto_hide=1', 'boot_success=1', 'saved_entry=linux')
            original = {p: p.read_bytes() for p in (source, cfg, env)}
            real_path, real_run = b.Path, b.run
            def paths(value):
                return source if value == '/etc/default/grub' else real_path(value)
            def programs(*names):
                return 'fixture-mkconfig' if 'grub-mkconfig' in names else checker
            def commands(*args):
                if args[0] == 'fixture-mkconfig':
                    Path(args[2]).write_text("menuentry 'New' --id linux {\n true\n}\n")
                    return ''
                result = real_run(*args)
                if fail_after_unset and args[0] == envtool and 'unset' in args:
                    raise b.Error('fixture failure after environment mutation')
                return result
            with patch.object(b, 'Path', side_effect=paths), patch.object(b, 'grub_config', return_value=cfg), patch.object(b, 'program', side_effect=programs), patch.object(b, 'run', side_effect=commands):
                if fail_after_unset:
                    with self.assertRaisesRegex(b.Error, 'fixture failure'):
                        b.apply_grub({'GRUB_TIMEOUT': 20, 'GRUB_TIMEOUT_STYLE': 'menu'})
                else:
                    b.apply_grub({'GRUB_TIMEOUT': 20, 'GRUB_TIMEOUT_STYLE': 'menu'})
            if fail_after_unset:
                for path, data in original.items():
                    self.assertEqual(path.read_bytes(), data)
            else:
                variables = real_run(envtool, str(env), 'list')
                self.assertNotIn('menu_auto_hide=', variables)
                self.assertIn('boot_success=1', variables)
                self.assertIn('saved_entry=linux', variables)
                self.assertIn('GRUB_TIMEOUT=20', source.read_text())
            backups = list(Path(d).glob('grubenv.bootlane-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original[env])

    def test_real_grub_environment_unset_and_backup(self):
        self.exercise_environment_transaction()

    def test_real_grub_environment_rollback_is_byte_exact(self):
        self.exercise_environment_transaction(fail_after_unset=True)

    def test_atomic_follows_symlink_and_preserves_binary_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            target, alias = Path(d) / 'target', Path(d) / 'alias'
            target.write_bytes(b'old')
            alias.symlink_to(target)
            b.atomic(alias, b'new\x00\xff')
            self.assertTrue(alias.is_symlink())
            self.assertEqual(target.read_bytes(), b'new\x00\xff')

    def test_protected_grub_path_reports_permissions(self):
        missing, protected = Mock(), Mock()
        missing.stat.side_effect = FileNotFoundError()
        protected.stat.side_effect = PermissionError('restricted directory')
        with patch.object(b, 'Path', side_effect=[missing, protected]):
            with self.assertRaises(b.PermissionRequired):
                b.grub_config()

    def test_missing_configuration_has_specific_error(self):
        missing = Mock()
        missing.stat.side_effect = FileNotFoundError()
        with patch.object(b, 'Path', return_value=missing):
            with self.assertRaisesRegex(b.Error, 'No GRUB configuration found'):
                b.grub_config()

    def test_symlink_alias_is_not_ambiguous(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'grub.cfg'
            config.write_text('menu')
            alias = Path(d) / 'alias.cfg'
            alias.symlink_to(config)
            with patch.object(b, 'Path', side_effect=[config, alias]):
                self.assertEqual(b.grub_config(), config)

    def test_distinct_configs_remain_ambiguous(self):
        with tempfile.TemporaryDirectory() as d:
            configs = [Path(d) / name for name in ('one', 'two')]
            for path in configs:
                path.write_text('menu')
            with patch.object(b, 'Path', side_effect=configs):
                with self.assertRaisesRegex(b.Error, 'Two different'):
                    b.grub_config()

    def test_atomic_preserves_extended_attributes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config'
            path.write_text('old')
            b.os.setxattr(path, 'user.bootlane-test', b'metadata')
            b.atomic(path, 'new')
            self.assertEqual(b.os.getxattr(path, 'user.bootlane-test'), b'metadata')

    def test_nested_ids(self):
        text = """menuentry 'Linux' --id 'linux' {
}
submenu 'Advanced' $menuentry_id_option 'advanced' {
  menuentry 'Old kernel' --id 'old' {
  }
}
menuentry 'Windows' --id 'windows' {
}
"""
        self.assertEqual([e['id'] for e in b.grub_entries(text)], ['linux', 'advanced>old', 'windows'])

    def test_edit_is_literal_and_preserves_unrelated_settings(self):
        text = 'GRUB_TIMEOUT=3\nexport GRUB_TIMEOUT=4\nGRUB_CMDLINE_LINUX="quiet"\n'
        result = b.update_grub(text, {'GRUB_TIMEOUT': 5, 'GRUB_DEFAULT': "danger$(touch /tmp/bad)'"})
        self.assertEqual(result.count('GRUB_TIMEOUT='), 1)
        self.assertIn('GRUB_CMDLINE_LINUX="quiet"', result)
        self.assertIn("GRUB_TIMEOUT=5", result)
        self.assertIn("'danger$(touch /tmp/bad)", result)

    def test_order_preserves_omitted_entries(self):
        self.assertEqual(b.order_value('0002', ['0001', '0002', '0003'], ['0001', '0002', '0003']), ['0002', '0001', '0003'])
        for value in ['0002,0002', 'FFFF', '2', '0001;reboot']:
            with self.assertRaises(b.Error):
                b.order_value(value, ['0001', '0002'], ['0001', '0002'])

    def test_preview_never_calls_apply(self):
        with patch.object(b, 'detect', return_value='grub'), patch.object(b, 'apply_grub') as apply, patch.object(b.shutil, 'which', return_value=None):
            b.main(['--timeout', '5'])
            apply.assert_not_called()

    def test_atomic_preserves_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config'
            p.write_text('old')
            p.chmod(0o640)
            b.atomic(p, 'new')
            self.assertEqual(p.read_text(), 'new')
            self.assertEqual(p.stat().st_mode & 0o777, 0o640)

    def test_generation_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            source, cfg = Path(d) / 'defaults', Path(d) / 'grub.cfg'
            source.write_text('GRUB_TIMEOUT=3\n')
            cfg.write_text('old menu')
            real_path = b.Path
            def paths(value):
                return source if value == '/etc/default/grub' else real_path(value)
            with patch.object(b, 'Path', side_effect=paths), patch.object(b, 'grub_config', return_value=cfg), patch.object(b, 'program', return_value='tool'), patch.object(b, 'run', side_effect=b.Error('generation failed')):
                with self.assertRaises(b.Error):
                    b.apply_grub({'GRUB_TIMEOUT': 7})
            self.assertEqual(source.read_text(), 'GRUB_TIMEOUT=3\n')
            self.assertEqual(cfg.read_text(), 'old menu')

if __name__ == '__main__':
    unittest.main()
