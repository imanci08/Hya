Hya v0.9.1 — Release Candidate Visual Polish


Release candidate changes
Chat’s adaptive Hya wordmark is 28% larger, the original docked character paints
at 25% larger scale, and the blue-purple pane is 17.6% less opaque. Existing
window sizes, layout slots, text/input opacity and desktop character are unchanged.
A small native KDE blur bridge requests rounded frosted glass on supported
compositors. See RELEASE_0.9.1.md for verification, build and rollback notes.

Standalone installation
See STANDALONE.md for building the native Arch package in an isolated directory,
install/update/removal commands, tray controls, opt-in Start on Login and optional
development-data import. Run installed Hya as hya or from KDE’s launcher;
python hya.py remains the editable development entry point. Installed data lives
in XDG hya directories; development retains the existing hyal directories.
Appearance > Orb Color preserves every saved preset and legacy setting key.
The chat Hya wordmark updates its subtle glass tint with the selected Orb Color.

First-run AI Setup (standalone packaging)
A friendly wizard checks the Ollama executable, local service, and compatible
chat models. It can use an existing model or offer an explicitly approved
download with size/disk estimates, progress and Cancel. Skip keeps Hya usable
without conversational AI. Reopen Set up local AI from Hya’s menu, or AI Setup
in expanded chat. Guided native installation currently supports Arch-based
systems via interactive pacman and sudo in Konsole/XTerm; other systems get
manual setup guidance. No models are bundled. See AI_SETUP.md.

v0.8.2: Tool JSON stays internal; action statuses are human-readable.
Compact chat has Expand and Close; settings remain in the expanded workspace.
Simple unambiguous app/folder/system-info requests can bypass Ollama inference
through the same validated permission broker. Disable this optional fast path
in Settings. Launcher acknowledgement no longer waits for GUI stderr to close.
See DESKTOP_SPEED.md for timing measurements, tests and manual KDE checks.

Smart Permissions retained from v0.8.1
Ordinary trusted installed graphical apps now launch without a confirmation
prompt. This includes standard system-installed Dolphin, KCalc, Kate and Firefox.
Terminal/admin apps, custom or unclassified launchers still require confirmation.
Unknown applications and executable paths are never treated as launch commands.
Turn automatic launching off under Expand > Settings when desired.

Open Home/Downloads/Documents or another ordinary user directory through the new
open_directory tool; this does not authorize searches or file contents. Filename
searches reuse explicitly authorized directory scopes across restarts. New scopes,
hidden/private directories and all browser searches still require permission.
Settings offers Forget approved search directories. File-content access remains
unimplemented, rather than being silently added to this release.
Every desktop operation remains in Action Log with automatic/confirmed status,
and launch_requested never claims a window was successfully opened. Character
artwork, colors, docking and chat appearance remain unchanged. See
SMART_PERMISSIONS.md for policy boundaries and desktop verification.

Application launching improvement
Ask “Open calculator,” “Open the file manager,” or “Open terminal.” Hya resolves
ordinary names against installed XDG applications and uses friendly names. If several apps match, choose from a short list.
Confirmation is then shown only when the app is not eligible for automatic launch.
There is no need to find desktop IDs, and no executable-path or shell fallback.
Missing applications are reported without launching a substitute. Permissions,
action logging, chat, animations and appearance are preserved. Restart Hya to
load this improvement. Details and tests: DESKTOP_TOOLS.md.

New in v0.8
Tool-capable local Ollama models can request a small allowlisted set of desktop
operations: list/open installed application IDs, read basic system information,
search filenames inside explicitly authorized directories, open browser web
searches, and draft copyable Bash text. No arbitrary commands or model-generated
code are executed. The existing character, docking, animations and glass styling
are unchanged. Models without advertised tool support retain ordinary chat and
show that direct desktop actions are unavailable.

Applications and browser searches always require Allow once in a clear permission
dialog. Every filename search requires explicit authorization for its exact
canonical directory and query; symlinks are skipped and file contents are not
read. Deny or close the dialog to refuse. Stop in chat or the permission dialog
cancels the remaining workflow; already-dispatched launches cannot be undone.
After denial, further protected actions are blocked for that user turn.
Expand > Action Log shows the private local record of attempts and outcomes.
Bash commands/scripts remain selectable, copyable text only, never run or saved
as scripts by Hya. Browser searches send only the explicitly approved query to
an external search provider through the default browser.

