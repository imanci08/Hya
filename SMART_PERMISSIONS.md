# Hya v0.8.1 — Smart Permissions

This is part of v0.8.1's existing usability work, not a separate application or
visual redesign. Launch `python hya.py`; restart a running Hya to load it.

## Automatic and confirmed actions

- Ordinary trusted installed graphical apps can launch automatically. Standard
  system-installed Dolphin, KCalc, Kate, Firefox and comparable graphical apps
  are eligible. Natural names/aliases and the installed XDG catalog are reused.
- An ambiguous app request still presents friendly choices. Selecting an ordinary
  eligible app requests its launch immediately. An ineligible app instead gets a
  separate confirmation. A missing/untrusted identifier is never an executable
  path or shell fallback.
- `open_directory(directory)` opens a validated existing directory using the
  default file manager. Ordinary paths under the user's home open automatically.
  Home/Downloads/Documents/Desktop/Pictures/Music/Videos use Qt's XDG-aware user
  directory locations; `~/` and absolute paths are also accepted. Symlinks resolve
  to canonical targets; outside-home, hidden or sensitive locations need approval.
- Basic CPU/RAM/root-disk/uptime information, installed app listing, and Bash
  drafting remain automatic. Bash is text only and is never run or saved as a
  script. There is no terminal execution tool.
- Filename searches use remembered authorization for a canonical directory and
  its ordinary descendants. Unapproved or private scopes ask first.
- All browser searches still ask: an external query can disclose private data.
  There is no arbitrary external URL tool. File-content access, sensitive data
  readers, file editing/deletion, privilege escalation and configuration changes
  remain unsupported, rather than gaining new implicit permission in v0.8.1.
  New tools receive no automatic category by default.

## What makes an application eligible?

The `smart_permissions.py` policy is application code, independent of the model.
Only a discovered/validated XDG Application entry may be launched. Automatic
launch additionally requires root-owned system files under `/usr` or `/opt`,
with non-group/world-writable ancestors, and a trusted system executable. User
PATH overrides are not used to classify a bare executable. Symlinked desktop
entries, user-owned/custom entries and D-Bus-only entries are not automatic.

The policy uses known ordinary program roles and registered desktop categories,
checks installed Exec metadata with **inspection only** (never shell evaluation),
and rejects terminal/admin/security/settings roles, privilege flags, interpreter
or privilege wrappers, terminal programs, dangerous flags, and unexpected fixed
arguments. Only conservative simple GUI launch options and desktop field codes
are eligible. A normal desktop app can of course perform its own normal startup
behavior; this feature does not sandbox applications or prove that every possible
application is harmless. Unknown/custom/misclassified entries fall back to explicit
confirmation; Terminal=true entries remain excluded from the launch catalog.

Terminal emulators such as Konsole, system settings, disk/partition tools,
package managers and privileged launchers do **not** auto-launch. Choosing one by
its normal name does not override that rule. Confirmation shows its friendly name
and installed launch metadata. Model-supplied `automatic`, `approved`, `category`,
commands, executable paths, or extra arguments are rejected by schema validation.

Before execution, the broker rechecks automatic eligibility and the launcher
compares the current installed entry to its prepared snapshot. Grants are bound
to exact canonical arguments. Stop invalidates queued requests. Existing denial
suppression still blocks further protected actions for that user turn.

## Settings and search scopes

Expand → Settings contains **Automatically launch ordinary installed graphical
applications**, enabled by default. Unchecking it restores confirmation for every
application launch, including ordinary apps. It persists in the existing
`$XDG_CONFIG_HOME/hyal/ai.ini` (`auto_launch_apps`). Other AI and appearance
settings are preserved. Turning it off does not grant/revoke file search scopes.

The first search in a new scope explicitly asks to authorize **future filename
searches** in that directory and ordinary descendants. Approval is persisted in
`$XDG_CONFIG_HOME/hyal/permissions.json`, created atomically with 0600 permissions.
The record includes canonical path, device and inode. Replacement directories or
retargeted symlinks do not inherit approval. Old v0.8 one-shot audit records are
not silently converted into persistent grants; consent to one query was not
consent to future searches.

