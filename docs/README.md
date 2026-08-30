# Docs

If you found this repo by accident: **start at the [root README](../README.md)**. Machina is a private control panel for one HP Victus. It is not a product, not supported, and will not run on your machine until you rewrite hardcoded paths, watt limits, and other personal wiring. There is no installer.

This folder is extra context, not a user manual for a shipped app.

## Read in this order

| Doc | What it is |
| --- | --- |
| [README](../README.md) | What it does, who it is for, why you should not clone-and-run |
| This page | Map of the rest |
| [getting-started.md](getting-started.md) | How *I* run it. The desktop file still points at `/home/h-livv/opt/machina`. |
| [features.md](features.md) | Status, hardware, watchdog, jobs, models, disk/network/logs |
| [not-for-other-machines.md](not-for-other-machines.md) | What is hard-wired and why Apply is dangerous on other hardware |
| [safety.md](safety.md) | Allowlist, confirmations, watchdog thresholds, audit files |

## Workflow in one paragraph

Open Machina → see whether the laptop is hot, busy, or idle → change profile / fans / watts if this firmware exposes them → start or stop a local model, a project job, or an allowlisted service → check events if something throttled or died. It stops at this machine’s sensors and allowlisted writes. It is not `btop`, not Omen Hub on Windows, and not a fleet manager.

## What lands on disk (on my machine)

Nothing in this git tree is the live state. Defaults:

- Config: `~/.config/machina/` — `guardrails.json`, optional `projects.json` / `services.json`, model params
- Data: `~/.local/share/machina/` — `audit.jsonl`, `events.jsonl`, `jobs/`, `logs/`

On another machine the **source** paths (Vault, `~/Projects`, `/run/media/h-livv`, watt clamps) are still wrong until you change them.

## What it will not do

- Fan percent curves (this HP cannot)
- Fake CPU package watts when `energy_uj` is root-only
- Arbitrary sysfs or `systemctl`
- Delete files
- Run unmodified on a random laptop