See DESKTOP_TOOLS.md for permission boundaries, APIs, logs, tests and required
KDE Wayland manual checks. The GIO launcher (usually in the distribution GLib
package) is used with fixed argument lists; there are no new pip dependencies.
Backup before editing: backups/v0.7.1-before-v0.8-20261018-225300/.
Launch as usual with python hya.py; restart a running Hya to load v0.8.

Retained from v0.7.1
Opening chat transfers Hya into a centered animated character area near the top
of the chat window. The desktop character becomes transparent/input-free, and
any existing Layer Shell peek is temporarily hidden. Closing chat returns the
same desktop/edge presentation, position, appearance, and continuing expression.
The original painter, pose, animation clock and 33 ms timer are reused.

Expanded Hya is 114 px (about 80% of normal); compact mode uses 92 px to keep the
conversation usable. The expanded workspace defaults to 720 x 800, bounded to the
selected screen. Expand/Compact keeps Hya docked and retains generation, draft,
conversation, and reading position. Right-click docked Hya for Expression Studio,
Appearance and Quit. The docked artwork cannot drag the desktop companion.
No static avatar, second animation engine, new AI features, or eyebrows are added.

Backup of v0.7.0: backups/v0.7.0-before-v0.7.1-20261018-221806/.
See DOCKING.md for lifecycle details, automated checks and remaining KDE Wayland
visual verification. Launch as before with python hya.py; restart a running Hya
to load this update. Existing settings and local conversation history are intact.

Retained from v0.7.0
Double-click Hya for a compact, rounded blue-purple quick-chat panel with his
animated orb character, selectable messages, Send/Stop, Expand and Close.
Expand opens the full movable/resizable workspace; Compact returns to quick
chat. Both views share the exact same live session, input draft, and streaming
request. The expanded workspace contains model/history/settings controls. Completed
assistant messages offer Copy Response and Copy code buttons for closed fenced
code blocks. Chat has no always-on-top flag; only explicit opening/view actions
request input focus. Closing cancels generation and hides chat, leaving Hya alive.

Placement uses the character/peek output and available logical screen geometry.
Regular Wayland window placement is still compositor-controlled; near-character
coordinates are best-effort hints. Peek anchors, artwork, offsets and clipping
are preserved. Double-clicking an edge peek also opens quick chat while the
original click-to-restore animation is paused while docked and resumes on close. The existing edge context menu
opens chat and remembers the tucked edge for restoration when chat closes.

See QUICK_CHAT.md for implementation, tests, previews and remaining Plasma
checks. Backup of the v0.6 source tree: backups/v0.6-before-v0.7.0-20261018-215826/. The current launcher is
hya.py; a small hyal.py compatibility launcher/import preserves older tools.
No eyebrows or new AI engine features are introduced in this release.

Retained from v0.6
Double-click Hya, or choose right-click > Chat with Hya even while tucked away.
Select an installed Ollama model, send with Enter (Shift+Enter for a newline),
and receive streamed local replies. Stop Generating or close chat to cancel.
New, Clear and Delete manage persistent local conversations. Models and request
settings are configurable; no models or system packages are auto-installed.
Existing Expression Studio and all character/edge behavior are preserved.
Thinking follows AI activity without overriding manual expressions or Sleeping.

See LOCAL_AI.md for EndeavourOS/general Linux setup, XDG data paths, privacy,
architecture, tests and the remaining Plasma/live-model verification checklist.
The editable personality is system_prompt.txt. Keep the new AI modules and this
prompt beside hya.py when packaging. QtNetwork and sqlite3 are already supplied
by PySide6/Python. Backup of the working prior version: backups/v0.5.2/.
Previews (fake model/data, actual Qt widgets): previews/local-chat.png and
previews/chat-workspace.png.

Launch from this directory:
    python hya.py

Dependencies: Python, PySide6 (including QtQuick/QML), and, on Wayland,
layer-shell-qt with org.kde.layershell 1.0. Use distribution packages so
PySide6 and the Layer Shell plugin use compatible Qt libraries.
Keep peek.qml, panel_boundary.py, appearance.py and personality.py beside
hya.py. QtDBus ships with the
system PySide6 package; no additional packages are required.
Do not globally set QT_WAYLAND_SHELL_INTEGRATION=layer-shell: normal mode
needs regular windows.

Startup and bottom-right placement
Hya launches directly into the fully tucked bottom peek pose. The normal
widget is never shown first, so there is no normal-mode flash or startup
retreat animation. Click to emerge and restore the upright companion.
The initial normal placement hint is (80,100) relative to the selected
output origin; on Wayland the compositor determines that first placement.