Hidden and sensitive subdirectories (dot-directories and names indicating private,
secrets, credentials, passwords, vaults, finance/tax/health, etc.) are skipped by
traversal and require a separate explicit root authorization before searching
inside them. Such a root can then be reused; deeper private directories still
need their own scope. Filenames in an explicitly approved root are searchable;
file contents are never opened. Existing descriptor-relative O_NOFOLLOW traversal,
result/depth/time limits and cancellation checks remain in place.

**Forget approved search directories** in Settings clears stored scopes
asynchronously. New searches then ask again. Opening a folder in the file manager
does not grant search permission, and filename permission does not grant file
contents or automatic opening of private folders. Sensitive-folder labels are
conservative heuristics, not a way to detect all possible personal information.

## Logging and interaction

Every tool retains its normal audit trail at
`$XDG_DATA_HOME/hyal/desktop-actions.jsonl`. Started records identify
`permission: automatic`, `confirmed`, or `read-only`; outcomes remain separately
recorded. Logging must work before dispatch. Results still report
`status: launch_requested`, not that an application or folder successfully opened.
The model's final explanation receives the same structured results.

Automatic policy checks, filesystem identity checks, persistence and launch waits
run in the existing worker pool. Chat, Stop, streaming, docking, manual expressions,
colors, breathing, edge anchoring and painting remain unchanged. Confirmation is
still modeless where required. No system tray, packaging, eyebrow or new character
appearance work is introduced.

## Verification

All 132 automated tests and syntax compilation passed. An offscreen startup,
dock, expand, close, reopen and shutdown smoke test also passed. Real Plasma
Wayland application launch and permission behavior remain manually unverified.

Run:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m compileall -q hya.py smart_permissions.py ai_settings.py desktop_tools.py desktop_service.py chat_window.py tests
```

New tests cover ordinary apps without a dialog, unsafe/custom/admin/terminal and
interpreter entries, trust/ownership/write-permission checks, persisted automatic
launch disablement through the actual Settings UI, forged argument rejection,
external search permission, ordinary/private/outside-home folder opening, standard
folder aliases, remembered/reloaded/revoked filename scopes, private descendants,
changed directories/symlinks, basic read-only actions, text-only Bash, automatic
ambiguous selection, log mode and unchanged launch-result formatting. Existing
application-choice tests retain their explicit-confirmation checks for untrusted
test entries, updated only to wait for the new asynchronous policy phase.

Automated launch side effects are mocked. The installed system files appear as
UID 65534 rather than root in this development sandbox, so real eligibility checks
here conservatively require confirmation. Tests simulate trusted system ownership
to exercise automatic paths without weakening production ownership checks. The
real KDE desktop, outside this sandbox, must verify ordinary system package files
have their normal root ownership. No real application or external search was
launched automatically during testing.

Manual Plasma Wayland checks:

1. Ask “Open Dolphin”, “Open calculator”, “Open Kate” and “Open Firefox” with a
   tool-capable local model. Verify an ordinary system-installed app launches
   without a dialog and its audit entry is automatic / launch requested.
2. Ask for Konsole and an administrative utility. Verify confirmation appears;
   Deny/Stop must prevent dispatch. Custom launchers should also require approval.
3. Disable automatic app launching in Settings, restart, and verify Dolphin asks.
   Re-enable it and verify the normal no-dialog behavior returns.
4. Open Downloads and a private/outside-home folder. Verify the latter asks and
   ordinary folder opening does not grant filename-search or content access.
5. Authorize a filename directory once, search again after restart, then clear
   scopes in Settings. Verify new/private scopes ask and symlinks are skipped.
6. Check all external browser searches still ask, text-only Bash copies do not
   execute, and streaming/animations/docking/edge restoration remain as before.

Backup before editing: `backups/v0.8-before-smart-permissions-20261018-234044/`.

Policy references: [desktop entry fields](https://specifications.freedesktop.org/desktop-entry/latest-single/),
[registered application categories](https://specifications.freedesktop.org/menu/latest/category-registry.html).
