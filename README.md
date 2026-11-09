# Colibri Environment Setup

The hub that fetches and wires every Colibri app on your machine. It detects your
device, lets you choose features, and clones the right repos into a unified suite
layout with a shared virtualenv.

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
| NCM (paused) | `Liso7150/ncm` | `D:/Colibri-Suite/ncm` |

Models live in `D:/colibri-models`, all cache in `D:/.cache`, shared venv at
`D:/Colibri/.venv` (paths are configurable in `repos.json`).

## Usage

```bash
python setup.py detect                         # device + recommended config
python setup.py features                       # list installable features
python setup.py plan --features inference,desktop,jetbrains
python setup.py fetch --features inference,desktop
python setup.py fetch --all
```

Or use the graphical/interactive **[installer](https://github.com/Liso7150/colibri-installer)**,
which detects your device and walks you through feature selection.

## Features

`inference`, `desktop`, `coding-agent`, `jetbrains`, `npu`, `fine-tune`, `ncm`
(paused). Each maps to the repos it needs (see `repos.json`).