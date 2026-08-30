# Docs

If you found this repo by accident: **start at the [root README](../README.md)**. Machina is a private control panel for one HP Victus. It is not a product, not supported, and will not run on your machine until you rewrite hardcoded paths, watt limits, and other personal wiring. There is no installer.

This folder is extra context, not a user manual for a shipped app.

## Read in this order

| Doc | What it is |
| --- | --- |
| [README](../README.md) | What it does, who it is for, why you should not clone-and-run, CLI table |
| This page | Map of the rest |
| [getting-started.md](getting-started.md) | How *I* run it: requirements, CLI, desktop launcher, first launch |
| [features.md](features.md) | Every sidebar page and the buttons on it |
| [not-for-other-machines.md](not-for-other-machines.md) | What is hard-wired and why Apply is dangerous on other hardware |
| [safety.md](safety.md) | Allowlist, confirmations, watchdog, Apply honesty, audit files |

## Workflow in one paragraph

Open Machina → see whether the laptop is hot, busy, or idle → change profile / fans / watts if this firmware exposes them → start or stop a local model, a project job, or an allowlisted service → check events if something throttled or died. It stops at this machine’s sensors and allowlisted writes. It is not `btop`, not Omen Hub on Windows, and not a fleet manager.

## Commands (this machine)

| Command | What it does |
| --- | --- |
| `./scripts/machina` | GUI |
| `./scripts/machina --once` | JSON snapshot to stdout (no window) |
| `./scripts/machina --dump` | Alias for `--once` |
| `./scripts/machina --help` | argparse help |
| `./scripts/install-desktop.sh` | Copy `.desktop` + icon into `~/.local/share` |
| `python -m unittest discover -s tests -v` | Unit tests |

`pip install -e .` exposes the same CLI as `machina`. Hardware Apply, model start/stop, and process signals are not CLI verbs; they only exist in the window (and internally via `pkexec` + `src/machina/privileged.py`). Every sidebar button is listed in [features.md](features.md).

## What lands on disk (on my machine)

Nothing in this git tree is the live state.

**Config** (`~/.config/machina/`):

| File | What |
| --- | --- |
| `guardrails.json` | Watchdog temps, NVIDIA/RAPL ranges, confirm flags |
| `projects.json` | Optional extra project roots |
| `services.json` | Optional extra systemd units (helper still allowlists system verbs) |
| `model-params.json` | Per-model `/set` / llama flags, history toggle |
| `llama-preset.ini` | llama.cpp models-preset Machina writes |
| `models-ui.json` | Models tab layout |
| `gpu-layers.json` | Remembered max `num_gpu` / `-ngl` after a **successful** load |

**Data** (`~/.local/share/machina/`):

| File | What |
| --- | --- |
| `audit.jsonl` | Hardware Apply log |
| `events.jsonl` | Thermals, models, jobs, disk pressure |
| `jobs/` | Captured stdout of launched tasks |
| `logs/` | Machina-spawned `ollama serve` / `llama serve` / FreeToken launch logs |
| `disk-scan.json` | Cached `du` of known trees |

On another machine the **source** paths (Vault, `~/Projects`, `/run/media/h-livv`, watt clamps) are still wrong until you change them.

## What it will not do

- Fan percent curves (this HP cannot)
- Fake CPU package watts when `energy_uj` is root-only
- Arbitrary sysfs or `systemctl`
- Delete files
- Run unmodified on a random laptop
