# Hya&#x20;

**Hya** is an animated AI desktop companion developed for **HyalOS**, featuring expressive character animations, a glass-inspired interface, and optional local AI powered by Ollama.

**Version:** 0.9.2 Public Beta

## Features

- Animated, customizable desktop character
- Glass-inspired blue-purple chat interface
- Desktop and screen-edge docking
- Customizable orb colors and expressions
- Optional local AI using Ollama
- Application launching and desktop assistance
- Smart Permissions and Action Log
- System tray integration
- Optional Start on Login

Hya works without an AI model. No AI models are bundled.

## Compatibility

Hya is primarily developed and tested on Arch-based Linux distributions running KDE Plasma and Wayland.

Support for other distributions and desktop environments is experimental.

## Installation

See [STANDALONE.md](STANDALONE.md) for Arch Linux package building and installation instructions.

Once installed, launch Hya from KDE's application launcher or run `hya` in a terminal.

AUR and Flathub releases are planned.

## Local AI

Hya supports optional local conversations through Ollama. The first-run setup assistant helps configure the local service and compatible models.

See [AI_SETUP.md](AI_SETUP.md) and [LOCAL_AI.md](LOCAL_AI.md).

## Privacy and Permissions

Hya uses a restricted set of desktop operations and does not execute arbitrary AI-generated shell commands.

Sensitive actions require permission. Trusted installed graphical applications may launch automatically when Smart Permissions is enabled.

Browser searches may contact external services after authorization.

See [SMART_PERMISSIONS.md](SMART_PERMISSIONS.md) and [DESKTOP_TOOLS.md](DESKTOP_TOOLS.md).

## Documentation

- [Standalone installation](STANDALONE.md)
- [AI setup](AI_SETUP.md)
- [Desktop tools](DESKTOP_TOOLS.md)
- [Smart Permissions](SMART_PERMISSIONS.md)
- [Docking](DOCKING.md)
- [Expression Studio](EXPRESSION_STUDIO.md)
- [Release notes](RELEASE_0.9.2.md)

## License

Original Hya source code is licensed under **GNU GPL-3.0-or-later**.

Hya and HyalOS branding and separately identified original artwork are reserved.

See [LICENSE](LICENSE) and [BRANDING.md](BRANDING.md).

---

**Hya v0.9.2 — Public Beta**

Developed for HyalOS.
