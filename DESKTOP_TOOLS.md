# Hya v0.8.2 — Desktop Assistant Capabilities

Launch `python hya.py`, open chat, and select an installed **local** Ollama model.
Hya inspects `/api/show` before generation. If the selected model advertises both
text completion and `tools`, the request includes six strict function schemas.
Otherwise no tools are offered: ordinary chat works and the status explains that
direct desktop actions are unavailable. Models are not installed or downloaded.

Examples to try with a tool-capable model:

- “Open calculator.” or “Open the file manager.”
- “Show my CPU, available memory, disk usage and uptime.”
- “Find filenames containing invoice in /home/YOUR_USER/Documents.”
- “Search the web for KDE keyboard shortcuts, after asking me.”
- “Draft a Bash backup script for me to review and copy. Do not run it.”

## Current smart-permission policy

v0.8.1 supersedes the original always-confirm rules described in earlier release
notes. Trusted ordinary graphical applications and ordinary user directories can
open automatically. Searches reuse explicitly remembered directory scopes.
Administrative/terminal/unclassified app launches, unapproved/private scopes and
all external browser searches require approval. Automatic app launching can be
disabled in Settings, and stored search scopes can be forgotten there.
Read SMART_PERMISSIONS.md for the full boundary and current verification.
File-content access and data/config modification remain unsupported.

## Allowed tools and permissions

| Structured function | Arguments | Behavior / permission |
|---|---|---|
| `list_applications` | none | Enumerates launchable desktop IDs and names from XDG applications directories; read-only. |
| `open_application` | `application` | Ordinary app name/purpose, resolved against installed entries. Friendly choice if ambiguous; ordinary trusted apps launch automatically, otherwise confirmation. |
| `open_directory` | `directory` | Opens an existing directory through the default file manager. Ordinary user paths open automatically; private/outside-home paths require approval. |
| `system_info` | none | Basic OS, CPU, logical CPUs, memory, root disk and uptime; read-only. |
| `search_files` | `directory`, `name` | Filename substring search only. Unapproved scopes need explicit persistent filename-search authorization; remembered ordinary descendants need no repeat dialog. |
| `web_search` | `query` | Safely encoded DuckDuckGo URL in the default browser. Always asks Allow once. |
| `draft_bash` | `script` | Returns text with `executed:false`; never executes or saves a script. |

There is no shell/terminal command tool, deletion, file-content reader, file
editor, privilege escalation, package installation, or configuration tool.
Unknown names, missing/extra keys, malformed types, controls in path/query/IDs,
invalid IDs, and oversized strings are rejected. Python expression strings,
JSON-looking prose, Bash fences and tool names in plain chat text never dispatch
anything. Tool schemas help the model; actual validation and permission checks
are mandatory in application code.

Permission dialogs belong to the existing chat window and show application-built
arguments as read-only plain text. Application prompts show the friendly name of the resolved installed app;
its entry and digest remain bound internally for launch revalidation; web prompts include the actual encoded URL and external
transmission notice; search prompts show the **canonical directory** and filename
query. One-shot approvals apply to exactly the shown arguments. Filename-search grants
explicitly authorize future searches in the shown scope until revoked. Deny is the default;
closing the dialog denies. Policy-owned automatic approval applies only to the categories documented in
SMART_PERMISSIONS.md. Search scope authorizations are persisted and can be revoked;
model-supplied confirmation or category flags are never accepted.
A denial consumes the token immediately and blocks all subsequent protected
requests for the rest of that user message. A new user message can request again.
Stop cancels rather than approving. Chat remains responsive while awaiting input.

## Application launch boundary

Desktop entries are discovered from `$XDG_DATA_HOME/applications` and
`$XDG_DATA_DIRS/*/applications` using desktop-file IDs (nested paths become IDs
with hyphens). User overrides mask system entries, including Hidden overrides.
Entries must be valid UTF-8 Application entries with Exec or DBusActivatable;
Hidden, NoDisplay, Terminal=true, symlinked, oversized, malformed, and unavailable
TryExec entries are excluded. The model passes the user’s ordinary name/purpose, never asks users for IDs.
An internal desktop_id form remains accepted for backward compatibility, but is
not advertised in the model-facing schema.

Natural-name resolution uses Name (including localized names), GenericName,
Keywords, Categories and the identifier brand. Synonym groups for calculators,
file managers and terminals are matching hints only: every candidate must be in
the discovered catalog. A unique strong match goes directly to policy evaluation: an ordinary trusted
application launches automatically; other applications need friendly confirmation. Generic requests do not prefer an app literally named Calculator
over KCalc when both are installed. An explicit installed brand name takes
precedence; a missing brand does not silently substitute a different app.