Bottom now uses Bottom+Right Layer Shell anchors, with a default horizontal
inset of 24 logical pixels from the physical screen corner. To shift farther
left, for example:
    python hya.py --bottom-horizontal-inset 80
This option is per launch and independent of --bottom-panel-inset, which
controls vertical panel-boundary clipping. Horizontal inset is clamped to
the output width; negative CLI values are rejected. It does not assume a
screen resolution or the exact position of a Wi-Fi icon. The entire panel
strip remains transparent and excluded from pointer input, keeping tray
icons and the clock usable. Left and Right anchoring/offsets are unchanged.

Remembering the normal position
Before hiding, Hya snapshots the normal widget's latest reported position.
Changing edges while hidden never overwrites it. The Hide at Screen Edge
submenu remains available in hidden mode, so edges can be changed directly.
After a normal drag, the next hide snapshots the updated normal position.
X11 restores the saved coordinates directly, with the upright original size.
Position persistence across application restarts is not enabled.

On Wayland, saved coordinates alone cannot reliably restore a remapped
normal toplevel. An already visible normal window is therefore kept mapped
at its compositor-managed position while hiding: its backing store is
cleared to transparent, and a nonempty input region completely outside its
bounds makes it pointer/touch-transparent. This retains the existing xdg
surface and its actual placement even if Qt lacks true global coordinates.
Restore reveals that same surface without move(), hide()/show() or native
window recreation. The separate Layer Shell window still supplies the peek.
The first restore after quiet startup has no previous mapped position to
retain; its initial move is only a hint. KWin still controls placement,
monitor-removal relocation and any independent compositor movement. Exact
first-time normal placement is not guaranteed, and the retained-position
behavior needs verification on the actual Plasma desktop.

Qt's QWindow mask API is an input hint; an empty mask resets full input, so
parking uses a nonempty off-surface region instead. Source references:
https://doc.qt.io/qt-6/qwindow.html#setMask
https://doc.qt.io/qt-6/qwindow.html#startSystemMove
https://codebrowser.dev/qt6/qtbase/src/plugins/platforms/wayland/qwaylandwindow.cpp.html

Controls
Drag with the left mouse button; double-click to chat locally with Hya.
Right-click > Hide at Screen Edge > Bottom / Left / Right.
Hover over the visible character to emerge farther; leave to retreat.
Left-click to animate out and restore the original upright normal window.
Right-click the peek surface for Chat with Hya, Come out, or Quit Hya.

Expression Studio
Right-click > Expression Studio offers Look Around, Thinking, Sleeping,
Sniffle, Sneeze, and Wake Up / Reset. Each action plays on the actual
companion immediately, including when natural Idle Animations is disabled.
Look Around visits left, right and up before centering. Thinking lasts
4.5 seconds. Sleeping yawns, closes its eyes and remains asleep until
Wake Up / Reset or another explicit expression replaces it. Sniffle is
standalone; Sneeze includes anticipation, squeeze/recoil and rebound.
Wake Up / Reset immediately cancels the active sequence and restores the
ordinary idle face, breathing and blinking.

Manual previews take priority over natural random behavior, menu dismissal
and incidental hover/mouse events. Normal dragging, menus, edge hovering
and click-to-restore remain usable while a preview is running. Natural
sleep continues to wake on interaction; manual sleep is reset explicitly.

In edge modes, a small modeless Expression Studio window opens automatically
with a live, upright full-character preview. The anchored companion stays
at its existing edge and also displays the expression in its orientation.
Open Preview Window in the submenu can show it in normal mode too. Closing
this preview does not reset an expression. No extra animation timer is used.

Developer API: Hya.play_expression(name, force=True, source='manual',
priority=None). The pure-Python ExpressionController handles sequence
ownership, priorities, interruptibility, persistent states and transitions.
See EXPRESSION_STUDIO.md for names, timing, API details and extension examples.

Rename compatibility
The visible character name is Hya. Launch with python hya.py; hyal.py remains
a compatibility entry point. QML module identifiers, legacy Hyal/Personality
imports, and the
existing ~/.config/hyal/appearance.ini path are preserved. Hya is the
preferred class import. No settings migration or manual copying is needed.

