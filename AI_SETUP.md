# First-run local AI setup

Hya v0.9 retains the setup wizard introduced with v0.8.2. Launch installed Hya
with `hya`, or development with `python hya.py`. See STANDALONE.md.
No Ollama executable or model weights are bundled. Existing character artwork,
animations, edge surfaces, desktop permissions and SQLite history are preserved.

On first launch the modeless wizard independently checks:

- Whether the Ollama executable is on PATH.
- Whether the configured loopback HTTP service responds.
- Which installed models `/api/show` verifies as local text-completion models.
  Embedding-only, cloud-backed, failed-verification and unsupported models are
  excluded. Models without tool support are labeled “chat only”.

A reachable local service works even when its executable is not on Hya's PATH.
Checks, HTTP streaming and disk preflight do not block inference/animation on the
UI thread. The wizard does not open chat or change the desktop character state.
It has a scrollable body and a fixed Skip/Finish footer for smaller screens.

## Finish, skip, and return later

Choose an existing model and **Use selected model**, or approve a download.
Successful pulls are verified again before they can be selected. The wizard
preserves the existing model as its first selection when it is available.

**Skip AI setup** keeps Hya's character and desktop presence usable, retains the
previous model setting and history, and disables conversational AI until setup is
completed. Closing the first-run wizard has the same effect. Closing a later
reopened wizard cancels setup without changing an established choice.

Reopen **Set up local AI…** from Hya's desktop menu or **AI Setup** in the expanded
chat workspace. Setup does not add the removed compact Options button back.
The wizard does not reappear automatically after Finish/Skip. Existing users see
it once on upgrade because earlier versions did not have a setup-complete flag.

`setup_complete` and `ai_enabled` are stored in the existing XDG config file,
`hyal/ai.ini` for development or `hya/ai.ini` for the installed profile. No
appearance, permission-scope or conversation file is migrated or
removed. Skipped chat makes no Ollama request; enabling AI restores normal model
refresh and chat. Finish may cancel a response that was started while this
modeless wizard was open, marking its partial reply using the existing history
behavior. Setup cannot initially be opened through Hya while a response is busy.

## Native installation and service startup

The guided native path currently supports Arch/EndeavourOS/Manjaro and systems
whose `/etc/os-release` identifies them as Arch-derived, with the distribution
pacman package and a supported terminal (Konsole or XTerm). HyalOS packaging can
use this path when its base identifies itself as Arch-derived. Other distributions
receive guidance instead of a guessed package manager or remote install script.

Clicking **Install Ollama…** first presents the exact fixed command and a default
**No** approval dialog. Only Yes opens a native terminal running:

```
sudo -- /usr/bin/pacman -S --needed ollama
```

There is no shell, `--noconfirm`, repository refresh, full-system upgrade, curl
installer, embedded password field, automatic GPU-stack selection or automatic
package installation. Review pacman's dependencies, disk estimates and download
prompts; sudo handles normal privilege authorization. Package repository/network
errors and declined authorization remain visible in the native terminal. If your
repository database needs maintenance, use your distribution's normal update
workflow; Hya does not silently repair or reconfigure the system.

After installation, Recheck detects the executable. **Start local service…**
separately asks approval for:

```
sudo -- /usr/bin/systemctl start ollama.service
```

It starts the service for this session; it does not enable startup at boot. The
native terminal remains open for inspecting success/failure. Close it after the
operation finishes, then **Recheck**. A terminal launch request never counts as
verified package installation or service startup. Closing Hya/the wizard does not
kill a privileged package transaction: decline/cancel through native prompts and
do not interrupt a package manager while it is committing changes.

The setup-only native commands are not registered desktop tools. Models cannot
invoke them, change their arguments or bypass setup's approval gate. Attempts and
outcomes are recorded in the existing local Action Log under `ai_setup_*` names.
Native prompts are deliberately not run during automated tests.

