# Hya v0.7.1 — Animated Character Docking

Launch `python hya.py`. Open chat by double-clicking normal or edge Hya, or through
Chat with Hya in the desktop context menu. Chat now supplies the character:
centered above its controls, upright, fully animated, with the original artwork.
The desktop artwork is cleared and pointer-transparent; the original edge surface
is temporarily hidden. Closing through Close, Escape, or the window manager
restores the desktop presentation. Chat closure still cancels generation and
persists incomplete replies with their existing cancelled status.

The handoff is immediate; no second Hya flies across the desktop or fades over
the docked character. Expanded mode uses a 114 × 114 area (80.3% of the original
142 × 142 canvas). Compact mode uses 92 × 92 (64.8%) and a 72 px input cap, retaining
the 410 × 470 default panel. Expanded workspace defaults to 720 × 800 and remains
resizable with its existing header movement/size grip and available-screen bound.

## One character, multiple presentation surfaces

`Hya` already owns the necessary shared state: ExpressionController, AIActivity,
current immutable pose, appearance palette, original monotonic start time, and
33 ms animation timer. No new state machine, character assets, animation timer,
thread, dependency, configuration file or history schema is introduced.

`DockedCharacter` in `chat_widgets.py` calls the exact `paint_hyal()` function,
scaled uniformly. It reads the owner's live palette, pose and original clock.
`frame_ready`, emitted by the existing timer and explicit expression triggers,
requests repainting. Breathing, blinking, diamond motion, rings, thinking,
sleeping, sniffle/sneeze and all Studio overrides therefore share their existing
timing. Color changes repaint immediately. Docked artwork is upright; the
unchanged edge painter resumes the chosen orientation on returning to the edge.

Right-click docked Hya to access Expression Studio, Appearance, and Quit Hya.
Open Preview Window uses the already-visible docked character while docked,
instead of adding another illustrated preview. A Studio window already open
before docking is hidden during chat and restored afterward. Menu interaction
uses the same idle/manual priority behavior. The docked widget has no desktop
move, hide-at-edge, or click-to-restore handlers; drag chat using its header.

## Desktop preservation and transition ordering

`dock_to_chat()` takes a presentation snapshot and runs in the chat's show event,
before its first painted frame. It does not move or unmap a mapped normal
Wayland window: that surface is cleared to transparent and its native input
mask is moved outside the window, retaining KWin's actual placement. The existing
edge window is hidden without deleting its QML engine, anchors or bridge. A
quiet-start normal surface remains unmapped. The visible Studio preview is also
hidden during chat. No saved normal position is overwritten.

`undock_from_chat()` runs from the hide event after the chat painter becomes
invisible. It restores the original widget/native input masks, mouse attributes,
same edge surface, and prior Studio visibility. Normal mode does not move or
remap its retained surface. Bottom/Left/Right preferences, margins, original
artwork, clipping, saved position and color remain intact.

Edge hover depth and retreat/restore progress are paused while docked. The
transition clock is shifted by docking duration on close, so an interrupted
retreat/restore resumes from the same progress. Hiding a peek for docking is not
an exposure failure: the exposure watchdog skips it and is rearmed on undock.
Screen-removal restoration is deferred until chat closes, when normal mode is
the safe fallback. Panel-boundary updates are reapplied on return.

Expressions continue while docked; finite expressions can finish and natural idle
behavior continues. Their clocks are not rewound. Manual Sleeping survives AI
completion/cancellation. Chat creation occurs before docking; if opening fails
after docking, the failure path hides chat and restores the desktop. Application
shutdown marks the terminal close path, hides chat, cancels requests and stops
the companion timer without briefly revealing desktop Hya.

## Chat preservation

Compact and expanded mode remain the same chat object and do not hide/unmap
chat or trigger undocking. No client, assistant message, conversation or input
widget is recreated. The active request, streaming text, input draft and message
history are retained. A layout-change guard retains the reading scroll offset
(clamped if the resized content is shorter) and preserves follow-tail behavior.
User-selected manual expressions still outrank AI Thinking.

## Changes

- `hya.py`: version, shared frame notification, presentation snapshot/restore,
  parked desktop painter, suspended edge updates and watchdog, Studio routing,
  chat-failure recovery and terminal shutdown handling.
- `chat_widgets.py`: animated shared-painter DockedCharacter replaces static avatar;
  centered rendering and safe expression/appearance context menu.
- `chat_window.py`: dedicated character area, 720 × 800 workspace default,
  compact sizing, show/hide docking lifecycle, scroll retention and shutdown.
- `tests/test_docking.py`: lifecycle, rendering, input, stream and geometry tests.
- `tools/render_chat_preview.py`: actual animated owner in both UI previews.
- README, QUICK_CHAT.md and this document describe the new behavior.

Ollama transport, SQLite store, AI settings, system prompt, personality controller,
appearance implementation, Layer Shell QML, anchors and painter artwork are
unchanged. No eyebrows are implemented. User settings and conversation files
are neither migrated nor replaced.

Backup before edits:
`backups/v0.7.0-before-v0.7.1-20261018-221806/`.

## Verification

Run from the project directory:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m compileall -q hya.py hyal.py chat_window.py chat_widgets.py tests tools
QT_QPA_PLATFORM=offscreen python tools/render_chat_preview.py
```

All 88 tests passed, including the original 76 and twelve new docking tests.
Syntax compilation and the timed offscreen application smoke test passed.
The docking tests additionally cover:
repeated normal docking with the same native surface/position and blank pixels;
all three edge surfaces and X11 fallback masks; transition-clock pausing;
pixel equality with the original painter for multiple expressions and a custom
preset; animation ticks during mocked inference; manual Sleeping; Studio preview
routing and drag isolation; opening/creation failures; unavailable Ollama after
quiet startup; native WM close; screen-removal fallback; application shutdown;
centering/resizing/bounds; and reading-position retention through view switches.

A timed offscreen smoke test exercises quiet startup, docking, expansion,
undocking, reopening and shutdown. Updated UI previews use the actual painter
and fake conversation/model data: `previews/local-chat.png` and
`previews/chat-workspace.png`.

An actual Wayland launch again aborted with exit 134 before opening a window
in this execution environment. Automated tests exercise the installed Layer
Shell QML module offscreen, not a live Plasma compositor. Real KWin input-mask
behavior, compositor frame ordering, perceived flash-free handoff, focus,
monitor changes and retained physical placement require desktop verification.
Live Ollama inference was not exercised in this task; HTTP responses are mocked.

Manual KDE Plasma Wayland checklist:

1. Drag normal Hya somewhere distinctive. Double-click, confirm only the docked
   character is visible, then close chat and verify the exact normal location.
2. Repeat from Bottom/Left/Right, including quiet startup. Verify the peek is
   absent during chat and returns with the same edge, depth, orientation and
   panel clipping; hover and click-to-restore must still work afterward.
3. Expand/Compact repeatedly during a streamed response. Verify continuous
   breathing/blinking/Thinking, stable draft/history and reading position.
4. Right-click docked Hya for every Studio expression and a color change. Check
   Sleeping remains selected through response completion. Dragging the embedded
   character must not move the desktop companion.
5. Test Close, Escape, KDE's window-close control, minimizing/restoring, monitor
   removal and application quit while docked. Confirm no duplicate, stranded or
   briefly flashed character. Check fractional scaling and workspace resizing.
