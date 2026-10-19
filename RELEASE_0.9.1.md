# Hya 0.9.1 — release candidate visual polish

The user verified v0.9.0 on real KDE Plasma Wayland. This candidate preserves its
window sizes, layouts, character design, desktop scale and application features.

## Changes

- The cached adaptive Hya wordmark renders at 32 px instead of 25 px (+28%), with
  its original top/left ink anchor, palette tint, translucency and restrained glow.
  Header layout metrics remain 25 px, so its height and control positions do not
  move. A small transparent overflow surface prevents the enlarged “y” descender
  from being cut off by the unchanged header. It does not receive mouse input.
- Chat's original animated renderer is painted at +25% scale: compact canvas
  115 × 115 instead of 92 × 92; expanded canvas approximately 142 × 142 instead
  of 114 × 114. The original layout slots, center, window sizes and desktop
  character remain unchanged. The sibling paint surface permits safe transparent
  overflow into existing space without moving messages/status/controls. There
  is still one animation/state controller and one character renderer.
- Main glass gradient alpha changes from 245 to 202 (17.6% less opacity), preserving
  the original blue-purple RGB values and gradient direction. No global window
  opacity is used. Borders, reflections, message/input/button backgrounds, text,
  icons and character opacity remain unchanged. Effective alpha is checked on
  actual rendered widgets, including background composites.

## KDE blur

v0.9.0's source had translucent backgrounds but no explicit compositor blur hook;
any blur visible on the user's desktop came from compositor/theme policy. The
candidate preserves that policy and adds an explicit request through KDE's public
[KWindowEffects::enableBlurBehind(QWindow*) API](https://api.kde.org/kwindoweffects.html).

`native/effects.cpp` is a tiny bridge with a stable C entry point. It uses public
Qt/KDE headers and a rounded blur region matching the 18 px panel corners.
`glass_effects.py` passes the live QWindow pointer through Shiboken's normal
pointer API; there is no mangled C++ symbol lookup, screenshot capture, background
polling or software blur animation. Requests run only on show/resize, coalesced by
a single-shot timer. Existing compositor blur is not disabled. Without the bridge
or a supporting compositor, transparency still works; requesting blur does not
prove that KWin applied it. Real frosted-background verification remains manual.

The native helper changes the Arch package from `any` to a native architecture
(current build x86_64, recipe also permits aarch64). Added dependencies are
`kwindowsystem` and explicit `shiboken6`; `cmake` is a build dependency. Qt/KDE were
already part of the target desktop. No AI/runtime/model dependency changes occur.
Development remains runnable without compiling the optional helper. To enable
explicit blur in development, build the helper separately and place its resulting
`libhya-effects.so` in `native/`; do not commit generated binaries.

## Build / install / rollback

```sh
python tools/prepare_release.py --output /tmp/hya-v0.9.1-build
cd /tmp/hya-v0.9.1-build
SOURCE_DATE_EPOCH=$(cat SOURCE_DATE_EPOCH) makepkg --cleanbuild
# Only when you choose to install:
sudo pacman -U hya-0.9.1-1-x86_64.pkg.tar.zst
```

Use the matching architecture on other machines. Hya must be restarted to load
updated code/native libraries. Existing installed configuration/history remain in
the same hya XDG directories; the development profile remains hyal. No data
migration is needed for this upgrade.

The working v0.9.0 package remains in `dist/` and is also retained with its original
recipe/source/report under `dist/v0.9.0/`. Roll back with `pacman -U` on that
v0.9.0 package, then restart Hya. Installation/rollback are user-approved actions;
neither was performed by the development agent.

Before editing, a source/artifact backup was created and read-verified:
`backups/v0.9.0-before-v0.9.1-20261019-004515.tar.gz`, with adjacent SHA256 file.

## Checks and release blockers

Build/test results and artifact hashes are recorded in `dist/BUILD_REPORT.txt`
and `dist/SHA256SUMS`. Previews of actual compact/expanded widgets are in
`previews/local-chat.png` and `previews/chat-workspace.png`; bright/dark composites
are in `previews/v0.9.1-*.png`. Offscreen composites demonstrate transparency and
contrast, not compositor blur. No fake wallpaper blur is used in the product.

Before publishing:

1. On real Plasma Wayland, verify actual KWin frost/blur against bright/dark
   wallpaper and windows; toggle compact/expanded and resize at 1×/2× scaling.
2. Inspect complete “Hya” lettering/descender, enlarged orb/ring/diamond/expressions,
   hover/streaming, and absence of clipping/overlap. Check small-screen resizing.
3. Repeat quick regression checks for tray, autostart, docking/undocking, all three
   edge modes, AI streaming/Stop, permissions and setup. v0.9.0's real-desktop
   success is user-reported; this candidate still needs that visual acceptance.
4. Redistribution licensing remains unresolved unless the project owner selects
   a license. The existing LicenseRef-Hya notice does not grant public release
   rights. No license was chosen on the user's behalf.
