# Colibri Environment Setup

The hub that fetches and wires every Colibri app on your machine. It detects your
device, lets you choose features, and clones the right repos into a unified suite
layout with a shared virtualenv and one runtime configuration.

## Credits

This suite builds on two upstream projects:

- **[Colibri](https://github.com/JustVugg/colibri)** — the device-tiered MoE
  inference engine (VRAM hot tier + host pool + SSD-streamed cold experts). The
  engine repo here is a fork of JustVugg/colibri.
- **[AirLLM](https://github.com/lyogavin/airllm)** — layer-streamed inference and
  streamed LoRA training, used to fine-tune large MoE models on small GPUs.

## Layout

| Concept | Repo | Local path |
|---|---|---|
| Engine + CLI | `Liso7150/colibri` | `D:/Colibri` |
| Shared core | `Liso7150/colibri-core` | `D:/Colibri-Suite/colibri-core` |
| CLI wrapper | `Liso7150/colibri-cli` | `D:/Colibri-Suite/colibri-cli` |
| Desktop app | `Liso7150/colibri-code` | `D:/Colibri-Suite/colibri-code` |
| Coding agent | `Liso7150/colibri-coding-agent` | `D:/Colibri-Suite/colibri-coding-agent` |
| JetBrains | `Liso7150/colibri-jetbrains` | `D:/Colibri-Suite/colibri-jetbrains` |
| Installer | `Liso7150/colibri-installer` | `D:/Colibri-Suite/colibri-installer` |
| Fine-tune | `Liso7150/colibri-finetune` | `D:/Colibri-Suite/colibri-finetune` |

The `D:` paths above are the legacy layout, used only on a Windows machine where
those directories already exist. Everywhere else the same layout lives under
`~/Colibri`, `~/Colibri-Suite`, `~/colibri-models` and `~/.cache/colibri`.
Roots, shared venv (`<engine_root>/.venv`), interpreter and workspace are all
resolved through one config file, `~/.colibri/config.json` (override with
`COLIBRI_CONFIG`), and the matching `COLIBRI_*` environment variables. The
workspace defaults to `suite_root`. Caches (`HF_HOME`, pip, npm) are kept under
`cache_root` and never inside the repos.

Pass `--root /path` to keep every checkout and cache under one folder:
`ROOT/engine`, `ROOT/suite`, `ROOT/models`, `ROOT/cache`, with this hub at
`ROOT/setup`. The installer prompts for that destination interactively (default
`~/Colibri`) and downloads nothing before you confirm. The shared config
`~/.colibri/config.json` is the only file written outside the chosen root, since
every Colibri app reads it.

## Usage

```bash
python setup.py detect                         # device + recommended config
python setup.py features                       # list installable features
python setup.py plan --features inference,desktop,coding-agent
python setup.py plan --all --json              # machine-readable, read-only
python setup.py fetch --features inference,desktop
python setup.py install --features inference,desktop
python setup.py install --features inference --build --model <model-dir>
```

`plan`/`--dry-run` never clone, install, write the config or start a server.
`fetch` only clones/verifies checkouts. `install` additionally creates the shared
venv, installs the selected dependencies, optionally builds the native engine
target, and writes the shared config only after every action succeeded. Servers
are never started for you; the plan prints the exact commands to run.

Or use the **[installer](https://github.com/Liso7150/colibri-installer)**, which
bootstraps this hub, detects your device and walks you through feature selection
(`python install.py`). Phones can run the core and PWA locally in Termux, with
the engine on demand when a compatible small model exists; Android browsers and
iOS are PWA clients of a Colibri host.

## Features

| Feature | Requires | Notes |
|---|---|---|
| `inference` | engine, core, cli | Local engine plus the shared runtime/CLI |
| `desktop` | engine, core, desktop, coding-agent | Electron app; packaging is a separate step |
| `coding-agent` | engine, core, coding-agent | Shared agent server plus web/PWA UI |
| `jetbrains` | engine, core, jetbrains | IDE plugin; package it separately |
| `npu` | core (+ `openvino`) | Embedding sidecar only, **not** a decoder |
| `fine-tune` | engine, finetune (+ torch/airllm/...) | Explicit opt-in; nothing downloads or trains implicitly |
| `mobile` | core, coding-agent | PWA on the same device (desktop or Termux phone); engine starts on demand |
| `installer` | installer | Download the portable bootstrap itself |

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite is offline: hardware probes are injected, and the shared-config
validator is compared against `colibri-core`'s authoritative loader whenever a
core checkout is available.
