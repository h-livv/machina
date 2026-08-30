# What it does

Machina is a single window for “what is this laptop doing, and what can I safely change?”

## Status

Live CPU, GPU, fans, thermals, battery, RAM, and a short status line (healthy / hot / throttling / partial data). Unavailable metrics are labeled, not invented. This kernel hides CPU package energy from unprivileged processes; Machina will not fake CPU watts.

## Hardware

Performance modes that match this HP firmware (`cool`, `quiet`, `balanced`, `performance`), plus CPU governor / energy preference, turbo, P-state floors, RAPL PL1/PL2, NVIDIA power cap, and backlight.

Fans on this chassis are **auto or max only**. There is no percent curve in the firmware, so Machina does not pretend you can set 37%.

## Watchdog

If the machine stays too hot, Machina can warn, then force max fans, then a cooler profile and a lower GPU cap. Thresholds live in settings; see [safety](safety.md).

## Processes and jobs

A process list with CPU / RAM / GPU / VRAM, terminate / kill / pause, and jobs launched from project tasks. Output is captured under `~/.local/share/machina/jobs/`. Long-running project processes can show up as detected jobs.

## Local models

Ollama, llama.cpp, and FreeToken: what is installed, what is in VRAM, start/stop/unload. Sampler / context / GPU-layer parameters apply to Ollama and llama.cpp only. On this machine, Ollama weights are expected on Vault; starting Ollama from Machina runs `ollama serve` as you so that path is visible. The system `ollama.service` unit does not see that store. FreeToken is the AppImage in `~/opt/` plus the desktop daemon on localhost:1900 (engine :1919); Machina starts that UI and can stop the engine to free VRAM.

## The rest

- **Storage** — mounts and a background size scan of a few known directories (never deletes).
- **Network** — interfaces, Wi-Fi, traffic, and ports used by models / dev servers.
- **Services** — a short allowlist (`ollama`, `docker`, `nvidia-powerd`), not the whole systemd session.
- **Logs and events** — Machina audit, model-server logs Machina started, a few journal units, and an event list for thermals, models, jobs, and disk pressure.