Appearance and persistence
Right-click > Appearance > Orb Color offers Sapphire, Amethyst, Rose
Quartz, Emerald, Ruby, Amber, Arctic and Midnight. Custom Color opens Qt's
color picker with live preview; OK saves it and Cancel restores the previous
selection. Reset to Default resets the orb color to Sapphire only.
Gradients, halo, rings and diamond share a cached color palette. Source
alpha, glass depth, translucent highlights and white facial features are
preserved. Bright custom colors keep a darker core so white eyes remain
legible, even with a white custom orb. Neutral Sapphire is pixel-for-pixel equivalent to v0.4.2.
Changes apply immediately to normal and edge surfaces; no restart is needed.
Appearance controls pause while the picker is open so preview colors cannot
be accidentally committed by another settings action.

Appearance > Idle Animations is a persisted on/off toggle for natural
activity. Disabling it cancels natural expressions; manual Studio previews
remain available and finish normally or can be reset. Breathing and
ordinary blinking continue.
Settings are written with Qt QSettings to:
    $XDG_CONFIG_HOME/hyal/appearance.ini
Usually this is ~/.config/hyal/appearance.ini. Missing/invalid color settings
fall back to Sapphire. No settings file is created until a setting is saved.
Qt's INI saving uses atomic replacement; a save failure is reported on stderr
while the chosen appearance remains usable for the current session.

Living personality
The original 33ms timer drives one shared expression state machine and one
immutable pose snapshot for both Python and Qt Quick painting. No extra
animation timers or image assets are added. Optional Ollama chat runs locally;
no new Python dependencies are required.
Palette calculations are cached; animation frames perform no config I/O.
Only one expression owns the face at a time:
- Curious: gently looks left/right/up, holds, and eases back to center.
- Thinking: upward gaze and a tiny thoughtful mouth, with a brief gaze pause.
- Sleepy: after three minutes without interacting with Hya, yawns for two
  seconds, closes his eyes over 2.5 seconds, then sleeps peacefully.
- Sniffle: narrows his eyes, scrunches his face and makes a small preparation.
- Sneeze: squeezes eyes shut, compresses for 0.45 seconds, then rebounds for
  1.1 seconds with a surprised face before returning to normal.

Idle events use randomized 20–50 second gaps. Curious directions do not
repeat consecutively and thinking does not repeat back-to-back. Sneezes
have only a 2% chance at eligible idle opportunities and a five-minute
cooldown, including an initial five-minute grace period. Sleep/expressions
that close the eyes suppress ordinary blinking; curious/thinking keep it.
Hovering, moving over Hya, clicking, opening menus, dragging or restoring
interrupts natural expressions and gently wakes him. Manual Studio previews
are protected from these incidental events until completion or reset. Menus, color selection and
edge transitions defer new idle events. Repeated wake input does not restart
the wake transition. Inactivity means no interaction with Hya, not global
keyboard/mouse inactivity: Hya does not monitor other applications.

All expression offsets, facial changes and squash/rebound transforms are
inside the verified local character rotation. Edge offsets, panel clipping,
anchors, margins and directional breathing stay as in the user-verified
v0.4.2 implementation. Both active surfaces use the same palette and pose.

Visual behavior
All modes paint the original orb, face, rings, glow and floating diamond.
There is no replacement illustration, shrinking, or opacity fade.
Bottom stays upright. Its resting depth follows the supplied screenshot:
the upper orb head, eyes and floating diamond remain visible. Hover
reveals more of the face. Right rotates counterclockwise so the diamond
points left, toward the desktop. Left rotates clockwise so the diamond
points right. Rotation uses the resting orb center (71, 78). The
original painter animates in local coordinates before rotation, so the
body, face, rings and diamond bob vertically in Normal/Bottom and
horizontally in Left/Right. Body breathing retains amplitude 2.5 logical
pixels and angular speed 1.8; the diamond retains its own original rhythm.
The artwork, angle choices, offsets, clipping and neutral positions are
unchanged from v0.4.1.
User-triggered hiding and restoring use a smooth 0.65-second
translation/rotation. Quiet startup skips the initial hide animation.
Selecting an edge resets stale hover state and automatically completes the
retreat without pointer input. Mapping/enter/leave events cannot extend
Hya during this transition. After tucking away, fresh pointer movement
arms hover; stationary cursor reports do not undo the initial retreat.
Leaving the surface eases him back into the idle position. The hidden
normal QWidget cannot send hover commands to the separate Wayland surface.
The neutral artwork, dragging and original menu actions remain unchanged;
Appearance adds the new color and personality controls.

