# Hya v0.8.2 — Desktop action speed and chat fixes

Run `python hya.py`; restart an existing Hya process to load this version.
Backup: `backups/v0.8.1-before-v0.8.2-20261018-235717.tar.gz`.
Appearance, animations, docking, edge QML, settings paths and conversation database
schema are preserved. No existing user history or permission scopes are deleted.

## Tool execution → history → presentation

Previously, `OllamaClient._desktop_result` emitted an internal result record, and
`ChatWindow._action_result` explicitly made an extra “Desktop tool · …” JSON
bubble. The same result was also sent to Ollama, whose final reply could echo the
JSON and be saved as ordinary assistant text. That produced both debug output and
duplicate summaries.

Now the structured result stays in the internal Ollama tool turn. The UI displays
a short human status, without creating another assistant bubble. Tool-turn
preambles are cleared before execution; the final model explanation uses the
existing single reply bubble. Empty final replies fall back to a local human
summary. Bash drafts remain one copyable fenced-code response.

`action_presentation.py` recognizes tool-shaped JSON, including errors, legacy
“Desktop tool” records and JSON fences. Partial JSON is buffered for display.
Known embedded result objects in post-tool explanations are also converted.
If JSON is echoed, the current UI uses the actual action outcome rather than
trusting an echoed success claim. Final text is sanitized **before** persistence.
Legacy assistant records are filtered on loading and context construction without
rewriting the original history. User messages and ordinary code examples retain
their original content. This does not attempt to rewrite every arbitrary model
statement; a natural-language model explanation can still be mistaken.

Action Log retains bounded structured outcomes and error diagnostics. Script
bodies remain excluded; only their character counts are logged. Permissions,
validation, denial suppression and cancellation continue to run in DesktopService.

## Compact header

The actual compact layout contains Hya, Expand and Close. Options has been removed
from construction and layout, rather than merely hidden behind a different state.
Expand exposes the existing model, conversation, Settings and Action Log controls.
Expand/Compact still share one session, draft, stream and docked character.
Offscreen captures of the actual widgets are `previews/local-chat.png` and
`previews/chat-workspace.png`.

## Launcher acknowledgement

The previous launcher used `Popen.communicate()` with stderr=PIPE. A GUI descendant
can inherit that pipe and keep it open after GIO exits. Waiting for EOF could then
cause the misleading ten-second timeout.

The launcher still uses fixed GIO argv with `shell=False`, in the existing worker
pool. It now waits only for the **GIO process**, with stderr redirected to a
private temporary file. A running GUI cannot keep that wait alive. Cancellation
terminates the launcher, not the launched application's process group. An actual
hung GIO request remains bounded and reports unknown acknowledgement; a nonzero
GIO exit reports failure and retains stderr diagnostics.

Zero exit means `launch_requested`: the desktop launch request was accepted.
It never means a window appeared. There is no window-appearance verification in
this version. See [GIO's launch contract](https://gnome.pages.gitlab.gnome.org/gtk/gio/method.AppInfo.launch.html).

## Optional local fast path

Settings → **Resolve simple desktop requests locally (fast path)** is enabled by
default and persists as `local_intents` in the existing `hyal/ai.ini`. Normal chat
setup still requires a selected, discovered local model; this release does not
add a separate offline chat mode.

A whole-utterance grammar recognizes simple requests such as:

- Open Dolphin / Launch Calculator
- Show my Downloads folder / Open Documents
- System info / Show system information

Applications must resolve to one strong installed match, reusing the existing
catalog and aliases. Missing, ambiguous and weak matches fall back to Ollama.
Only standard XDG user-folder aliases take the folder shortcut. Arbitrary paths,
private locations, multi-action prose, negations, quoted instructions, shell-like
syntax and complex requests do not trigger a local shortcut. The grammar is
intentionally limited and English-only; unsupported requests use normal chat.

Recognition and installed-app lookup run in the worker pool. A recognized request
is submitted to the **same** DesktopService preparation, validation, policy,
confirmation and audit path as an Ollama tool call. Terminal/admin/custom apps
still need approval; disabling automatic launching still forces confirmation.
No permission flags are supplied by the resolver. A cancelled or stale recognition
callback cannot dispatch a later action. Local results complete without an Ollama
request, avoiding inference and a redundant model summary. Model-driven requests
retain the existing structured tool loop and final explanation.

## Timings

`$XDG_DATA_HOME/hyal/diagnostics.log` (normally
`~/.local/share/hyal/diagnostics.log`) records timestamped milliseconds for
`intent_recognition`, `application_lookup`, `launcher_request`, and
`ollama_inference`. It rotates at 256 KB with one backup. No prompts, paths,
queries or response text are included. The separate Action Log remains the audit
record and must succeed before dispatch. Inference timing covers each chat request,
including failure/cancellation, rather than time waiting for permission.

A ten-sample read-only benchmark in this execution environment discovered 44
installed entries and resolved Calculator. Median catalog lookup: **156.4 ms**;
median matching against the catalog: **10.431 ms**. These are local measurements,
not an end-to-end KDE launch benchmark or an Ollama speed claim. No application
was launched. A regression also reproduces the inherited-stderr problem with a
short-lived fake launcher and a one-second descendant: acknowledgement completes
before the descendant exits.

## Verification and remaining desktop checks

Run with isolated test data:

```sh
QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME=/tmp/hya-test-config XDG_DATA_HOME=/tmp/hya-test-data python -m unittest discover -s tests
python -m compileall -q hya.py chat_window.py desktop_tools.py desktop_service.py ollama_client.py action_presentation.py local_intents.py diagnostics.py tests
```

All **150 tests** passed in the final full-suite run. Syntax compilation and an
offscreen startup → dock → expand → close → reopen → shutdown smoke test passed.
The actual compact and workspace widget captures were generated; the compact
capture was visually inspected to confirm Options is absent.

The suite covers live widget structure, success/error JSON echoes, persisted legacy
messages, copyable Bash, redacted audit records, aliases, ambiguous/missing apps,
negation/quoting/compound-command rejection, permission enforcement, cancellation
during recognition, model fallback, settings persistence, stage timings and the
launcher pipe regression. Existing animation, appearance, AI, docking and edge tests
are retained. Network requests and application launches are mocked, except for
the harmless Python launcher/descendant regression processes.

Real Plasma Wayland launch, placement and focus behavior are **not verified** here.
The sandbox also maps installed file ownership to UID 65534, so the conservative
trust policy may ask for approval here where a normal root-owned installation
would launch automatically. The ownership policy was not weakened.

Manual checks on the real desktop:

1. Open chat; confirm the compact header has Expand and Close, and Expand exposes
   all unique settings. Stream a response while switching views and resizing.
2. Ask “Open Dolphin”, “Launch calculator”, “Show my Downloads folder” and
   “Show system information”. Check concise results, no duplicate JSON bubble,
   correct permissions and accepted-versus-visible wording. Inspect both logs.
3. Disable each automatic/fast-path setting and verify its distinct effect. Try a
   terminal/admin app, an ambiguous installed name, negated/quoted requests and a
   sensitive request. Confirm permissions and fallback remain intact.
4. Stop during lookup, while permission is pending and after launch acceptance.
   No queued action should appear later; an already launched app cannot be undone.
5. Reopen old conversations with tool JSON, restart, and check history, scopes,
   copies, character expressions and Bottom/Left/Right docking/restoration.
6. Launch a long-running app and verify no false ten-second timeout. Check real
   GIO failures remain readable in Action Log. This version does not inspect
   compositor window lists to assert that a launch created a visible window.
