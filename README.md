# Machina

Machina is a **personal control panel** for my HP Victus 15 (Intel i5-13420H + RTX 4050) on Fedora KDE. It was built for my own machine. It is **not** a product, not supported, and not meant to ship.

**Do not clone this and expect it to run.** Paths, watt limits, fan control, project roots, model directories, and service names are **hardcoded to this laptop**. If you decide to run it anyway, you **must** change those paths and other personal wiring first. Skip that and you get empty screens, refused writes, or **unsafe hardware assumptions** (fan override, RAPL, NVIDIA power limit). There is no installer and no portability layer. That is not a small cleanup — it is required, and it is on you.

It is the one window I leave open instead of juggling `btop`, `nvidia-smi`, Omen-style power toggles, and a pile of terminals for models and experiments.

## What you can do with it

1. **See what the laptop is doing** — CPU, GPU, fans, thermals, battery, RAM, and a short status line. Missing or unreadable sensors are marked not-ok, not invented. CPU package watts stay absent on this kernel (`energy_uj` is root-only).
2. **Change the knobs this firmware actually exposes** — performance profile (cool / quiet / balanced / performance), CPU policy, turbo, RAPL, GPU power cap, backlight. Fans are auto or max only; this HP has no percent curve.
3. **Let it react when it stays too hot** — warn, then force max fans, then a cooler profile and a lower GPU cap. Off if you do not want unattended writes. It uses package and GPU temperature only.
4. **Handle processes and jobs** — what is using CPU / GPU / VRAM, signal a pid, launch a project task, watch it finish or fail.
5. **Drive local models** — Ollama, llama.cpp, and FreeToken: what is loaded, VRAM, start/stop/unload. Sampler / context / GPU layers are Ollama and llama.cpp only. Start waits until the API answers. On this box, Ollama weights live on Vault; Machina starts `ollama serve` as me so that path is visible. FreeToken is the AppImage in `~/opt/`; Machina can start that UI and unload the engine.
6. **Check disk, network, a few services, and logs** — mounts and a read-only size scan, links and model/dev ports, allowlisted systemd units, audit and events.

Writes that need root go through `pkexec` and an allowlist. Confirmations sit in front of medium/high-risk changes (high-risk also needs an extra checkbox). Apply and model start report failure instead of pretending success when a write, restore step, or server never actually came up. The watchdog is on by default; it waits a few seconds after launch and only then writes after a hot streak.

## Which machine this is for

This is **my Victus**, not a generic Linux monitor.

It fits when the firmware is HP `hp-wmi` (those four profiles, auto/max fans), Intel P-state + RAPL in the 15–45 / 30–90 W band, and an NVIDIA GPU whose OEM cap is 60 W (hard ceiling 75 W). It fits the directories I actually have (`~/Projects`, `~/Labs`, Vault). It does **not** invent Omen Hub features this kernel does not export, and it will not flash BIOS.

On a different chassis the Apply buttons are the danger. Telemetry might still paint; the watt and fan numbers are this laptop’s.

## Run

From the repo root:

| Command | What it does |
| --- | --- |
| `./scripts/machina` | Open the window |
| `./scripts/machina --once` | One telemetry snapshot as JSON, no GUI |
| `./scripts/machina --dump` | Same as `--once` |
| `./scripts/machina --help` | CLI help |
| `./scripts/install-desktop.sh` | Install the KDE/GNOME app-menu launcher (hardcoded path) |
| `python -m unittest discover -s tests -v` | Stdlib unit tests (no pytest extra) |

`pip install -e .` then `machina` is the same entry point (`machina.__main__:main`). Unused on this machine; `./scripts/machina` is the usual path.

The window’s pages and buttons are listed in [docs/features.md](docs/features.md). Safety, watchdog, and audit files: [docs/safety.md](docs/safety.md).

## Documentation

| Doc | What it is |
| --- | --- |
| [docs/README.md](docs/README.md) | Map of the docs |
| [docs/getting-started.md](docs/getting-started.md) | How I run it (not a portable install guide) |
| [docs/features.md](docs/features.md) | Window pages, buttons, and use-cases |
| [docs/not-for-other-machines.md](docs/not-for-other-machines.md) | Hardcoded paths and limits — required reading if you are not me |
| [docs/safety.md](docs/safety.md) | What Apply can write, watchdog, honesty rules, audit files |

## Status

This repo matches **how I run it**: my laptop, Fedora KDE, local models, projects on this disk. Paths, hardware ranges, and defaults are personal. It will not work on another machine until those hardcoded locations and custom bits are replaced. Expect sharp edges and no compatibility promise.

## Later

I want to **generalize** this so it is not tied to one setup: detect hardware instead of assuming this Victus, portable paths, any machine. Until then, treat it as a private tool, not a release.