Multiple plausible matches show up to six friendly names with generic descriptions.
The chooser starts unselected. Continue selects a candidate; policy evaluation follows: ordinary trusted apps launch immediately; other apps
show an “Open KCalc?”-style confirmation. Missing apps
produce a friendly no-match error, with no path/shell fallback. Broad results
suggest a more specific name rather than guessing. Backend choice validation
accepts only entries from the current request; stale/forged selections and
approval before selection fail closed. The selected ID is then passed internally
to the existing launcher.

Launches re-resolve the ID and compare the entry to the confirmation snapshot.
If its contents changed, launch is rejected. The app runs through `gio launch`
with a fixed executable and argv, `shell=False`, and no additional model args.
Hya does not parse or execute model command strings or reinterpret the entry's
Exec field itself. Installed desktop entries and their applications are trusted
local programs: an approved app can perform its normal behavior independently
of Hya. Helper/hidden/terminal entries are intentionally unavailable.

`gio open` receives only a fixed HTTPS search URL built with `urlencode`, not a
model-provided URL or scheme. Search terms are not interpreted as shell syntax.
This is the sole intentionally external action: the browser sends the approved
query to DuckDuckGo. Model inference and conversation storage remain local.
No app or browser is launched automatically during setup or tests.

The `gio` executable is supplied by GLib on typical Linux distributions (including
EndeavourOS). Missing GIO produces a clear tool error, without installing anything.
A successful launcher exit means **launch requested**, not proof a window appeared.
Wayland activation/focus and app behavior remain compositor/application controlled.

## Filename-only directory authorization

The requested absolute directory is canonicalized before the permission prompt.
The user explicitly authorizes filename searches in that canonical directory
and ordinary descendants; new hidden/private scopes require separate permission. An alias/symlink root is shown as its resolved target, never silently
granted. Changing its inode before execution invalidates authorization.

Traversal uses directory descriptors, O_NOFOLLOW and relative child opens;
symlink files and directories are skipped. File contents are never opened. Only
regular filenames matching a case-insensitive substring are returned. The search
is bounded to 100 matches, 30,000 visited entries, 24 nested levels and a six-second
cooperative traversal budget. Permission errors are skipped; results identify
truncation. There is no implicit broad home-directory search grant. Remembered grants are
explicit, bound to directory identity, and revocable.
Cancellation is checked between entries; a kernel/filesystem operation already
blocked on an unhealthy/network filesystem cannot be forcibly interrupted by
Python, but runs off the UI thread.

## Streaming, tool results and cancellation

Ollama HTTP remains asynchronous QtNetwork. The client accumulates streamed
content, thinking fields and structured tool calls. Calls run **only after** the
complete HTTP stream has a valid final done marker. At most four calls per model
turn and three tool rounds per user message are allowed; excess calls fail closed.
Calls are processed sequentially. Results/denials/errors are sent back as role
`tool` messages, then Ollama streams its final natural-language explanation.
There is one busy conversation/generation throughout the workflow. Ephemeral
structured turns are not replayed as fresh commands from persisted chat history.

Desktop preparation, metadata reads, file enumeration, process launch waits and
log I/O run in Qt's worker pool. The original animation timer and expression
controller continue Thinking across HTTP, permission and execution phases.
Manual Expression Studio overrides remain protected. The permission dialog is
modeless, so chat Stop and character animation remain usable. Expand/Compact,
docking, existing history and other chat controls retain their prior behavior.

Stopping/closing chat invalidates the current token, aborts HTTP, cancels queued
work and dismisses permission prompts. Late worker results cannot start another
model round. Cancellation is cooperative after execution starts. An app/browser
already dispatched cannot be undone; chat explicitly reports that limitation.
Actual executed attempts retain their final audit outcome even if the chat reply
was cancelled. Final assistant persistence still uses the original complete /
cancelled / error states. No SQLite migration is performed.

## Local action log

Expand → **Action Log** reads the private local audit trail asynchronously:

`$XDG_DATA_HOME/hyal/desktop-actions.jsonl`

Normally `~/.local/share/hyal/desktop-actions.jsonl`. New files use owner-only
0600 permissions. Records contain UTC time, tool name, relevant arguments and
started/completed/failed/denied/rejected/cancelled status. Script bodies are not
copied into this log; only their character count is recorded. Search path/query
and browser queries are local sensitive metadata, so the file is ordinary private
plaintext rather than an encrypted store. Conversation deletion does not delete
the separate audit trail. There is no model-accessible log-reading or deletion tool.
The viewer shows the most recent 100 KB without opening external files or apps.

A writable log is required **before** execution: logging failure prevents side
effects. A failure writing the final outcome can occur after dispatch; the error
explicitly says an action may already have completed. Started-only records after
a crash must not be interpreted as successful completion.

## Architecture and public integration points

