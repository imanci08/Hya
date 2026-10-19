# Hya local AI — v0.8.2 desktop tool integration

See [Desktop speed and UI fixes](DESKTOP_SPEED.md) for local shortcuts and diagnostics.

See [Smart Permissions](SMART_PERMISSIONS.md) for automatic-action policy and settings.

Launch with `python hya.py`. Hya still starts tucked behind the bottom-right
panel. Double-click the restored character, or right-click any character surface
and choose **Chat with Hya**. Chat opens only on request; the companion does not
need Ollama to start. Choose an installed local model, type a message, and press
Enter. Shift+Enter inserts a newline. Stop Generating cancels immediately;
closing chat (including Escape) also cancels. Reopening chat retains history.

## EndeavourOS / Arch setup

These manual setup steps remain available. The first-run wizard now offers
explicitly approved native installation on supported Arch systems and streamed
model downloads. It never installs silently. See [AI Setup](AI_SETUP.md).
Install the repository Ollama package and start its packaged service:

```sh
sudo pacman -S ollama
sudo systemctl enable --now ollama.service
```

For strictly local operation, configure Ollama itself to disable cloud features:
run `sudo systemctl edit ollama.service`, add the following, then restart it with
`sudo systemctl restart ollama.service`:

```ini
[Service]
Environment="OLLAMA_NO_CLOUD=1"
```

Choose a model suitable for your hardware from Ollama's model library. Review
its download size and license, then explicitly run `ollama pull MODEL`, replacing
MODEL with the chosen model tag. No model is assumed or bundled with Hya.
Start with a small quantized text/chat model on modest hardware. CPU inference
works; GPU support depends on Ollama and the installed drivers.

