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
        app.busy = False
        app.confirmation_open = False
        app.read_elevated = False
        app.last_preview = None
        app.apply_button = Mock()
        app.status = Mock()
        return app

    def test_apply_opens_preview_without_saving(self):
        app = self.app()
        app.preview = Mock()
        app.apply_next = Mock()
        app.apply()
        app.preview.assert_called_once_with()
        app.apply_next.assert_not_called()

    def test_preview_commands_do_not_apply(self):
        app = self.app()
        app.task = Mock()
        app.apply_next = Mock()
        app.apply()
        args, callback = app.task.call_args.args
        self.assertNotIn('--apply', args)
        app.apply_next.assert_not_called()

    def test_completed_preview_requests_confirmation(self):
        app = self.app()
        app.details = Mock()
        app.apply_next = Mock()
        changes = app.arguments()
        app.preview_next(changes, len(changes), ['Preview output'])
        app.details.assert_called_once_with('Review your changes', 'Preview output', confirm=True)
        self.assertEqual(app.last_preview, changes)
        app.apply_next.assert_not_called()

    def test_confirm_saves_only_the_reviewed_settings(self):
        app = self.app()
        changes = app.arguments()
        app.last_preview = changes
        app.apply_next = Mock()
        app.confirm_apply()
        app.apply_next.assert_called_once_with(changes, 0, [])
        self.assertIsNone(app.last_preview)
        # Repeated confirmation cannot save the same preview twice.
        app.confirm_apply()
        app.apply_next.assert_called_once()

    def test_cancel_discards_preview_without_saving(self):
        app = self.app()
        app.last_preview = app.arguments()
        app.apply_next = Mock()
        app.cancel_confirmation()
        self.assertIsNone(app.last_preview)
        app.confirm_apply()
        app.apply_next.assert_not_called()
        app.apply_button.configure.assert_called_with(state='normal')

    def test_dialog_confirmation_and_close_callbacks(self):
        for action in ('Confirm and apply  →', 'Cancel', 'window-close', 'escape'):
            with self.subTest(action=action):
                app = self.app()
                app.root = Mock()
                app.label = Mock()
                app.confirm_apply = Mock()
                app.cancel_confirmation = Mock()
                dialog = Mock()
                callbacks = {}
                def button(parent, text, command, primary=False):
                    callbacks[text] = command
                    return Mock()
                app.button = button
                with patch.object(gui.tk, 'Toplevel', return_value=dialog, create=True), patch.object(gui.tk, 'Text', create=True), patch.object(gui.tk, 'Frame', create=True):
                    app.details('Review', 'Settings', confirm=True)
                self.assertTrue(app.confirmation_open)
                dialog.grab_set.assert_called_once()
                if action == 'window-close':
                    dialog.protocol.call_args.args[1]()
                elif action == 'escape':
                    dialog.bind.call_args.args[1](Mock())
                else:
                    callbacks[action]()
                self.assertFalse(app.confirmation_open)
                dialog.destroy.assert_called_once()
                if action == 'Confirm and apply  →':
                    app.confirm_apply.assert_called_once()
                    app.cancel_confirmation.assert_not_called()
                else:
                    app.cancel_confirmation.assert_called_once()
                    app.confirm_apply.assert_not_called()

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
        app.confirm_apply()
        self.assertIsNone(app.last_preview)
        app.apply_next.assert_not_called()

if __name__ == '__main__':
    unittest.main()