- `application_resolver.py`: deterministic name/metadata/alias matching over the discovered catalog only.
- `desktop_tools.py`: Python standard-library registry, exact validation, schemas,
  canonical preparation, grant checking and bounded tool implementations. No UI
  or language-model dependency. `execute()` independently validates and requires
  an exact-bound Grant for protected actions.
- `desktop_service.py`: asynchronous worker pool, one-shot permission token broker,
  cancellation and local action log. `submit(call)` returns a token and emits
  `permission_needed(token, details)` or `result(token, data)`; only the UI calls
  `approve(token)` or `deny(token)`. `begin_turn()` resets denial suppression for
  a newly submitted user message. This API is not exposed as a model tool.
- `ollama_client.py`: capability gating, structured streaming, bounded tool rounds,
  continuation messages and cancellation; connects to an injected DesktopService.
- `chat_window.py`: permission UI, action progress/results, Bash-copy rendering,
  model compatibility notice and Action Log access.
- `system_prompt.txt`: editable capability-aware personality and honest-action rules.
- `hya.py`: version 0.8.2 only. Character artwork/docking/edge logic is unchanged.

The original appearance, personality, AI settings, SQLite store, action-free chat
widgets and Layer Shell QML are unchanged. No system tray packaging, eyebrows,
heavy dependencies or character redesign are included.

## Verification and remaining desktop checks

All 110 tests passed (the original 88 plus 22 new desktop-tool tests), along
with syntax compilation and the offscreen application smoke test. Automated
tests mock Ollama HTTP and all launcher side effects. They cover:
strict validation, permission/grant binding, stale/double approvals, immediate
denial and retry suppression, cancellation before approval/during execution,
worker responsiveness, logging failure before launch, action-log persistence,
installed-ID resolution/entry changes, encoded URLs/fixed argv/no shell,
filename authorization/no contents/symlink skipping/directory identity, bounded
search, text-only Bash, tool-capable streaming/results, malformed/unknown calls,
no-tool models/plain-text non-execution, round limits, real permission UI buttons,
conversation persistence and every existing character/chat/edge regression.

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m compileall -q hya.py desktop_tools.py desktop_service.py ollama_client.py chat_window.py tests tools
```

A timed offscreen startup/dock/expand/close/reopen/shutdown smoke test passes.
Real Wayland startup still aborts with exit 134 before opening a window in this
execution environment. No real application/browser was launched for testing;
launches and native tool-capable Ollama responses require desktop verification.

Manual KDE Plasma Wayland checklist:

1. Select a local model that advertises tools. Ask to open an installed app.
   Verify an ordinary trusted app launches automatically. Disable automatic app
   launching in Settings and verify Deny prevents dispatch. Inspect Action Log.
2. Request a browser search with punctuation and Unicode. Check the exact query,
   external-provider notice, approval, default-browser URL and focus behavior.
3. Request filenames in a small directory. Authorize that exact directory once;
   check symlink skipping, no contents, cancellation and result explanation.
4. Stop/close chat with a pending permission, and stop after approving a launch.
   Verify no stale dialog, duplicate operation or model continuation appears;
   an already-launched app is allowed to remain open.
5. Select a model without tools: ordinary chat and Bash drafting must still work
   with a clear direct-action limitation. Check HTTP/tool errors remain readable.
6. During actions, test docking, Expand/Compact, colors, manual Sleeping/Studio,
   Bottom/Left/Right restore, clipboard copies and chat-history restart behavior.

Backup before editing:
`backups/v0.7.1-before-v0.8-20261018-225300/`.

API references: [Ollama structured and streamed tool calls](https://docs.ollama.com/capabilities/tool-calling), [GIO desktop launch implementation](https://mail.gnome.org/archives/commits-list/2020-December/msg02950.html).

## Application-name resolution verification

All 118 automated tests passed, including the original 110 and eight new
application-resolution tests; syntax compilation also passed.
`tests/test_application_resolution.py` adds isolated XDG entry fixtures covering
common aliases, specific brand preference, non-KDE alternatives, missing programs,
localized/generic/keyword metadata, ambiguity and bounded lists, excluded entries,
choice then confirmation, stale choices, and changed entries. Actual installed
metadata was also inspected without launching anything: calculator matched KCalc,
file manager matched Dolphin, and terminal found Konsole/UXTerm/XTerm as choices.
Live Ollama interpretation and real KDE application launch/focus still require
the desktop checks above. Existing permission, cancellation and logging behavior
remain enforced. No character, animation, Ollama transport, or history code changed.

XDG metadata reference: [recognized desktop entry keys](https://specifications.freedesktop.org/desktop-entry/latest/recognized-keys).

Application-launcher backup before this improvement: `backups/v0.8-before-app-resolution-20261018-231723/`.

Current v0.8.1 policy details and verification: SMART_PERMISSIONS.md.

For v0.8.2 presentation, local fast routing, launcher fix and timings, see DESKTOP_SPEED.md.
