import queue
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

# Load controller code without requiring a desktop display or Tk installation.
spec = importlib.util.spec_from_file_location('gui', Path(__file__).parents[1] / 'bootlane_gui.py')
gui = importlib.util.module_from_spec(spec)
tk_stub = types.ModuleType('tkinter')
tk_stub.ttk = types.ModuleType('ttk')
tk_stub.messagebox = Mock()
with patch.dict(sys.modules, {'tkinter': tk_stub}):
    spec.loader.exec_module(gui)

class GuiTests(unittest.TestCase):
    def app(self):
        app = gui.Bootlane.__new__(gui.Bootlane)
        app.mode = Mock()
        app.mode.get.return_value = 'menu'
        app.loader = Mock()
        app.loader.get.return_value = 'auto'
        app.change_timeout = Mock()
        app.change_timeout.get.return_value = True
        app.timeout = Mock()
        app.timeout.get.return_value = '5'
        app.entries = Mock()
        app.entries.selection.return_value = ('chosen',)
        app.ids = {'chosen': 'advanced>linux'}
        return app

    def test_permission_failure_offers_elevated_read(self):
        app = self.app()
        app.events = queue.Queue()
        callback = Mock()
        app.events.put((callback, 3, '', 'Protected config', ['--list'], False))
        app.busy = True
        app.apply_button = Mock()
        app.status = Mock()
        app.root = Mock()
        app.task = Mock()
        with patch.object(gui.messagebox, 'askyesno', return_value=True):
            app.poll()
        app.task.assert_called_once_with(['--list'], callback, elevated=True)
        callback.assert_not_called()

    def test_permission_prompt_can_be_declined(self):
        app = self.app()
        app.events = queue.Queue()
        app.events.put((Mock(), 3, '', 'Protected config', ['--list'], False))
        app.apply_button = Mock()
        app.status = Mock()
        app.root = Mock()
        app.task = Mock()
        with patch.object(gui.messagebox, 'askyesno', return_value=False):
            app.poll()
        app.task.assert_not_called()

    def test_elevated_read_enables_elevated_preview(self):
        app = self.app()
        app.events = queue.Queue()
        callback = Mock()
        app.events.put((callback, 0, 'entries', '', ['--list'], True))
        app.root = Mock()
        app.poll()
        self.assertTrue(app.read_elevated)
        callback.assert_called_once_with('entries')

    def test_settings_are_separate_and_keep_literal_entry_id(self):
        self.assertEqual(self.app().arguments(), [['--loader', 'auto', '--timeout', '5'], ['--loader', 'auto', '--default', 'advanced>linux']])

    def test_invalid_timeout_cannot_apply(self):
        for value in ('abc', '-2', '86401'):
            app = self.app()
            app.timeout.get.return_value = value
            with self.assertRaises(ValueError):
                app.arguments()

    def test_empty_firmware_list_cannot_apply(self):
        app = self.app()
        app.mode.get.return_value = 'firmware'
        app.order = []
        with self.assertRaises(ValueError):
            app.arguments()

    def test_authentication_uses_argument_array(self):
        with patch.object(gui.shutil, 'which', return_value='/usr/bin/pkexec'):
            command = gui.cli_command(['--default', 'a;reboot'], elevated=True)
        self.assertEqual(command[0], '/usr/bin/pkexec')
        self.assertEqual(command[-1], 'a;reboot')

    def test_changed_selection_cannot_apply_old_preview(self):
        app = self.app()
        app.busy = False
        app.last_preview = [['--loader', 'auto', '--timeout', '10']]
        app.apply_button = Mock()
        app.apply_next = Mock()
        app.apply()
        self.assertIsNone(app.last_preview)
        app.apply_next.assert_not_called()

if __name__ == '__main__':
    unittest.main()
