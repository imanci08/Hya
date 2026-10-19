# Hya v0.8.2 — Orb Quick Chat and Docking

Run `python hya.py`. Double-click the normal companion to open compact chat,
or select **Chat with Hya** from its normal/edge context menu. Double-clicking
the peek surface also opens chat; its original first click still starts the
normal restore animation, paused while docked and resumed on close. The context
menu remembers a tucked edge without starting a restore. See DOCKING.md.

The default panel is 410 × 470 logical pixels, with a translucent rounded glass
surface, original animated orb character, selectable plain-text message bubbles, input,
Send, Stop, Expand, and Close. Enter sends; Shift+Enter adds a newline.
Drag the header to move it; the bottom-right grip resizes it. Expand opens the
full workspace (initially 720 × 800, bounded to the selected screen) with the existing conversation selector,
New/Clear/Delete, model selector, refresh and settings controls. Compact returns
to the small view. There is no redundant Options button in compact chat.
The two modes remember their own sizes during this session.

## Shared session and existing functionality

Both views are the **same ChatWindow instance**. Switching only changes layout,
size and placement; it never closes, cancels, reloads history, clears a draft,
recreates a client or issues another request. The same assistant label receives
all streamed chunks, including while switching. Closing the panel/workspace or
pressing Escape retains v0.6 behavior: cancel generation, mark partial history
cancelled, and hide chat. Hya remains running. Reopening retains conversation
and input. Stop cancels without closing. No inference/history schema changes
are needed; existing settings and history paths remain unchanged.

Finished assistant replies have Copy Response. Completed closed Markdown fences
(backticks or tildes) also produce Copy code buttons, preserving code literally,
including newlines. An unclosed streaming fence gets no code button until it is
closed and the response finishes. Partial replies on cancellation remain marked
and copyable. Clipboard operations happen only on an explicit button press.
Messages are plain text: no HTML, automatic links, code execution or tools.

The original expression controller and timer continue to drive the companion
and peek painter. AI Thinking respects manual Studio priority, including Sleeping.
The centered docked character uses the original painter, shared pose and clock;
the existing timer updates it, including expressions and color changes. No eyebrows
are added. Ollama transport, request streaming, cancellation, SQLite history,
settings, personality and appearance modules remain unchanged.

## Geometry, focus and Wayland

Placement uses the current peek output or normal character output and
`QScreen.availableGeometry()` in logical coordinates, including negative monitor
origins. Hidden surface coordinates are inferred from the existing physical
edge anchors/margins/panel inset; the exposed input region supplies a reference
near the visible artwork. The algorithm prefers above for Bottom, inward for
Left/Right, and above/below for normal mode, then clamps the rectangle to the
available desktop. This does not move, reparent or change the existing Layer
Shell surface. Workspace size is bounded to the selected screen.

Quick chat and workspace use a regular, frameless Qt window, independent of the
companion's always-on-top parent. Neither sets an always-on-top flag, global
input grab, Layer Shell keyboard interactivity, or focus-stealing timer.
Only explicit opening, and Expand/Compact actions request activation.
Streaming and automatic status updates never activate the window. Header movement
uses `startSystemMove()`; `QSizeGrip` supplies workspace resizing. X11 can also
use a QWidget movement fallback.

On KDE Wayland, regular toplevel positioning and true global normal-window
coordinates are controlled by the compositor. Size/clamping and target output
are requested, but **exact placement near Hya and final compositor clamping
cannot be guaranteed**. A cursor-based hint is used when normal-window global
coordinates appear unavailable. This limitation is deliberate: chat remains a
regular usable workspace without changing the working non-focusing Layer Shell
peek or globally applying Layer Shell to normal windows.
References: [Qt window positioning and native movement](https://doc.qt.io/qt-6/qwindow.html),
[available screen geometry](https://doc.qt.io/qt-6/qscreen.html#availableGeometry-prop).

## Files and compatibility

- `chat_window.py`: compact/full view state, controls, explicit focus and placement;
  retains the existing chat backend and session ownership.
- `chat_widgets.py`: header movement, original-painter avatar, geometry helpers,
  selectable message bubbles and literal fenced-code clipboard actions.
- `hya.py`: quick-chat entry point and the peek bridge's chat action.
- `peek.qml`: double-click chat callback only; anchors, layer, margins, exclusion,
  keyboard behavior, artwork and existing click handling remain unchanged.
- `hyal.py`: tiny compatibility import/launcher for pre-rename tests and tools.
  The supplied v0.6 tree had hya.py while tests still imported hyal; this restores
  compatibility without renaming the current application.
- `tests/test_quick_chat.py`: mocked-stream UI, clipboard, geometry and interaction
  regressions. All original tests are retained.
- `tools/render_chat_preview.py`: actual compact/workspace Qt screenshots using
  fake local model/data and no inference.

The verified pre-update backup is listed under Installation below. It contains
the original sources, tests, tools, documentation and previews. Existing
historical backups remain available for pixel tests.

## Verification

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m compileall -q hya.py hyal.py chat_window.py chat_widgets.py tests tools
QT_QPA_PLATFORM=offscreen python tools/render_chat_preview.py
```

New checks cover geometry for all edges, normal mode, negative origins and small
outputs; compact controls/focus and native header movement; actual double-click
routing on the installed QML surface; shared streaming through expansion and
contraction; drafts, persisted reply identity, cancellation and close/reopen;
clipboard copies, literal code fences, no stream-driven activation, reading older
messages during generation, and manual Sleeping while chatting from each edge.
All 76 v0.7.0 tests are retained; current docking verification is in DOCKING.md. The original screen-edge, startup, palette, artwork and
backend tests remain.

Offscreen screenshots: `previews/local-chat.png` and
`previews/chat-workspace.png`. These are UI previews with fake model responses.
A timed offscreen startup/peek/quick-chat launch passed. A real Wayland launch
aborted with status 134 before opening a window in this environment. Real Plasma
placement, decorations/compositing, focus, native drag/resize and live Ollama
inference have not been verified in this development session.

Remaining desktop checks:

1. Double-click normal and hidden Hya; check proximity, output selection, panel
   access, screen bounds and explicit input focus. Check both a negative-origin
   second monitor and fractional scaling if available.
2. Drag chat by its header and resize the workspace by its grip. Confirm ordinary
   apps can cover chat and typing elsewhere is not interrupted by streaming.
3. Generate a response, expand/compact repeatedly, and verify uninterrupted text,
   one response, unchanged draft and history. Stop/close/reopen and test Escape.
4. Copy text and fenced code. Scroll upward during generation and verify the view
   stays put. Select a model and edit settings in the expanded workspace.
5. Confirm all edge hover/restore behavior, character dragging, color controls,
   Expression Studio and manual Sleeping still work while inference runs.

## Installation

The tested staging build was applied to `/home/chandler/Downloads/Hya` after
reopening that directory as the writable workspace. All staged source files
were checked for completeness, the original live files matched the v0.6 staged
baseline, and all 76 tests passed before applying the 12 changed/new files.

The complete pre-update project backup (excluding historical backups and caches)
is `backups/v0.6-before-v0.7.0-20261018-215826/`, with a
`BACKUP_SHA256.json` integrity manifest. Existing historical backups were retained.
Per-user appearance/AI settings and conversation history were not copied,
replaced, migrated or deleted. Tests use isolated XDG config/data directories.

The v0.7.1 docking lifecycle and updated desktop verification checklist are documented in DOCKING.md.