Layer Shell and geometry
Wayland uses the existing separate transparent Qt Quick surface, selected
on the normal window's output (or the startup output). Bottom anchors
Bottom+Right and clamps its right margin; sides retain Top+Left/Right and
their original clamped top margin.
All positions are logical screen coordinates, including negative monitor
origins. exclusionZone=-1 anchors to the physical output, ignoring work-area
reservations. KeyboardInteractivityNone and activateOnShow=false preserve
keyboard focus. No desktop space is reserved.

Panel-boundary fallback (deliberate, independent of stacking)
The upstream Plasma PanelView requests LayerTop. Ordering inside a shared
Layer Shell layer is undefined, while LayerBottom can put a companion behind
ordinary application windows. Simply changing layers does not establish the
requested panel behavior. Hya retains LayerOverlay and explicitly clips.
For Bottom, the physical-bottom-anchored window is 142 + panelInset pixels
high. Only the upper 142 pixels contain artwork and pointer handlers. The
panelInset strip below is transparent and excluded from the input mask,
including during hide/hover/restore. Hya is thus clipped at the panel top,
reproducing concealment without drawing over the panel or blocking clicks.
Side surfaces remain 142x142. This is a clipping effect, not verified native
compositor occlusion.

Panel discovery reads Plasma's evaluateScript D-Bus API without changing
any configuration. screenForConnector maps the selected Qt connector to
Plasma's output ID. Bottom panels are selected by output and horizontal
coverage at Hya's center. Their live thickness determines the inset.
The initial query has a 500ms timeout before mapping; subsequent queries
run asynchronously every two seconds while Bottom mode is active. Valid
cached data survives a temporary read failure. Screen geometry changes
update margins. Removing the output restores normal mode.

Limits and override
The scripting API reports panel thickness, not floating-theme padding or
an autohiding panel's live position. Automatic alignment targets a fixed,
nonfloating taskbar like the supplied reference. Floating or autohiding
panels may require an explicit inset measured from the physical bottom to
the desired clipping boundary. If scripting/session D-Bus is unavailable,
a diagnostic is printed and the physical-bottom fallback remains usable.
For example, to set a 40 logical-pixel boundary explicitly:
    python hya.py --bottom-panel-inset 40
Use 0 for physical-edge clipping with no panel. The override does not change
the panel, reserve space, or use available desktop geometry. It is clamped
to the current output height and applies only to Bottom mode.

Sources inspected for layer behavior and panel API:
https://github.com/KDE/plasma-workspace/blob/master/shell/panelview.cpp
https://github.com/KDE/plasma-workspace/blob/master/shell/scripting/panel.h
https://github.com/KDE/plasma-workspace/blob/master/shell/scripting/scriptengine.cpp
https://wayland.app/protocols/wlr-layer-shell-unstable-v1

Restore reuses an existing mapped Wayland normal window in place; the
compositor controls first-time placement and relocation as described above. X11 uses the same painter and animations with a
positioned QWidget instead of Layer Shell. QML load failure leaves normal
mode visible. Failure to expose the edge surface restores normal mode with
an error after 1.5 seconds.

Backups
backups/v0.5.1/ preserves the working Expression Studio release before
the startup, bottom-right placement and restoration changes.
backups/v0.5/ preserves the working character-polish release before
Expression Studio and the user-facing rename.
backups/v0.4.2/ preserves the user-verified implementation, settings-free
source, QML, panel helper, README, tests and preview tool before v0.5.
backups/v0.4.1/ preserves source, QML, panel helper, README, tests and preview
tool before the v0.4.2 animation fixes.
backups/v0.4/ preserves the working version before these fixes.
backups/v0.3/ contains the preserved working v0.3 source, QML, README, tests.
backups/v0.4-eyes-only/ preserves the superseded eyes-only implementation.
The original v0.2 backups are also retained.

