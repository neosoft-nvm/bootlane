#!/usr/bin/env python3
"""Bootlane desktop interface. Requires the distribution's Python Tk package."""
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    sys.exit('Bootlane needs Python Tk. Install python3-tk (Ubuntu/Debian), python3-tkinter (Fedora/openSUSE), or tk (Arch), then launch again.')

BASE = Path(__file__).resolve().parent
CLI = BASE / 'bootlane.py'
BG, CARD, INK, MUTED, ACCENT = '#101923', '#192633', '#eef5f4', '#9bafbd', '#69e0b7'


def cli_command(args, elevated=False):
    command = [sys.executable, str(CLI), *args]
    if elevated:
        if not shutil.which('pkexec'):
            raise RuntimeError('Administrator access needs pkexec. Install your distribution’s PolicyKit package and run a desktop authentication agent.')
        command.insert(0, shutil.which('pkexec'))
    return command


class Bootlane:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.read_elevated = False
        self.ids = {}
        self.firmware_ids = {}
        self.order = []
        self.last_preview = None
        self.confirmation_open = False
        root.title('Bootlane • Your next start')
        root.geometry('1000x790')
        root.minsize(850, 700)
        root.configure(bg=BG)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background=CARD, foreground=INK, font=('Sans', 11))
        style.configure('TCombobox', fieldbackground=BG, background=CARD, foreground=INK, arrowcolor=ACCENT, padding=8)
        style.map('TCombobox', fieldbackground=[('readonly', BG)], foreground=[('readonly', INK)])
        style.configure('Treeview', background=BG, fieldbackground=BG, foreground=INK, rowheight=36, borderwidth=0)
        style.configure('Treeview.Heading', background=CARD, foreground=MUTED, padding=10)
        style.map('Treeview', background=[('selected', '#285449')], foreground=[('selected', INK)])
        root.option_add('*TCombobox*Listbox.background', CARD)
        root.option_add('*TCombobox*Listbox.foreground', INK)
        header = tk.Frame(root, bg=BG)
        header.pack(fill='x', padx=32, pady=(25, 18))
        logo = tk.Canvas(header, width=50, height=50, bg=BG, highlightthickness=0)
        logo.pack(side='left', padx=(0, 15))
        logo.create_line(8, 43, 23, 7, fill=ACCENT, width=5, capstyle='round')
        logo.create_line(29, 43, 44, 7, fill=ACCENT, width=5, capstyle='round')
        logo.create_line(25, 32, 29, 22, fill=INK, width=3)
        title = tk.Frame(header, bg=BG)
        title.pack(side='left')
        self.label(title, 'bootlane', 27, INK, BG, bold=True).pack(anchor='w')
        self.label(title, 'A better beginning.', 11, MUTED, BG).pack(anchor='w')
        self.label(header, 'LINUX  /  BOOT PREFERENCES', 10, MUTED, BG).pack(side='right')
        nav = tk.Frame(root, bg=BG)
        nav.pack(fill='x', padx=32)
        self.mode = tk.StringVar(value='menu')
        for name, value in [('01  Boot menu', 'menu'), ('02  Firmware priority', 'firmware')]:
            tk.Radiobutton(nav, text=name, variable=self.mode, value=value, command=self.switch, bg=BG, fg=INK, selectcolor=CARD, activebackground=BG, activeforeground=ACCENT, indicatoron=False, relief='flat', padx=18, pady=10).pack(side='left', padx=(0, 8))
        self.body = tk.Frame(root, bg=CARD)
        self.body.pack(fill='both', expand=True, padx=32, pady=16)
        self.menu = tk.Frame(self.body, bg=CARD)
        self.firmware = tk.Frame(self.body, bg=CARD)
        self.build_menu()
        self.build_firmware()
        self.menu.pack(fill='both', expand=True)
        footer = tk.Frame(root, bg=BG)
        footer.pack(fill='x', padx=32, pady=(0, 12))
        self.status = tk.StringVar(value='Ready. Apply changes opens a preview for your confirmation.')
        tk.Label(footer, textvariable=self.status, bg=BG, fg=MUTED, anchor='w', wraplength=900).pack(fill='x')
        actions = tk.Frame(root, bg=BG)
        actions.pack(fill='x', padx=32, pady=(0, 25))
        self.label(actions, 'Changes take effect on your next boot.', 10, MUTED, BG).pack(side='left')
        self.apply_button = self.button(actions, 'Apply changes  →', self.apply, primary=True)
        self.apply_button.pack(side='right')
        self.loader.trace_add('write', self.invalidate)
        self.timeout.trace_add('write', self.invalidate)
        self.change_timeout.trace_add('write', self.invalidate)
        self.root.after(100, self.poll)
        self.load_menu()

    def label(self, parent, text, size=11, color=INK, bg=CARD, bold=False):
        return tk.Label(parent, text=text, bg=bg, fg=color, font=('Sans', size, 'bold' if bold else 'normal'))

    def button(self, parent, text, action, primary=False):
        return tk.Button(parent, text=text, command=action, bg=ACCENT if primary else '#263a49', fg=BG if primary else INK, activebackground='#9cebd0' if primary else '#365363', activeforeground=BG if primary else INK, relief='flat', borderwidth=0, padx=18, pady=10, cursor='hand2', font=('Sans', 11, 'bold'))

    def build_menu(self):
        self.label(self.menu, 'Make your next start yours.', 21, bold=True).pack(anchor='w', padx=24, pady=(20, 5))
        self.label(self.menu, 'Choose an entry below to make it the default. Leave it unselected to keep the current choice.', 10, MUTED).pack(anchor='w', padx=24)
        controls = tk.Frame(self.menu, bg=CARD)
        controls.pack(fill='x', padx=24, pady=15)
        self.loader = tk.StringVar(value='auto')
        self.label(controls, 'BOOTLOADER', 10, MUTED).pack(side='left', padx=(0, 12))
        combo = ttk.Combobox(controls, textvariable=self.loader, values=['auto', 'grub', 'systemd-boot'], state='readonly', width=17)
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', lambda event: self.load_menu())
        self.button(controls, 'Read as administrator', lambda: self.load_menu(True)).pack(side='right')
        self.button(controls, 'Refresh', self.load_menu).pack(side='right', padx=8)
        self.entries = ttk.Treeview(self.menu, columns=('title', 'id'), show='headings', selectmode='browse', height=5)
        self.entries.heading('title', text='START AUTOMATICALLY WITH')
        self.entries.heading('id', text='ENTRY ID')
        self.entries.column('title', width=460)
        self.entries.column('id', width=250)
        self.entries.pack(fill='both', expand=True, padx=24)
        self.entries.bind('<<TreeviewSelect>>', self.invalidate)
        row = tk.Frame(self.menu, bg=CARD)
        row.pack(fill='x', padx=24, pady=18)
        self.change_timeout = tk.BooleanVar(value=False)
        tk.Checkbutton(row, text='Set menu waiting time', variable=self.change_timeout, bg=CARD, fg=INK, selectcolor=BG, activebackground=CARD, activeforeground=INK).pack(side='left')
        self.timeout = tk.StringVar(value='')
        tk.Spinbox(row, from_=-1, to=86400, textvariable=self.timeout, width=7, bg=BG, fg=ACCENT, buttonbackground=CARD, insertbackground=INK, relief='flat', font=('Sans', 18)).pack(side='left', padx=14)
        self.label(row, 'seconds   ·   0 = immediate   ·   −1 = wait for me', 10, MUTED).pack(side='left')
        self.label(self.menu, 'GRUB files are backed up before saving. Administrator authentication happens when needed.', 10, MUTED).pack(anchor='w', padx=24, pady=(0, 18))

    def build_firmware(self):
        self.label(self.firmware, 'First in line. First to boot.', 21, bold=True).pack(anchor='w', padx=24, pady=(20, 5))
        self.label(self.firmware, 'Move a firmware entry up or down to choose which bootloader your computer tries first.', 10, MUTED).pack(anchor='w', padx=24)
        controls = tk.Frame(self.firmware, bg=CARD)
        controls.pack(fill='x', padx=24, pady=14)
        self.button(controls, 'Read firmware entries', self.load_firmware).pack(side='left')
        self.button(controls, 'Read as administrator', lambda: self.load_firmware(True)).pack(side='left', padx=8)
        self.priority = tk.Listbox(self.firmware, bg=BG, fg=INK, selectbackground='#285449', selectforeground=INK, highlightthickness=0, relief='flat', font=('Sans', 13), activestyle='none')
        self.priority.pack(fill='both', expand=True, padx=24)
        move = tk.Frame(self.firmware, bg=CARD)
        move.pack(fill='x', padx=24, pady=16)
        self.button(move, '↑  Move up', lambda: self.move(-1)).pack(side='left')
        self.button(move, '↓  Move down', lambda: self.move(1)).pack(side='left', padx=8)
        self.label(self.firmware, 'UEFI only. This changes firmware priority, not the order of entries inside a boot menu.', 10, MUTED).pack(anchor='w', padx=24, pady=(0, 18))

    def switch(self):
        self.menu.pack_forget()
        self.firmware.pack_forget()
        (self.menu if self.mode.get() == 'menu' else self.firmware).pack(fill='both', expand=True)
        self.invalidate()

    def update_apply_button(self):
        self.apply_button.configure(state='disabled' if self.busy or self.confirmation_open else 'normal')

    def invalidate(self, *unused):
        self.last_preview = None
        self.update_apply_button()

    def task(self, args, callback, elevated=False):
        if self.busy:
            return
        try:
            command = cli_command(args, elevated)
        except RuntimeError as exc:
            messagebox.showerror('Administrator access unavailable', str(exc))
            return
        self.busy = True
        self.apply_button.configure(state='disabled')
        self.status.set('Waiting for administrator authentication…' if elevated else 'Reading boot settings…')
        def worker():
            try:
                proc = subprocess.run(command, text=True, capture_output=True)
                self.events.put((callback, proc.returncode, proc.stdout, proc.stderr, args, elevated))
            except Exception as exc:
                self.events.put((callback, 1, '', str(exc), args, elevated))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            callback, code, out, err, args, elevated = self.events.get_nowait()
            self.busy = False
            if code == 3 and not elevated:
                self.invalidate()
                self.status.set('Administrator access is needed to read protected boot settings.')
                if messagebox.askyesno('Read protected boot settings?',
                        'Your system restricts access to the boot configuration. '
                        'Read it using the administrator password dialog? '
                        'This does not change your boot settings.'):
                    self.task(args, callback, elevated=True)
            elif code:
                self.invalidate()
                self.status.set('Operation stopped. Earlier successful settings, if any, remain saved. Review the details.')
                messagebox.showerror('Bootlane needs your attention', '\n\n'.join(part.strip() for part in (err, out) if part.strip()) or 'Authentication cancelled or command failed.')
            else:
                if elevated and '--apply' not in args:
                    self.read_elevated = True
                callback(out)
            self.update_apply_button()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def load_menu(self, elevated=False):
        if self.busy:
            return
        self.invalidate()
        self.timeout.set('')
        self.change_timeout.set(False)
        def loaded(out):
            data = json.loads(out)
            self.read_elevated = elevated or self.read_elevated
            self.entries.delete(*self.entries.get_children())
            self.ids.clear()
            for entry in data['entries']:
                item = self.entries.insert('', 'end', values=(entry['title'], entry['id']))
                self.ids[item] = entry['id']
            seconds = data.get('timeout')
            if seconds is not None:
                self.timeout.set(str(seconds))
                self.change_timeout.set(True)
                waiting = 'wait indefinitely' if seconds == -1 else f'{seconds} seconds'
                self.status.set(f"Bootloader: {data['loader']} · Configured waiting time: {waiting}.")
            else:
                self.status.set(f"Bootloader: {data['loader']} · Current waiting time could not be read. Enable Set menu waiting time and enter a value to change it.")
        self.task(['--loader', self.loader.get(), '--inspect'], loaded, elevated)

    def load_firmware(self, elevated=False):
        if self.busy:
            return
        self.invalidate()
        def loaded(out):
            import re
            order = re.search(r'^BootOrder:\s*([0-9A-Fa-f,]+)', out, re.M)
            self.firmware_ids = {m[0].upper(): m[1] for m in re.findall(r'^Boot([0-9A-Fa-f]{4})\*?\s+(.+)$', out, re.M)}
            self.order = order[1].upper().split(',') if order else []
            self.render_order()
            self.status.set('Firmware priority loaded. Select an entry and move it to its new position.')
        self.task(['--firmware-list'], loaded, elevated)

    def render_order(self):
        self.priority.delete(0, 'end')
        for i, ident in enumerate(self.order):
            self.priority.insert('end', f'  {i+1:02}    {self.firmware_ids.get(ident, ident)}    [{ident}]')

    def move(self, direction):
        selected = self.priority.curselection()
        if not selected or self.busy:
            return
        i, j = selected[0], selected[0] + direction
        if 0 <= j < len(self.order):
            self.order[i], self.order[j] = self.order[j], self.order[i]
            self.render_order()
            self.priority.selection_set(j)
            self.invalidate()

    def arguments(self):
        if self.mode.get() == 'firmware':
            if not self.order:
                raise ValueError('Read the firmware entries first.')
            return [['--boot-order', ','.join(self.order)]]
        args = ['--loader', self.loader.get()]
        changes = []
        if self.change_timeout.get():
            timeout = int(self.timeout.get())
            if not -1 <= timeout <= 86400:
                raise ValueError('Use -1 to wait indefinitely, or 0–86400 seconds.')
            changes.append(args + ['--timeout', str(timeout)])
        selected = self.entries.selection()
        if selected:
            changes.append(args + ['--default', self.ids[selected[0]]])
        if not changes:
            raise ValueError('Select an entry or enable the waiting time setting.')
        return changes

    def preview(self):
        if self.busy:
            return
        self.invalidate()
        try:
            changes = self.arguments()
        except (ValueError, KeyError) as exc:
            messagebox.showerror('Check your selection', str(exc))
            return
        self.preview_next(changes, 0, [])

    def preview_next(self, changes, index, outputs):
        if index == len(changes):
            # Form edits while a command ran invalidate the preview.
            try:
                current = self.arguments()
            except (ValueError, KeyError):
                current = None
            if current != changes:
                self.status.set('Selection changed. Click Apply changes again to review it.')
                return
            self.last_preview = changes
            self.status.set('Review the preview and confirm to save. Nothing has been saved yet.')
            self.details('Review your changes', '\n\n'.join(outputs), confirm=True)
            return
        self.task(changes[index], lambda out: self.preview_next(changes, index + 1, outputs + [out]), elevated=self.read_elevated)

    def apply(self):
        if not self.confirmation_open:
            self.preview()

    def cancel_confirmation(self):
        self.invalidate()
        self.status.set('Cancelled. No changes were saved.')

    def confirm_apply(self):
        if self.busy or not self.last_preview:
            return
        try:
            if self.arguments() != self.last_preview:
                self.invalidate()
                self.status.set('Selection changed. Click Apply changes again to review it.')
                return
        except (ValueError, KeyError):
            self.invalidate()
            self.status.set('Selection changed. Click Apply changes again to review it.')
            return
        changes = self.last_preview
        self.last_preview = None
        self.apply_next(changes, 0, [])

    def apply_next(self, changes, index, outputs):
        if index == len(changes):
            self.status.set('Saved. Your preferences take effect on the next boot.')
            self.details('Preferences saved', '\n\n'.join(outputs))
            return
        # Each step is independent; a later failure leaves earlier successful settings applied.
        self.status.set(f'Applying setting {index+1} of {len(changes)}…')
        self.task(changes[index] + ['--apply'], lambda out: self.apply_next(changes, index + 1, outputs + [out]), elevated=True)

    def details(self, title, text, confirm=False):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry('760x480' if confirm else '760x420')
        dialog.minsize(600, 360)
        dialog.transient(self.root)
        dialog.configure(bg=CARD)
        self.label(dialog, title, 18, bold=True).pack(anchor='w', padx=20, pady=15)
        if confirm:
            self.label(dialog, 'Nothing has been saved yet. Confirm to apply the changes below.', 11, MUTED).pack(anchor='w', padx=20, pady=(0, 12))
        box = tk.Text(dialog, bg=BG, fg=INK, wrap='word', relief='flat', padx=15, pady=15, font=('Monospace', 10))
        box.pack(fill='both', expand=True, padx=20)
        box.insert('1.0', text)
        box.configure(state='disabled')
        if confirm:
            self.confirmation_open = True
            self.update_apply_button()
            def close(accepted=False):
                dialog.grab_release()
                dialog.destroy()
                self.confirmation_open = False
                if accepted:
                    self.confirm_apply()
                else:
                    self.cancel_confirmation()
                self.update_apply_button()
            actions = tk.Frame(dialog, bg=CARD)
            actions.pack(fill='x', padx=20, pady=15)
            self.button(actions, 'Confirm and apply  →', lambda: close(True), primary=True).pack(side='right')
            cancel = self.button(actions, 'Cancel', close)
            cancel.pack(side='right', padx=10)
            dialog.protocol('WM_DELETE_WINDOW', close)
            dialog.bind('<Escape>', lambda event: close())
            dialog.grab_set()
            cancel.focus_set()
        else:
            self.button(dialog, 'Done', dialog.destroy, primary=True).pack(anchor='e', padx=20, pady=15)



if __name__ == '__main__':
    root = tk.Tk()
    Bootlane(root)
    root.mainloop()
