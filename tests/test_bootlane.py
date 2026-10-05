import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bootlane', Path(__file__).parents[1] / 'bootlane.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class Tests(unittest.TestCase):
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
