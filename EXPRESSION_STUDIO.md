# Hya Expression Studio API

Use the GUI entry point to trigger and display an expression:

```python
hya.play_expression('look_around')
hya.play_expression('thinking')
hya.play_expression('sleeping')
hya.play_expression('sniffle')
hya.play_expression('sneeze')
hya.play_expression('reset')
```

`Hya.play_expression(name, force=True, *, source='manual', priority=None)` returns `True` when accepted, `False` when a priority or interruptibility rule rejects it. Unknown names, unknown sources without an explicit priority, and invalid priorities raise `ValueError` before replacing the current expression. Menu labels such as `Look Around`, `Sleeping`, and `Wake Up / Reset` are also accepted; snake-case identifiers are recommended for integrations.

This entry point updates the shared pose immediately, schedules repainting of the companion and Layer Shell surface, and lets the existing 33ms timer animate subsequent frames. Manual requests made in an edge mode also open a modeless, upright live preview. Neither this preview nor an expression changes the edge anchors, clipping, offsets, input mask, appearance settings, or hover state. The companion continues to display the expression in its current orientation.

## Controller and ownership

`personality.py` contains the pure-Python `ExpressionController`. `hya.personality` is its shared instance. `Personality` remains an alias for old callers; `Hya` and the existing `Hyal` class import both remain available from `hyal.py`. The original filenames, `paint_hyal`, QML import `Hyal 1.0`, and `hyal/appearance.ini` configuration path remain compatible.

The controller exposes the same `play_expression()` API, plus an optional `now=` argument for deterministic tests. `advance(now)` processes transitions and returns an immutable `Pose`; `sample(now)` samples the current stage without processing transitions. The GUI owns the clock/timer and stores one pose snapshot used by the QWidget, Qt Quick painted item, and studio preview. A standalone controller must be advanced by its host; changing its state alone does not repaint a widget. Prefer the Hya GUI entry point in application code.

The old `start(stage, now)` method is retained only for raw-stage sampling tools and compatibility. It bypasses expression ownership and should not be used for new integrations.

## Sequences and durations

| Public name | Stages | Duration / ending |
| --- | --- | --- |
| `look_around` | left → right → up → center, smooth interpolation and holds | 5.2s → neutral |
| `thinking` | upward gaze, thoughtful mouth, hold, ease out | 4.5s → neutral |
| `sleeping` | yawning → dozing → sleeping | 2s + 2.5s → indefinite sleep |
| `sniffle` | sniffle → sniffle_out | 0.9s + 0.45s → neutral; does not sneeze |
| `sneeze` | sniffle → sneeze → rebound | 0.9s + 0.45s + 1.1s → neutral |
| `reset` | cancel current sequence and clear ownership | immediate ordinary idle face |
| `curious` | original randomized single glance | 3.8s → neutral; used by natural idle |

`STAGES` maps raw stage names to immutable `StageSpec(duration, interruptible)` definitions. `None` duration means a long-lived stage. `EXPRESSIONS` maps public names to `ExpressionSpec(stages, priority=100, persistent=False)` definitions. Sleeping is explicitly marked persistent. Finite sequences clear ownership and schedule a fresh randomized idle interval after completion; they never resume an older, interrupted expression.

## Priorities and interruption

| Trigger source | Default priority |
| --- | --- |
| `idle` | 10 |
| `interaction` | 20 |
| `desktop` | 30 |
| `ai` | 50 |
| `manual` | expression definition's priority, normally 100 |

Higher numbers win. With `force=False`, a request must have **strictly higher** priority than the active expression and the current stage must be interruptible. Equal-priority requests do not restart an animation. The 0.45s sneeze-impact stage is noninterruptible; anticipation and rebound are interruptible. `force=True` deliberately overrides both restrictions. An explicit nonnegative integer `priority=` can customize a trigger source; a custom source name requires such a priority.

Natural randomized glances, thinking, rare sneezes and natural sleep all use `play_expression(..., force=False, source='idle')`. Incidental menu cleanup, mouse movement, hover and held buttons call `interact()` at interaction priority. These events cannot erase a manual preview or an AI reaction. Natural sleep still wakes on interaction; **manually requested sleep stays asleep until Reset or a replacement explicit request**. Closing the preview window does not cancel it. Ordinary edge hovering, dragging and click-to-restore remain functional while a manual sequence owns the face.

The Idle Animations appearance setting controls natural scheduling. It cancels natural expressions when disabled, but explicit previews still work and keep their ownership. Reset does not re-enable the user's idle setting or modify their color. Forced manual sneezes bypass the natural rarity gate, then update the same natural sneeze cooldown.

## Future AI and desktop triggers

Use non-forced requests for background reactions so a manual preview takes precedence:

```python
hya.play_expression('thinking', force=False, source='ai')
hya.play_expression('look_around', force=False, source='desktop')
```

Call GUI methods only on the Qt GUI thread. A worker should emit a Qt signal, connected with `Qt.QueuedConnection` to a GUI-thread `QObject` slot that calls this API with the intended source/force options. Do not manipulate QWidget/QQuick objects directly from an AI worker. There are no AI calls or desktop-monitoring hooks in this release; these are supported trigger labels for later integrations.

## Adding an expression

1. Add a named raw stage to `STAGES`, including duration and interruptibility. Add its procedural `Pose` sampling branch in `sample()`; existing facial styles and squash/rebound properties can be reused.
2. Add an `ExpressionSpec` listing the stages in order. Mark an indefinite final stage as persistent. Finite final stages return to neutral automatically.
3. Add a menu label in `Hya.add_expression_menu()` if a permanent studio action is wanted. The action must call `Hya.play_expression()`.
4. Add deterministic clock tests for its sequence and interruption behavior, plus rendered-frame tests in normal and all edge orientations. Keep transformation changes inside the existing local-coordinate painter.

Natural random scheduling is intentionally separate from manual menu registration: a new studio expression does not automatically become an idle behavior.

## Verification limits

The test suite triggers real QAction callbacks, exercises actual `QMenu.exec()` dismissal, captures changed QWidget/preview frames, and runs all studio sequences against the installed Layer Shell QML module in offscreen mode. The hidden surface geometry and mask are compared before and after each sequence. Real Plasma Wayland focus, popup placement and preview-window placement still need desktop verification because this execution environment cannot start Qt on its Wayland socket.


## Startup and position integration (v0.5.2)

`create_companion(bottom_panel_inset=None, bottom_horizontal_inset=24)` is the application startup factory. It calls `Hya.start_hidden()` without first showing the normal widget. Studio actions remain available from the tucked bottom-right surface and automatically open the same live preview.

`Hya.hide_at_edge(side, *, animate=True, screen=None)` also accepts a different edge while already hidden. Only the initial normal-to-hidden transition snapshots the normal position. Startup uses `animate=False` so the first mapped peek frame is already fully tucked. User menu actions keep the existing retreat animation.

An established normal Wayland window remains mapped but transparent and effectively input-free while hiding. `isVisible()` can therefore be true while the companion is visually hidden; use `hidden_at_edge` for application behavior. Do not hide/remap that parked normal window in an integration: this would give up the compositor placement being preserved. The actual Layer Shell surface and Expression Studio preview continue to share the controller's pose. Restoration after initial startup is the first normal map and remains subject to KWin placement policy.
