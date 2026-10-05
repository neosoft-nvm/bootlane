#!/usr/bin/env python3
"""Portable Linux boot preferences. Preview by default; no external Python packages."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

# Do not resolve programs through an untrusted sudo caller's PATH.
os.environ['PATH'] = '/usr/sbin:/usr/bin:/sbin:/bin'

class Error(Exception):
    pass

def run(*args):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise Error(f'{shlex.join(args)} failed: {p.stderr.strip() or p.stdout.strip()}')
    return p.stdout

def program(*names):
    for name in names:
        if shutil.which(name):
            return name
    raise Error('Missing distribution package providing ' + ' / '.join(names))

def atomic(path, text):
    path = Path(path)
    stat = path.stat()
    fd, tmp = tempfile.mkstemp(prefix='.bootlane-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, stat.st_mode & 0o777)
        os.chown(tmp, stat.st_uid, stat.st_gid)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def update_grub(text, values):
    lines = text.splitlines()
    for key, value in values.items():
        lines = [line for line in lines if not re.match(r'^\s*(?:export\s+)?' + key + r'\s*=', line)]
        lines.append(key + '=' + shlex.quote(str(value)))
    return '\n'.join(lines) + '\n'

def grub_entries(text):
    # Use stable IDs. Submenu parents are tracked by indentation used by grub-mkconfig.
    parents, entries = [], []
    for line in text.splitlines():
        m = re.match(r'^(\s*)(menuentry|submenu)\s+(.*)', line)
        if not m:
            continue
        indent = len(m[1].expandtabs(8))
        while parents and parents[-1][0] >= indent:
            parents.pop()
        try:
            tokens = shlex.split(m[3])
        except ValueError:
            continue
        ident = None
        for i, token in enumerate(tokens):
            if token in ('--id', '$menuentry_id_option') and i + 1 < len(tokens):
                ident = tokens[i + 1]
            elif token.startswith('--id='):
                ident = token[5:]
        if not ident or '$' in ident:
            continue
        path = '>'.join([p[1] for p in parents] + [ident])
        if m[2] == 'submenu':
            parents.append((indent, ident))
        else:
            entries.append({'id': path, 'title': tokens[0]})
    return entries

def grub_config():
    paths = [Path('/boot/grub/grub.cfg'), Path('/boot/grub2/grub.cfg')]
    found = [p for p in paths if p.is_file()]
    if len(found) != 1:
        raise Error('Cannot identify a unique GRUB configuration; mount /boot and remove ambiguity.')
    return found[0]

def detect():
    sd = shutil.which('bootctl') and subprocess.run(['bootctl', 'is-installed'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    grub = Path('/etc/default/grub').is_file()
    if sd and grub:
        raise Error('Both bootloaders are installed. Specify --loader grub or --loader systemd-boot after checking which one boots this machine.')
    if sd:
        return 'systemd-boot'
    if grub:
        return 'grub'
    raise Error('No supported bootloader detected.')

def entries(loader):
    if loader == 'systemd-boot':
        return [{'id': e['id'], 'title': e.get('title', e['id'])} for e in json.loads(run(program('bootctl'), '--json=short', 'list'))]
    result = grub_entries(grub_config().read_text())
    for p in sorted(Path('/boot/loader/entries').glob('*.conf')):
        title = next((l[6:].strip() for l in p.read_text().splitlines() if l.startswith('title ')), p.stem)
        result.append({'id': p.stem, 'title': title})
    # IDs with unresolved GRUB expressions are deliberately omitted.
    return list({e['id']: e for e in result}.values())

def firmware():
    text = run(program('efibootmgr'))
    m = re.search(r'^BootOrder:\s*([0-9A-Fa-f,]+)', text, re.M)
    if not m:
        raise Error('No UEFI BootOrder available; legacy BIOS order is not supported.')
    ids = re.findall(r'^Boot([0-9A-Fa-f]{4})\*?\s', text, re.M)
    return text, m[1].upper().split(','), [x.upper() for x in ids]

def order_value(value, current, available):
    requested = [x.strip().upper() for x in value.split(',')]
    if any(not re.fullmatch('[0-9A-F]{4}', x) or x not in available for x in requested):
        raise Error('Use existing four-digit UEFI entry IDs, separated by commas.')
    if len(set(requested)) != len(requested):
        raise Error('Duplicate boot order IDs.')
    return requested + [x for x in current if x not in requested]

def apply_grub(values):
    source, cfg = Path('/etc/default/grub'), grub_config()
    # Later sourced distribution fragments may override our settings.
    for p in Path('/etc/default/grub.d').glob('*.cfg'):
        if any(re.search(r'^\s*(?:export\s+)?' + key + r'\s*=', p.read_text(), re.M) for key in values):
            raise Error(f'{p} overrides requested settings. Resolve this override before applying.')
    mkconfig = program('grub-mkconfig', 'grub2-mkconfig')
    checker = program('grub-script-check', 'grub2-script-check')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backups = []
    for path in (source, cfg):
        backup = path.with_name(path.name + '.bootlane-' + stamp)
        shutil.copy2(path, backup)
        backups.append((path, backup))
    fd, tmp = tempfile.mkstemp(prefix='.bootlane-generated-', dir=cfg.parent)
    os.close(fd)
    try:
        atomic(source, update_grub(source.read_text(), values))
        run(mkconfig, '-o', tmp)
        run(checker, tmp)
        atomic(cfg, Path(tmp).read_text())
    except Exception:
        for path, backup in backups:
            atomic(path, backup.read_text())
        raise
    finally:
        Path(tmp).unlink(missing_ok=True)
    print('Backups: ' + ', '.join(str(b) for _, b in backups))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loader', choices=['auto', 'grub', 'systemd-boot'], default='auto')
    parser.add_argument('--list', action='store_true', help='show boot menu entry IDs')
    parser.add_argument('--timeout', type=int, help='seconds, 0 for immediate boot, -1 to wait indefinitely')
    parser.add_argument('--default', help='exact menu entry ID from --list')
    parser.add_argument('--firmware-list', action='store_true')
    parser.add_argument('--boot-order', help='UEFI IDs in priority order; omitted current IDs are appended')
    parser.add_argument('--apply', action='store_true', help='perform previewed changes (requires root)')
    args = parser.parse_args(argv)
    if args.timeout is not None and not -1 <= args.timeout <= 86400:
        raise Error('Timeout must be -1 or between 0 and 86400 seconds.')
    if args.boot_order and (args.timeout is not None or args.default):
        raise Error('Apply firmware order and bootloader preferences separately.')
    if args.firmware_list or args.boot_order:
        raw, current, available = firmware()
        if args.firmware_list:
            print(raw, end='')
        if args.boot_order:
            new = order_value(args.boot_order, current, available)
            print('UEFI order: ' + ','.join(current) + ' -> ' + ','.join(new))
            print('Undo: sudo python3 bootlane.py --boot-order ' + ','.join(current) + ' --apply')
            if args.apply:
                require_root()
                run(program('efibootmgr'), '--bootorder', ','.join(new))
                if firmware()[1] != new:
                    raise Error('Firmware did not retain the requested order.')
        return
    loader = detect() if args.loader == 'auto' else args.loader
    print('Bootloader: ' + loader)
    listed = entries(loader) if args.list or args.default else []
    if args.list:
        for e in listed:
            print(e['id'] + '\t' + e['title'])
    if args.default and args.default not in [e['id'] for e in listed]:
        raise Error('Default must exactly match an ID from --list.')
    if args.timeout is None and not args.default:
        if not args.list:
            print('Use --list, --timeout SECONDS, --default ID, or --firmware-list. See --help.')
        return
    if loader == 'systemd-boot':
        # A single firmware variable update per invocation avoids partial multi-setting writes.
        if args.default and args.timeout is not None:
            raise Error('Set systemd-boot timeout and default in separate invocations.')
        cmd = [program('bootctl'), 'set-default', args.default] if args.default else [program('bootctl'), 'set-timeout', 'menu-force' if args.timeout == -1 else str(args.timeout)]
        print('Preview: ' + shlex.join(cmd))
        if args.apply:
            require_root()
            run(*cmd)
    else:
        values = {}
        if args.timeout is not None:
            values.update(GRUB_TIMEOUT=args.timeout, GRUB_TIMEOUT_STYLE='menu')
            # Fedora's automatic hidden menu overrides the visible menu preference.
            envtool = shutil.which('grub2-editenv') or shutil.which('grub-editenv')
            if envtool and re.search(r'^menu_auto_hide=1$', run(envtool, '-', 'list'), re.M):
                raise Error('GRUB automatic hiding is enabled. Run sudo grub2-editenv - unset menu_auto_hide (or grub-editenv), then retry.')
        if args.default:
            values.update(GRUB_DEFAULT=args.default, GRUB_SAVEDEFAULT='false')
        print('Preview /etc/default/grub: ' + json.dumps(values))
        print('Regenerate and validate the GRUB menu; back up original files first.')
        if args.apply:
            require_root()
            apply_grub(values)
    if not args.apply:
        print('No changes made. Add --apply with sudo to save.')

def require_root():
    if os.geteuid() != 0:
        raise Error('Applying changes requires root. Run with sudo.')

if __name__ == '__main__':
    try:
        main()
    except (Error, OSError, ValueError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        sys.exit(1)