The Arch package includes `/usr/bin/ollama` and `ollama.service`:
[package files](https://archlinux.org/packages/extra/x86_64/ollama/files/).

## Other Linux distributions

Install Ollama through your distribution or the official
[Linux installation instructions](https://docs.ollama.com/linux).
For a foreground local server, run `OLLAMA_NO_CLOUD=1 ollama serve`.
Download your chosen model explicitly, then use Refresh models in Hya.
Do not start a second server if an existing Ollama service is already listening.
PySide6's QtNetwork and Python's sqlite3 are the only additional facilities used;
there are no new pip dependencies, cloud keys, or accounts.

## First run and settings

Chat checks the executable on PATH and asynchronously queries the local server.
A server in a container can work even if the executable is absent from PATH.
Unavailable servers, empty model lists, and missing saved models produce visible
instructions; Send stays disabled until a local model is selected. Cloud-backed
tags are omitted. Embedding-only models are rejected at generation time.

Selecting a model saves it as the default. Settings provides the loopback HTTP
endpoint (default `http://127.0.0.1:11434`), context tokens (4096), per-request
timeout (300 seconds), and model keep-alive (0 seconds). Zero requests immediate
unloading after each answer, trading warm-start speed for low memory use. A
positive keep-alive up to 300 seconds is available. Before switching models Hya
requests unloading of its previous model. Other Ollama clients can independently
load models; Hya does not control them. Stop aborts the HTTP request; actual
inference cleanup and memory release are handled by Ollama.

AI settings: `$XDG_CONFIG_HOME/hyal/ai.ini` (normally `~/.config/hyal/ai.ini`).
Appearance settings remain in their existing file. Failed settings writes are
shown in chat. The editable personality is `system_prompt.txt` beside `hya.py`,
read on every send. Keep that file with the application when packaging it.

## History and privacy

History: `$XDG_DATA_HOME/hyal/conversations.sqlite3` (normally
`~/.local/share/hyal/conversations.sqlite3`), created with owner-only file
permissions. History is ordinary, unencrypted local SQLite data. Conversation
selection, New, Clear, and Delete are available. Clear/Delete require confirmation
and affect only the selected conversation; repeat Delete to remove others.

User messages are committed before requests. Assistant rows start pending; only
an Ollama final `done:true` plus a successful HTTP finish makes a reply complete.
Cancelled/error replies retain visible partial text and a status label, and are
excluded from future prompts. Pending rows left by a crash become interrupted
on next startup; partial streaming text is held in memory until the request ends.
Recent complete messages are sent in chronological order with a conservative
character budget tied to context size. Older history remains on disk; it is not
semantic memory. A newest message exceeding that budget is truncated in model
context (the complete original remains visible and saved). Token usage is
model-dependent; Ollama enforces the actual context limit.

Hya accepts only numeric loopback/localhost HTTP endpoints, pins localhost to
127.0.0.1, disables HTTP proxies and automatic redirects, and only calls local
model listing, inspection, chat, and unload endpoints. Explicitly approved
browser web searches are separate external activity through the default browser;
they do not change the local Ollama endpoint. A model inspection with
no conversation text precedes each chat request: remote metadata or missing
local model information causes rejection. The local Ollama service and its
model metadata are trusted; disable its cloud features as described above for
server-side enforcement. See [Ollama's local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).

Responses are selectable **plain text**. v0.8 adds structured, allowlisted desktop
tools through a separate permission broker; plain text never executes actions.
The model has no shell execution, file content tool, file modification/deletion
or privileged-operation tool. User-approved first-run native setup is separate. See DESKTOP_TOOLS.md for the exact tools and confirmations.
Only the user-approved AI Setup wizard downloads models. Conversational/model
tool requests cannot initiate installation or downloads. Requests use the documented
[chat API](https://docs.ollama.com/api/chat) and
[model discovery API](https://docs.ollama.com/api/tags).

## Architecture and development

- `ollama_client.py`: asynchronous QtNetwork requests, NDJSON parsing across
  arbitrary UTF-8 fragments, bounded responses, deadlines, cancellation, model
  inspection, local-only validation, and explicit error signals.
- `ai_settings.py`: local endpoint validation and independent XDG INI settings.
- `conversation_store.py`: transactional SQLite conversations and reply states.
- `chat_window.py`: reusable modeless chat, setup feedback, model/settings/history
  controls, plain-text bubbles, throttled streaming painting, and keyboard input.
- `ai_activity.py`: existing ExpressionController ownership at AI priority 50.
  The original companion timer renews Thinking while busy. Manual Studio
  expressions (priority 100), including Sleeping, remain protected. Completion
  resets only AI-owned expressions; errors use Curious because Confused is not
  defined. There is no second facial animation system.
- `hya.py`: lazy chat entry points, AI activity integration in the existing timer,
  and shutdown cleanup. No painting, QML anchoring, clipping, offset, breathing,
  or restoration code was changed.

No blocking model requests, worker threads, or polling loops are used. Qt's
network event loop keeps sockets asynchronous. SQLite writes are small local
transactions on the GUI thread. Large histories are not paginated in v0.6; very
long conversations may take longer to render. A single response is capped at
2 MB of stream data; input is capped at 16000 characters.

The working v0.5.2 sources, tests, tools, QML and documentation are preserved in
`backups/v0.5.2/`. Existing legacy names and launch paths are retained.

## Verification

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m compileall -q hya.py appearance.py personality.py panel_boundary.py ai_settings.py ai_activity.py ollama_client.py conversation_store.py chat_window.py tests tools
QT_QPA_PLATFORM=offscreen python tools/render_chat_preview.py
```

The original 67 automated tests passed in the v0.6 verification, along with syntax compilation and an offscreen
application/chat launch smoke test. Tests use mocked HTTP replies, not an
installed/running model. They exercise
fragmented UTF-8 streams, request settings, cloud rejection before sending text,
HTTP/server/stream errors, deadlines, cancellation during inspection/generation,
model switching/unloading, history restart/recovery/deletion, input handling,
UI controls, expression precedence, and all existing edge/artwork regressions.
`previews/local-chat.png` and `previews/chat-workspace.png` are generated from actual Qt widgets with explicitly
fake model/history data, not a live AI response.

The execution environment successfully runs offscreen Qt and the installed Layer
Shell QML module. A real Wayland launch aborts with exit 134 here before a window
opens. No live Ollama executable/model was available. An additional attempt to run a
local mock HTTP server was blocked by sandbox socket permissions (EPERM);
the transport is tested through mocked HTTP replies, not a real socket here.
Real Plasma focus, visual
compositing and live inference are therefore **not verified** by these checks.

Desktop checklist:

1. Launch quietly into the existing bottom-right tuck. Open Chat with Hya from
   the edge menu; verify typing focus, taskbar access and readable glass styling.
2. With Ollama stopped, verify useful setup feedback and unaffected companion
   animations. Start it, refresh, choose a local model, and stream a reply.
3. Scroll upward during streaming; verify it stays put. Return to the bottom
   for automatic scrolling. Verify Enter, Shift+Enter, Stop, Escape, and reopen.
4. Send from Normal/Bottom/Left/Right. Verify Thinking appears on the shared
   character, breathing stays directional, hover and restoration still work.
   Select manual Sleeping during generation; completion must not wake Hya.
5. Switch models, cancel mid-answer, restart Hya, verify history/status labels,
   then test New/Clear/Delete and saved model selection.

For current v0.7.0 quick-chat tests, placement limitations, and previews, see QUICK_CHAT.md.

Desktop tool calling, permission dialogs, audit logging and v0.8 verification are documented in DESKTOP_TOOLS.md.
