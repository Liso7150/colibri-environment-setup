# Fennec Environment Setup

The hub that fetches and wires every Fennec app on your machine. It detects your
device, lets you choose features, and clones the right repos into a unified suite
layout with a shared virtualenv and one runtime configuration.

## Credits

This suite builds on upstream projects it does not fork or vendor:

- **[Colibri](https://github.com/JustVugg/colibri)** — the base idea of the engine:
  device-tiered MoE inference (VRAM hot tier + host pool + SSD-streamed cold
  experts). The engine checkout tracks upstream directly; no fork is used.
- **[AirLLM](https://github.com/lyogavin/airllm)** — layer-streamed inference and
  streamed LoRA training, used to fine-tune large MoE models on small GPUs.
- **[Jev / jev-ultrafast](https://github.com/browser-use/jev-ultrafast)** — the
  browser agent behind the `web_task` outlet. Fennec drives it through its own
  `jev_ultrafast.Agent` API and never edits it; its TypeSafe key stays inside its
  own checkout.
- **[OpenBot](https://github.com/CopilotKit/OpenBot)** — the coworker workspace
  behind the `coworker_task` outlet. Fennec only speaks to the AG-UI routes it
  already publishes on loopback; you install and run it yourself.

## Layout

| Concept | Repo | Local path |
|---|---|---|
| Engine + CLI | `JustVugg/colibri` (upstream) | `~/Colibri` |
| Shared core | `Liso7150/fennec-core` | `~/Fennec-Suite/fennec-core` |
| CLI wrapper | `Liso7150/fennec-cli` | `~/Fennec-Suite/fennec-cli` |
| Desktop app | `Liso7150/fennec-desktop` | `~/Fennec-Suite/fennec-desktop` |
| Coding agent | `Liso7150/fennec-coding-agent` | `~/Fennec-Suite/fennec-coding-agent` |
| JetBrains | `Liso7150/fennec-jetbrains` | `~/Fennec-Suite/fennec-jetbrains` |
| Installer | `Liso7150/fennec-installer` | `~/Fennec-Suite/fennec-installer` |
| Fine-tune | `Liso7150/fennec-finetune` | `~/Fennec-Suite/fennec-finetune` |
| Jev outlet | `browser-use/jev-ultrafast` (upstream) | `~/Fennec-Suite/jev-ultrafast` |
| OpenBot outlet | `CopilotKit/OpenBot` (upstream) | `~/Fennec-Suite/OpenBot` |

An older manifest or config may still carry `D:/Colibri`, `D:/Fennec-Suite`,
`D:/fennec-models` and `D:/.cache`. Those are recognised only so they can be
migrated: not every machine has a `D:` drive, so the defaults above are used and
the installer lets you pick any destination.

The engine comes from upstream `JustVugg/colibri` at `main` — no fork is used. The
local stack launcher + Vulkan/serve-probe patch is maintained separately in the
private [fennec-patch](https://github.com/Liso7150/fennec-patch) repo and applied
with `git am` (its README has the commands). `fetch`/`update` refuse to touch an
engine checkout that sits on another branch or carries local commits, so a patched
engine is never reset or fast-forwarded behind your back.
Roots, interpreter and workspace are all
resolved through one config file, `~/.fennec/config.json` (override with
`FENNEC_CONFIG`), and the matching `FENNEC_*` environment variables. The
workspace defaults to `suite_root`. Caches (`HF_HOME`, pip, npm) are kept under
`cache_root` and never inside the repos. The two optional outlets have keys too —
`jev_root`/`FENNEC_JEV_ROOT` and `openbot_url`/`FENNEC_OPENBOT_URL` (`--jev-root`,
`--openbot-url`) — and stay unwritten unless you set them, because the core
probes its own default locations first. Secrets never enter this file; only
`FENNEC_API_KEY` and `FENNEC_APP_TOKEN` carry them.

Pass `--root /path` to keep every checkout and cache under one folder:
`ROOT/engine`, `ROOT/suite`, `ROOT/models`, `ROOT/cache`, with this hub at
`ROOT/setup`. The installer prompts for that destination interactively (default
`~/Colibri`) and downloads nothing before you confirm. The shared config
`~/.fennec/config.json` is the only file written outside the chosen root, since
every Fennec app reads it.

## Usage

```bash
python setup.py detect                         # device + recommended config
python setup.py features                       # list installable features
python setup.py plan --features inference,desktop,coding-agent
python setup.py plan --all --json              # machine-readable, read-only
python setup.py fetch --features inference,desktop
python setup.py install --features inference,desktop
python setup.py install --features inference --build --model <model-dir>
python setup.py plan --features browser-outlets   # clone-only outlets, read-only first
python setup.py update                         # fast-forward every installed clean checkout
```

`plan`/`--dry-run` never clone, install, write the config or start a server.
`fetch` only clones/verifies checkouts. `install` additionally provisions
`python` on PATH with the selected dependencies, optionally builds the native engine
target, and writes the shared config only after every action succeeded. Servers
are never started for you; the plan prints the exact commands to run.
`update` runs `git pull --ff-only` for the installed suite checkouts, refuses
dirty/ahead/foreign checkouts, and leaves every upstream checkout alone — the
engine, Jev and OpenBot are only updated deliberately with
`fetch --features … --update`. All four upstream credits stay in the update
output and none of them is pulled by it: the engine base idea
[JustVugg/colibri](https://github.com/JustVugg/colibri) is updated on purpose in
`~/Colibri`, [lyogavin/airllm](https://github.com/lyogavin/airllm) with
`python -m pip install -U airllm` in the interpreter the apps use, and
[OpenBot](https://github.com/CopilotKit/OpenBot) /
[Jev](https://github.com/browser-use/jev-ultrafast) with their own README
commands.

Or use the **[installer](https://github.com/Liso7150/fennec-installer)**, which
bootstraps this hub, detects your device and walks you through feature selection
(`python install.py`). Phones can run the core and PWA locally in Termux, with
the engine on demand when a compatible small model exists; Android browsers and
iOS are PWA clients of a Fennec host.

## Features

| Feature | Requires | Notes |
|---|---|---|
| `inference` | engine, core, cli | Local engine plus the shared runtime/CLI |
| `desktop` | engine, core, desktop, coding-agent (+ faster-whisper, av<18) | Electron app; packaging is a separate step |
| `coding-agent` | engine, core, coding-agent (+ faster-whisper, av<18) | Shared agent server plus web/PWA UI |
| `jetbrains` | engine, core, jetbrains (+ faster-whisper, av<18) | IDE plugin; package it separately |
| `speech` | core (+ faster-whisper, av<18) | Local STT sidecar on 127.0.0.1:8183, started on demand |
| `npu` | core (+ `openvino`, `openvino-tokenizers`, `numpy`, `huggingface-hub`) | Accelerator sidecar only, **not** a decoder; fetches the prebuilt IR embedding model into `<models_root>/embed/bge-base-en-v1.5-int8-ov` (no optimum-intel, no torch) |
| `fine-tune` | engine, finetune (+ torch/airllm/...) | Explicit opt-in; nothing downloads or trains implicitly |
| `mobile` | core, coding-agent (+ faster-whisper, av<18) | PWA on the same device (desktop or Termux phone); engine starts on demand |
| `browser-outlets` | core, jev, openbot | Clone-only upstreams the core delegates browser work to (`web_task`, `coworker_task`); no dependencies installed, nothing patched, nothing started |
| `installer` | installer | Download the portable bootstrap itself |

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite is offline: hardware probes are injected, and the shared-config
validator is compared against `fennec-core`'s authoritative loader whenever a
core checkout is available.
