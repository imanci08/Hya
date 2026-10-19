# Hya v0.9.1 — Standalone Edition

Run development with `python hya.py`. The installed application runs as `hya`
from any working directory or KDE's application launcher.

## Build in an isolated directory

```sh
python tools/prepare_release.py --output /tmp/hya-v0.9.1-build
cd /tmp/hya-v0.9.1-build
SOURCE_DATE_EPOCH=$(cat SOURCE_DATE_EPOCH) makepkg --cleanbuild
```

Install build dependencies (`base-devel`, `desktop-file-utils`, `cmake`) and the runtime
packages declared in PKGBUILD using your normal distribution workflow if missing.
Do not run makepkg as root. The build never installs itself or pulls AI models.
The snapshot has a real SHA-256 checksum and deterministic source metadata.

## Install / update / remove (user-approved operations)

```sh
sudo pacman -U hya-0.9.1-1-x86_64.pkg.tar.zst
hya
sudo pacman -R hya
```

Updating uses `pacman -U` with a newly built version. Package removal leaves
per-user preferences and history intact. No installation or removal was performed
by the development agent. Runtime packages are Python, PySide6, Qt Base,
Qt Declarative, Qt SVG, Layer Shell Qt, KWindowSystem, Shiboken and GLib (GIO). The current Arch Qt Base
package supplies the Wayland platform plugin; older distro packaging may also
need its separate Qt Wayland runtime. Ollama, sudo and native setup terminals
are optional. No Python wheels, Qt libraries, GPU stacks or models are bundled.

## Installed filesystem layout

- `/usr/bin/hya`: executable Python launcher, independent of the source directory.
- `/usr/lib/hya/`: Python implementation, QML, prompt and icon asset.
- `/usr/share/applications/io.hyalos.Hya.desktop`: KDE launcher.
- `/usr/share/icons/hicolor/scalable/apps/hya.svg`: application/tray icon.
- `/usr/share/doc/hya/`: standalone/setup documentation.

The SVG is only the launcher/tray identity. Every animated character surface
continues using the original QPainter implementation.

## Profiles and optional import

Development retains `~/.config/hyal` and `~/.local/share/hyal`. Installed Hya uses
`~/.config/hya`, `~/.local/share/hya`, and `~/.cache/hya`. XDG overrides are honored.
The installed entry point selects its profile in-process, not through an
inherited environment variable. Configuration, SQLite history, permission scopes,
action logs, diagnostics and instance locks are separate. Both profiles can run
independently; duplicates within one profile activate the existing instance. In
containers that prohibit Unix IPC sockets, startup falls back to a lock-only
mode: duplicate launches are still blocked, but cannot activate the existing UI.

To explicitly copy development preferences, approved search scopes and history:
close installed Hya, before creating installed settings/history, then run:

```sh
hya --import-development --yes
```

Without `--yes` the command only explains consent. Import copies the known INI
files, permissions.json and a consistent SQLite backup; it never shares a live
connection or overwrites destination data. Source files are preserved. Logs and
caches are not imported. Import is optional; a fresh installed profile is default.

## Tray and Start on Login

Show Hya resumes the last desktop/edge state; Hide Hya suspends desktop surfaces
without quitting. Open Chat docks the original live character. Closing chat
restores the preserved desktop state. Settings opens expanded chat's settings.
Quit Hya shuts down HTTP requests, setup, chat, edge surfaces, tray and IPC.
The normal floating character remains a Tool window; workspace behavior is kept.

Start on Login is off by default. The installed tray toggle creates/removes only
`$XDG_CONFIG_HOME/autostart/io.hyalos.Hya.desktop`, pointing to `/usr/bin/hya`.
Development cannot enable installed autostart. Repeated enabling does not create
duplicates; unmanaged/symlinked entries are not overwritten. A leftover entry
uses TryExec, so a removed executable is not launched. Disable before uninstall
if you also want that user file removed. No system-wide startup files change.

If no tray host exists, Hide Hya is refused so a recovery surface remains.
Qt registers its icon when a host appears later; a lost host while hidden restores
the desktop surface. The lightweight host check runs only while tray-hidden.

## Orb terminology and adaptive title

Appearance → Orb Color keeps all presets and the existing `crystal/*` persisted
keys. Internal class/asset names remain compatible. Body geometry, painter,
expressions, rings and diamond are unchanged.
The shared compact/expanded Hya wordmark derives its translucent gradient and
restrained highlight/glow from Appearance, updates immediately on color changes,
and caches its pixmap between palette/size/font changes. A dark contour protects
contrast on lighter surfaces. No separate title setting or animation is added.

## First-run AI

See [AI_SETUP.md](AI_SETUP.md). The wizard reuses a local service and verified
installed models, offers explicitly approved native setup on supported systems,
and approved cancellable model downloads. Skip leaves the companion usable.
No first-run work runs through model tools. HyalOS can preconfigure the installed
profile/model and setup-complete flag using the same modular implementation;
no EndeavourOS path is embedded in application core.

The project did not include a redistribution license. `LicenseRef-Hya` records
that unresolved status; this local package recipe does not grant distribution
rights. Agree on a project license before publishing third-party builds.

## Manual KDE Plasma Wayland checks

1. Install the reviewed local package; launch from KDE and `hya` outside the source
   directory. Launch again: one instance per profile, existing chat/draft retained.
2. Check native tray presence, Show/Hide for normal/Bottom/Left/Right, Open Chat,
   compact/expanded docking, window-manager close, Settings and full Quit.
3. Temporarily remove the tray host: Hya must remain recoverable. Check floating
   character taskbar behavior separately from the normal expanded workspace.
4. Opt into Start on Login, log out/in, disable and repeat. Confirm no duplicates
   and no development database/config/log changes.
5. Run AI setup with existing/no Ollama and models; verify native authorization,
   download/cancel/disk-full handling and Skip. Preserve existing AI history.
6. Change every Orb Color (including white/Midnight) while compact and expanded;
   inspect title legibility/glow at desktop scale and 2× scaling. Check appearance,
   expressions, dragging, animations, edge clipping and tool permissions.

Real package installation, autostart login and native Plasma tray/Wayland behavior
have not been verified in this execution environment.

## Verification results

The v0.8.2 archive backup was verified against the source before editing:
`backups/v0.8.2-before-v0.9-20261019-002135.tar.gz`. Existing v0.8.1 backups
were not changed. Automated tests and source/package checks are recorded in
`dist/BUILD_REPORT.txt` with delivered artifact hashes in `dist/SHA256SUMS`.
The package was built, inspected and unpacked for offscreen testing, not installed.

For the v0.9.1 visual refinements, native blur request, preserved v0.9.0 rollback
package and candidate-specific release checks, see RELEASE_0.9.1.md.
