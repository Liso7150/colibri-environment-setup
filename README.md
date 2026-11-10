# Fennec Environment Setup

The hub that fetches and wires every Fennec app on your machine. It detects your
device, lets you choose features, and clones the right repos into a unified suite
layout with a shared virtualenv and one runtime configuration.

## Credits

This suite builds on two upstream projects:

- **[Colibri](https://github.com/JustVugg/colibri)** — the base idea of the engine:
  device-tiered MoE inference (VRAM hot tier + host pool + SSD-streamed cold
  experts). The engine checkout tracks upstream directly; no fork is used.
- **[AirLLM](https://github.com/lyogavin/airllm)** — layer-streamed inference and
  streamed LoRA training, used to fine-tune large MoE models on small GPUs.

## Layout

| Concept | Repo | Local path |
|---|---|---|
| Engine + CLI | `JustVugg/colibri` (upstream) | `D:/Colibri` |
| Shared core | `Liso7150/fennec-core` | `D:/Fennec-Suite/fennec-core` |
| CLI wrapper | `Liso7150/fennec-cli` | `D:/Fennec-Suite/fennec-cli` |
| Desktop app | `Liso7150/fennec-desktop` | `D:/Fennec-Suite/fennec-desktop` |
| Coding agent | `Liso7150/fennec-coding-agent` | `D:/Fennec-Suite/fennec-coding-agent` |
| JetBrains | `Liso7150/fennec-jetbrains` | `D:/Fennec-Suite/fennec-jetbrains` |
| Installer | `Liso7150/fennec-installer` | `D:/Fennec-Suite/fennec-installer` |
| Fine-tune | `Liso7150/fennec-finetune` | `D:/Fennec-Suite/fennec-finetune` |

The `D:` paths above are the legacy layout, used only on a Windows machine where
those directories already exist. Everywhere else the same layout lives under
`~/Colibri`, `~/Fennec-Suite`, `~/fennec-models` and `~/.cache/fennec`.

The engine comes from upstream `JustVugg/colibri` at `main` — no fork is used. The
local stack launcher + Vulkan/serve-probe patch is maintained separately in the
private [fennec-patch](https://github.com/Liso7150/fennec-patch) repo and applied
with `git am` (its README has the commands). `fetch`/`update` refuse to touch an
engine checkout that sits on another branch or carries local commits, so a patched
engine is never reset or fast-forwarded behind your back.
Roots, shared venv (`<engine_root>/.venv`), interpreter and workspace are all
resolved through one config file, `~/.fennec/config.json` (override with
`FENNEC_CONFIG`), and the matching `FENNEC_*` environment variables. The
workspace defaults to `suite_root`. Caches (`HF_HOME`, pip, npm) are kept under
`cache_root` and never inside the repos.

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
python setup.py update                         # fast-forward every installed clean checkout
```

`plan`/`--dry-run` never clone, install, write the config or start a server.
`fetch` only clones/verifies checkouts. `install` additionally creates the shared
venv, installs the selected dependencies, optionally builds the native engine
target, and writes the shared config only after every action succeeded. Servers
are never started for you; the plan prints the exact commands to run.
`update` runs `git pull --ff-only` for the installed suite checkouts, refuses
dirty/ahead/foreign checkouts, and leaves the engine checkout alone (update it
deliberately with `fetch --features … --update`). Both upstream credits stay in
the update output and neither is pulled by it: the engine base idea
[JustVugg/colibri](https://github.com/JustVugg/colibri) is updated on purpose in
`D:/Colibri`, and [lyogavin/airllm](https://github.com/lyogavin/airllm) with
`python -m pip install -U airllm` in the shared venv.

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
| `installer` | installer | Download the portable bootstrap itself |

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite is offline: hardware probes are injected, and the shared-config
validator is compared against `fennec-core`'s authoritative loader whenever a
core checkout is available.