For other Linux distributions, use a supported native repository package where
available, or follow [Ollama's Linux instructions](https://docs.ollama.com/linux)
independently, then Recheck. Hya never downloads/runs an installation script.
[Arch's Ollama package](https://archlinux.org/packages/extra/x86_64/ollama/) is the
verified native target for this implementation.

## Model downloads

The smallest recommendation is **Qwen3 0.6B**, with a conservative displayed
estimate of **0.6 GB** and about **1.7 GB free disk** required for staging/model
storage. The published quantized weight size is roughly 0.52 GB. It is a starter
model: larger models provide better answers and more reliable tool use.
[Official Qwen3 tags and sizes](https://ollama.com/library/qwen3/tags).

Choices include Qwen3 1.7B (estimated 1.5 GB), Qwen3 4B (estimated 2.6 GB), or an
explicit local Ollama library model name with a user-entered size estimate.
URLs, executable paths, shell strings and explicit cloud tags are rejected.

**Download** shows a default-No confirmation with size and free-space estimates.
Only approval sends `/api/pull` to the configured loopback endpoint. Ollama
contacts its registry to fetch model files; no conversation is sent. Pulls are
streamed asynchronously with status, per-layer bytes and progress. Previously
cached blobs may be reused. Percentages reflect layers reported so far, and may
change as additional layers are discovered. The client times out on inactivity,
not total download duration. No artificial chat-size limit accumulates over the
whole progress stream.

The disk preflight requires twice the estimated download size plus 512 MiB.
**Disk-check location** is a best-effort hint: `OLLAMA_MODELS` from Hya's
environment, an existing `/var/lib/ollama`, the official Linux service default, or
`~/.ollama/models`. It does not change the server's model directory. Ollama's API
does not report the actual configured directory, which can differ from Hya's
environment; confirm that the hint is on the server's model-storage filesystem.
See [Ollama storage configuration](https://docs.ollama.com/faq#where-are-models-stored).
Server disk-full errors are still handled if the estimate/location is wrong.
If the reported layers exceed the approved size estimate, Hya stops its pull and
asks for a larger estimate or a smaller model rather than silently expanding the
approved download. RAM for inference is separate from disk requirements.

**Cancel current check / download**, Skip, closing the wizard and app shutdown
abort Hya's network request and invalidate pending disk-check callbacks. Ollama
may retain partial blobs for resumption; Hya never deletes models automatically.
A pull initiated by another client may continue. There is no delete/rollback call
that could remove an existing shared model. Failures, incomplete streams, stalls,
invalid progress, registry failures and server disk-full messages remain visible
and allow retry/Recheck. Completed downloads still need compatibility verification.
[Pull API](https://docs.ollama.com/api/pull).

## Files and testing

- `ai_setup.py`: setup-only HTTP checks, compatible-model verification, native
  command allowlist, disk preflight, download/cancellation and audit integration.
- `ai_setup_window.py`: wizard, explicit approvals, existing/custom model choices,
  progress, retry/recheck, skip and persisted completion.
- `ai_settings.py`: two compatible settings added; existing values remain.
- `hya.py`: first-launch scheduling, reopen menu and shutdown hook.
- `chat_window.py`: expanded-workspace setup button and skipped-AI behavior.
- `ollama_client.py`: optional progress-stream handling, preserving existing chat
  requests; AI-disabled guard prevents conversation generation.
- `tests/test_ai_setup.py`: mocked HTTP/installation and actual Qt widget tests.
- `previews/ai-setup.png`: inspected offscreen capture of the actual wizard.

Backup: `backups/v0.8.2-before-ai-setup-20261019-001251.tar.gz`.

Run:

```sh
QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME=/tmp/hya-setup-test-config XDG_DATA_HOME=/tmp/hya-setup-test-data python -m unittest discover -s tests
python -m compileall -q ai_setup.py ai_setup_window.py ai_settings.py ollama_client.py chat_window.py hya.py tests
```

All **168 automated tests** passed, including 18 setup tests. Syntax checks and
the offscreen startup/dock/expand/close/reopen/shutdown smoke test passed. The
actual wizard capture was inspected to confirm the fixed Skip footer remains
visible. Existing artwork, animation, edge QML, permission policy, application
matching and history modules were checked byte-for-byte against the backup.

No actual package installation, service start or model download has been tested
in this execution environment. Real Plasma Wayland/manual checks remain:

1. First-run wizard appears once; Skip/close retains an animated edge Hya and
   reopening setup works. Restart after Skip/Finish should not prompt again.
2. On a clean supported machine/VM, decline install, then approve and inspect
   native pacman/sudo prompts, installation failure/cancellation, service start
   approval and Recheck. Verify no startup enablement or GPU packages are assumed.
3. Download the small model, inspect actual registry progress, Cancel/retry,
   disconnect/reconnect and low-disk handling on the server's real filesystem.
4. Select an existing/local chat-only model, reject an embedding/cloud model,
   verify conversation streaming and persistence after restart.
5. Test a small display, keyboard focus, wizard close/shutdown during a pull, and
   character animation/docking across Bottom/Left/Right. Verify no history,
   appearance, permission or expression settings were reset.
