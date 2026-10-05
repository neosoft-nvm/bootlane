# Bootlane

**Choose what boots. Choose how long it waits.**

A small, portable Linux desktop and command-line utility for GRUB, systemd-boot, and UEFI boot priorities. One Python file; no Python packages to install. Requires Python 3.8 or newer and the distribution's existing bootloader tools.

## Desktop app

Bootlane has a dark desktop interface with mint accents, boot-entry selection, a waiting-time control, firmware priority buttons, and a confirmation preview opened by Apply changes. It uses Tk, the standard Python desktop toolkit; it does not require a browser or background server.

Install the desktop dependencies using your distribution's package manager:

| Distribution | Command |
| --- | --- |
| Ubuntu / Debian / Mint / Pop!_OS | `sudo apt install python3-tk pkexec` |
| Fedora / Rocky / AlmaLinux | `sudo dnf install python3-tkinter polkit` |
| openSUSE | `sudo zypper install python3-tkinter polkit` |
| Arch / Manjaro / EndeavourOS | `sudo pacman -S python tk polkit` |

Package availability can vary by distribution version; `pkexec` may be packaged separately. Your desktop must have a running PolicyKit authentication agent. The existing GRUB/bootctl tools described below are also required; firmware priorities need `efibootmgr`.

From the downloaded or cloned folder:

```sh
python3 bootlane_gui.py
```

To add Bootlane to your app menu, run this **without sudo**:

```sh
python3 install.py
```

The installer copies the app to your user data folder and creates a desktop launcher. To update it after downloading a new version, run the installer again.

Select a boot menu entry, set the waiting time, and click **Apply changes**. A preview opens with **Confirm and apply** and **Cancel** buttons. Changes are saved only after you confirm. Closing the preview or pressing Escape cancels without saving. Leave all entries unselected to change only the timeout; turn off the waiting-time checkbox to change only the default entry. On systems with protected boot files (including Fedora), Bootlane offers to read them through the administrator password dialog. This read does not change settings. You can also use **Read as administrator** directly. Protected previews may ask for authentication again. The firmware view lets you move existing boot priorities up and down.

Bootlane stays open as your normal user; administrator commands use the system password dialog. If you change both timeout and default, they are saved sequentially. If a later setting fails, an earlier successful setting remains saved. The CLI can be used to restore it. No automatic reboot occurs.

The GUI source has been checked, but this development environment has no graphical display, so live rendering and interaction still need verification on a desktop Linux machine.

## Command-line quick start

```sh
python3 bootlane.py --list
python3 bootlane.py --timeout 5
sudo python3 bootlane.py --timeout 5 --apply
python3 bootlane.py --default 'ENTRY_ID_FROM_LIST'
sudo python3 bootlane.py --default 'ENTRY_ID_FROM_LIST' --apply
```

Commands preview changes unless you add `--apply`. Listing may need sudo when /boot is restricted. Default IDs must match an entry from `--list`. GRUB submenu entries use `parent-id>entry-id`; quote these in your shell. Timeout 0 boots immediately; -1 waits indefinitely; other values are seconds.

When both GRUB and systemd-boot are installed, select the bootloader actually used by your machine:

```sh
sudo python3 bootlane.py --loader grub --timeout 5 --apply
sudo python3 bootlane.py --loader systemd-boot --timeout 5 --apply
```

systemd-boot default and timeout changes are applied separately. It uses bootctl's persistent EFI settings, which take precedence over loader.conf. It requires a bootctl version supporting `--json=short list`, `set-default`, and `set-timeout` (and `menu-force` for indefinite waiting). Unsupported commands produce an error.

## UEFI boot order

```sh
sudo python3 bootlane.py --firmware-list
sudo python3 bootlane.py --boot-order 0002,0001
sudo python3 bootlane.py --boot-order 0002,0001 --apply
```

Use the four-digit IDs shown by efibootmgr. Existing priorities omitted from your request are appended so entries remain available. The utility prints an undo command before applying and checks the resulting order. Requires efibootmgr and access to UEFI variables. Firmware order chooses which bootloader runs first; the bootloader default chooses its menu entry. Legacy BIOS device order and bootloader menu rearrangement are outside this utility's scope.

## Distribution coverage

| Distribution family | Intended backend | Required tools |
| --- | --- | --- |
| Ubuntu, Debian, Linux Mint | GRUB | grub-mkconfig, grub-script-check |
| Fedora, RHEL, Rocky, AlmaLinux | GRUB with BLS entries | grub2-mkconfig, grub2-script-check |
| openSUSE | GRUB | grub2-mkconfig, grub2-script-check |
| Arch, Manjaro, EndeavourOS | Installed GRUB or systemd-boot | Corresponding tools |
| Pop!_OS and other systemd-boot installations | systemd-boot | bootctl |

Coverage is based on bootloader interfaces and conventional paths, **not a completed hardware/distribution certification matrix**. Custom layouts, immutable installations, older bootctl versions, and other bootloaders may require adaptation. Mount your actual /boot and EFI partition first; do not run from a live image or chroot without verifying the target. Bootlane does not install or replace a bootloader.

GRUB distinguishes protected files from missing files and accepts symlink aliases for the same configuration. It requires one unambiguous `/boot/grub/grub.cfg` or `/boot/grub2/grub.cfg`. It never regenerates an EFI vendor stub. It lists stable IDs in generated GRUB menus and BLS files. Dynamically generated or unusual menu layouts may not be listed; inspect the chosen entry before rebooting. Direct GRUB IDs select a fixed kernel entry rather than automatically following future kernel upgrades.

## Backups and recovery

Before GRUB changes, Bootlane saves timestamped copies beside `/etc/default/grub` and the generated `grub.cfg`. It regenerates to a temporary file, checks GRUB syntax, then replaces the menu while preserving extended attributes, including SELinux labels. Generation, validation, or automatic-hiding update failures restore the backed-up files. When setting a timeout on Fedora with automatic menu hiding enabled, the preview explains that hiding will be disabled. Apply backs up the GRUB environment file as well, then disables hiding so the selected timeout takes effect. Keep the reported backups until you have booted successfully. For manual recovery, copy each reported backup over its original path using sudo. If the machine cannot boot, perform this from a recovery environment with the target filesystems mounted.

GRUB configuration generation executes your distribution's installed scripts. Custom scripts can have side effects outside the two backed-up files. Later grub.d settings that explicitly override requested values cause Bootlane to stop. Fedora automatic menu hiding is handled as part of the timeout change and included in backups. The environment is read from grubenv beside the detected GRUB configuration, following any symlink to the actual file.

systemd-boot uses EFI variables rather than file backups. Inspect current settings with `bootctl status` before changing them. Restore previous values with `bootctl set-default PREVIOUS_ID` or `bootctl set-timeout PREVIOUS_TIMEOUT`; pass an empty string to clear an override and use loader.conf again. No reboot is performed automatically.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests cover nested GRUB IDs, literal configuration values, priority validation, preview-only behavior, protected boot files, GUI authentication retries, file permissions, extended attributes, and rollback. Integration tests use installed GRUB tools against temporary environment files to verify automatic-hiding removal, preservation of other variables, and byte-for-byte rollback after a failure. Real boot and firmware changes have not been tested on hardware.

## References

- [GNU GRUB configuration](https://www.gnu.org/software/grub/manual/grub/html_node/Simple-configuration.html)
- [Fedora unified GRUB configuration paths](https://fedoraproject.org/wiki/Changes/UnifyGrubConfig)
- [systemd bootctl](https://www.freedesktop.org/software/systemd/man/latest/bootctl.html)
