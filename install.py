#!/usr/bin/env python3
"""Install Bootlane for the current user; no sudo needed."""
import os
from pathlib import Path
import shutil
import sys

source = Path(__file__).resolve().parent
if os.geteuid() == 0:
    sys.exit('Run this installer as your normal desktop user, without sudo.')
base = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
if not base.is_absolute():
    sys.exit('XDG_DATA_HOME must be an absolute path.')
target = base / 'bootlane'
apps = base / 'applications'
target.mkdir(parents=True, exist_ok=True)
apps.mkdir(parents=True, exist_ok=True)
for name in ['bootlane.py', 'bootlane_gui.py', 'bootlane.svg', 'README.md']:
    if (source / name).resolve() != (target / name).resolve():
        shutil.copy2(source / name, target / name)

def desktop_quote(value):
    value = str(value).replace('%', '%%')
    for char in ['\\', '"', '`', '$']:
        value = value.replace(char, '\\' + char)
    # Desktop files have an additional string escaping layer.
    return '"' + value.replace('\\', '\\\\') + '"'

(apps / 'bootlane.desktop').write_text(
    '[Desktop Entry]\nType=Application\nName=Bootlane\n'
    'Comment=Choose what boots and how long it waits\n'
    f'Exec={desktop_quote(sys.executable)} {desktop_quote(target / "bootlane_gui.py")}\n'
    f'Icon={target / "bootlane.svg"}\nTerminal=false\nCategories=System;Settings;\n'
)
print('Installed. Open Bootlane from your application menu.')
print('If it does not appear immediately, sign out and back in.')
print(f'To uninstall, remove {target} and {apps / "bootlane.desktop"}.')