Verification
    python -m py_compile hya.py panel_boundary.py appearance.py personality.py tests/*.py tools/*.py
    QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
    QT_QPA_PLATFORM=offscreen python tools/render_previews.py
    QT_QPA_PLATFORM=offscreen python tools/render_personality_previews.py
    QT_QPA_PLATFORM=offscreen python tools/render_expression_studio.py

Tests preserve the original normal painter and compare full transformed
character images at idle/hover/blink times. Additional rendered-pixel checks
locate the inward diamond and both eyes, rather than checking angle values
alone. The actual installed QML module is exercised through all three edge
lifecycles. Captured Qt Quick frames verify the panel strip stays transparent
and click-through, including when the inset changes. Tests also cover
fallback placement, negative monitor origins, panel selection, execution of
the read-only discovery script, and invalid/denied D-Bus replies.
v0.4.2 adds tests for automatic retreat on all edges without a manual leave
command, stale/synthetic hover events on Wayland and the X11 fallback,
real Qt Quick mouse movement/leave handling, and rendered-pixel measurements
of body/face and diamond motion. Face pixels travel 5px peak-to-peak on the
expected axis, matching the existing 2.5px breathing amplitude. Neutral
rendered images also match the v0.4.1 backup across edges and transitions.

previews/edge-peeks.png contains all three positions at idle and hover with
a simulated 40px taskbar for Bottom. Individual transparent PNGs are beside
it. These are raster previews, not screenshots of native Plasma occlusion.

v0.5 tests also cover per-user INI persistence through a fresh Python process,
preset/custom/reset/idle-toggle behavior, picker preview/cancel/accept,
malformed settings, palette depth/alpha/white faces, state transitions,
random scheduling, sleep/wake timing, sneeze rarity/cooldown and blink
exclusivity. Rendered expression images are checked on all three edges;
the actual installed QML surface is captured to check live recoloring,
sleeping and waking. The original v0.5 release passed 33 automated tests and syntax checks. Neutral Sapphire images are compared against the
v0.4.2 backup at multiple breathing/blink times, at idle and hover.

New previews (generated from the actual QPainter, not external illustrations):
- previews/crystal-colors.png — all eight presets.
- previews/facial-expressions.png — neutral, gaze directions, thinking,
  yawn, doze, sleep, sniffle, sneeze and surprised rebound.
- previews/living-orientations.png — expressions in normal and all edge modes.
- Individual transparent frames are in previews/colors/ and previews/expressions/.
The colored preview canvas is not part of Hya's transparent window.
A 500-frame software QImage smoke benchmark measured approximately 1ms per
frame for both v0.4.2 and v0.5, including an active sneeze. This is not a
measurement of real Plasma compositor CPU usage.

v0.5.1 tests add real menu-trigger rendering, menu-dismissal regression,
manual/natural sleep distinctions, immediate reset, idle-disabled previews,
priority arbitration, forced interruptions, noninterruptible sneeze impact,
sequence timing, and explicit previews on all three edge surfaces. The
studio preview changes rendered frames without changing anchored surface
geometry or input masks. Existing palette, persistence and geometry tests
remain in the full suite. The v0.5.1 release passed 45 automated tests.
EXPRESSION_STUDIO.md documents the public API.
previews/expression-studio.png shows the actual Qt menu and live preview
window captured offscreen; it is not a Plasma desktop screenshot.

v0.5.2 adds tests for the actual startup factory and absence of normal Show
events, a fully tucked first frame, real QML Bottom+Right anchors, configurable
margins with negative output origins, tray-strip transparency/input masking,
startup click restoration, repeated edge switches, stale-surface callbacks,
updated drag positions, X11 restoration, and panel detection at the new
bottom-right location. Wayland lifecycle tests verify the normal surface
stays mapped with a blank frame and no effective input region, then restores
without move/remap even when Qt reports incorrect global coordinates.
Studio Reset/Close buttons are also tested through native Qt window input
while their normal parent is parked. All 54 tests and syntax checks passed.

Remaining desktop verification
Actual Qt Wayland startup remains blocked in this execution environment.
The user-verified artwork, Expression Studio, appearance configuration,
rotations, side anchors and breathing are preserved. Tests exercise the
installed QML module offscreen, not a real Plasma compositor. On KDE:
- Launch: only the tucked bottom-right peek should appear, with no orb flash
  elsewhere. Check both default and customized --bottom-horizontal-inset.
- Click the peek: verify upright restoration. After the first normal placement,
  drag Hya, hide him, and restore repeatedly: the same position should return.
- While hidden, click/type in a window underneath the former normal position;
  check there is no invisible input blocker or residual artwork/background.
- Switch Bottom/Left/Right directly while hidden, then restore: the saved normal
  location must survive all switches. Confirm side positioning is unchanged.
- Check tray/Wi-Fi/clock clicks, hover/retraction, panel clipping, and fractional
  scaling on each monitor, including monitors with negative desktop origins.
- Remove the selected display or change layout: confirm KWin relocates/reveals
  the normal window sensibly. First placement and compositor relocations are
  subject to KWin policy, not an application coordinate guarantee.
- Recheck all Studio actions, the live preview, saved colors and idle toggle.
