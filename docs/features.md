# What it does

Machina is a single window for “what is this laptop doing, and what can I safely change?”

There is no in-window command palette and no CLI for Apply, models, or kill. Everything below is a sidebar page, a button, a slider that commits, or a confirm dialog. CLI is only launch / `--once` / `--dump` — see [getting started](getting-started.md).

## Chrome

Window title **Machina**. Sidebar brand **MACHINA** / **Local control plane**. Status line at the bottom of the sidebar (summary + product name). Status bar: last action, or “Another change is still applying…” while a worker is running.

Pills under the banner:

| Pill | Shows |
| --- | --- |
| Status | `HEALTHY`, `HEALTHY (partial data)`, `WARM` (≥80 °C), `THERMALLY CONSTRAINED` (throttle or ≥90 °C), `THERMALLY CRITICAL` (≥97 °C), `UNKNOWN`, `ON BATTERY`, `MEMORY PRESSURE` |
| Profile | HP ACPI profile |
| Fans | Auto / max plus peak rpm |
| Power | `AC` / `Battery` / `Power`, plus battery % when present |

Banner: watchdog warnings, missing package+GPU temps, or a successful Apply. Hidden when nothing is going on.

Busy label (right of the pills): `Applying…`, `Working…`, `Applying parameters…`, `Writing model…`, `Probing max GPU layers…`, or `Loading remembered GPU layers…`.

Only the **visible** page is refreshed each tick (~1 Hz). Collector starts with a 0.3 s sample, then 1 s.

### Confirmations

Medium- and high-risk hardware writes, and some process/service/model actions, open **Confirm** (`OK` / `Cancel`). High-risk also requires checking **I understand this can increase heat, noise, or wear.** Watchdog Applies skip this dialog. While any confirm is open, `_busy` is set so other Applies (including the watchdog) wait.

Risk is assessed per action (performance on battery is high; GPU above 70 W is high; SIGKILL and `systemctl enable`/`disable` are high; max fans, turbo off, restore, GPU above 60 W or below 40 W, RAPL at the 45/90 W ceiling, SIGTERM are medium). Low-risk writes (Cool/Quiet/Balanced, backlight, Start Ollama) apply without a dialog.

## Sidebar order

Overview → Performance → CPU → Cooling → Graphics → Power → Processes → Jobs → Services → Models → Parameters → Storage → Health → Network → **MORE** → Projects → Logs → Events → Safety

## Status (Overview)

Read-only. Machine line (`product · OS`). Status card plus up to four summary lines (and “Partial data — claims are qualified.” when sources are weak).

Gauges: CPU °C, GPU °C, CPU load %, GPU load %. KPIs: RAM (with swap if used), VRAM, CPU clock, GPU power.

Unavailable metrics are labeled, not invented. CPU and battery source flags are ok only when a package temp or usage (CPU) or a percent (battery, if present) exists. This kernel hides CPU package energy from unprivileged processes; Machina will not fake CPU watts. NVIDIA errors set the GPU source to not-ok even if the device is still “present.”

## Hardware

### Performance

Four **ModeCard**s write HP ACPI **platform profile** plus matching governor and EPP (Linux stand-in for Omen’s performance slider). GPU watts and RAPL are **not** bundled here. Click a card to apply.

| Card | Writes |
| --- | --- |
| Cool | profile `cool`, governor `powersave`, EPP `power`, fans auto |
| Quiet | profile `quiet`, governor `powersave`, EPP `balance_power`, fans auto |
| Balanced | profile `balanced`, governor `performance`, EPP `balance_performance`, fans auto |
| Performance | profile `performance`, governor `performance`, EPP `performance`, fans auto (medium; **high on battery**) |

Status line under the cards: current profile, governor, EPP, turbo, and an on-battery hint.

### CPU

KPIs: Utilization, Average clock, Package temp, Turbo. Per-logical-CPU bars.

| Control | What |
| --- | --- |
| Minimum / Maximum performance % sliders | Floor 10%. Do not write until you press the button. |
| **Apply P-state limits** | `min_perf_pct` / `max_perf_pct` |
| EPP combo + **Set energy preference** | Helper allowlist: `default`, `performance`, `balance_performance`, `balance_power`, `power`. Combo is filled from sysfs; values outside the allowlist are blocked. |
| Governor combo + **Set governor** | Helper allowlist: `performance`, `powersave`. |
| **Enable turbo** / **Disable turbo** | `no_turbo` sysfs |

### Cooling

Fan 1 / Fan 2 rpm and Control (`pwm1_enable`). Thermal sensor list.

| Button | Writes |
| --- | --- |
| **BIOS auto** | `pwm1_enable=2` |
| **Maximum override** | `pwm1_enable=0` (medium risk) |

No percent curve. The active mode’s button is disabled.

### Graphics

KPIs: GPU name, Temperature, Utilization, Clocks (core/memory), VRAM, P-state. Intel iGPU clock line. Throttle flags if NVIDIA reports them.

| Control | What |
| --- | --- |
| **NVIDIA power limit** slider | 30–75 W. Commits when you release the slider. |
| **Silent 45 W** | Immediate apply |
| **OEM 60 W** | Immediate apply (this chassis default) |
| **Boost 70 W** | Immediate apply (high risk; above 60 W already needs confirmation) |

### Power

Page title **Power & battery**. KPIs: Charge, Battery health, Cycles, Battery power.

| Control | What |
| --- | --- |
| PL1 / PL2 sliders | 15–45 W / 30–90 W. Do not write until you press the button. |
| **Apply RAPL limits** | Package long_term / short_term |
| **Panel brightness** slider | 1–100%. Commits on release (often unprivileged). |

Note when live CPU watts are missing (`energy_uj` root-only). Limits can still be written via pkexec.

## Watchdog

If enabled (Safety, default on): after ~4 s of samples, three consecutive ~1 Hz ticks at trip/critical can write without a confirm. Thresholds live on Safety. See [safety](safety.md).

## Processes and jobs

### Processes

Filter box (name / command / project). **Mine only** (on). **Hide kernel threads** (on). Table: Name, PID, CPU %, RAM, GPU, VRAM, User, Project, Time. Double-click a row for the command line.

| Button | Signal |
| --- | --- |
| **Command line** | Dialog only |
| **Pause** | STOP |
| **Resume** | CONT |
| **Terminate** | TERM (medium) |
| **Kill** | KILL (high) |

Protected names (`systemd`, `kwin_wayland`, `plasmashell`, `init`, `sshd`, `Xorg`, `login`) and pid ≤ 1 / Machina’s own pid are refused. Elevated kill re-checks `/proc/<pid>/comm` when a name is known.

### Jobs

Launched tasks plus `/proc` processes that look like this machine’s experiments (`collision/run.py`, `geant4`, `sgl_`, `ollama serve`, …). Table: Name, Project, PID, Status, CPU, RAM, VRAM, Elapsed. Exited jobs stay ~2 minutes.

| Button | What |
| --- | --- |
| **Pause** / **Resume** | STOP / CONT |
| **Terminate** | TERM (no Kill button on this page) |
| **Open output** | Job log under `~/.local/share/machina/jobs/` |
| **Reveal command** | Dialog with argv and cwd |
| **Jump to project** | Switches to Projects and selects that repo |

### Projects (under MORE)

Tree of `~/Projects`, `~/Labs`, `~/opt/machina` (plus optional `projects.json`). Tasks from README / CMake / pyproject / justfile **if present**. just is not installed here, so Machina does not invent just recipes.

| Button | What |
| --- | --- |
| **Run** (or double-click a task) | `job.launch` — output on Jobs |
| **Open folder** | File manager on the repo path |

## Local models

### Models

Page title **Model telemetry**. KPIs: Ollama, Loaded, Model VRAM, tok/s (from serve log after you prompt in a terminal), llama.cpp, FreeToken.

| Button | What |
| --- | --- |
| **Start Ollama** | `ollama serve` as you (Vault `OLLAMA_MODELS` if set). Waits up to 8 s for `/api/version`. Honors **History** (`OLLAMA_NOHISTORY` when off). |
| **Stop Ollama** | SIGTERM to your `ollama serve`. System `ollama.service` is Services → Stop. |
| **Start llama** | `llama serve`. Waits up to 20 s until `/v1/models` or `/health` answers. |
| **Stop llama** | SIGTERM to your `llama serve`. |
| **Start FreeToken UI** | `~/opt/freetoken-desktop*.appimage` (daemon :1900, engine :1919). |
| **Unload from VRAM** | Drop the resident runner (Ollama, llama.cpp, or FreeToken engine). No row selection needed. |
| **Unload selected** | Per-row unload from the resident table. |
| **Load selected into VRAM** | Ollama generate keep-alive, or llama.cpp load with saved params. FreeToken: load in that UI (Machina refuses). |

Tables: **Resident models** (Loaded model, Size, Processor, Context, VRAM, Expires) and **Model library** (Model, Size, Family, Source). Column widths persist in `models-ui.json`. Hover the blurb for the long Vault / AppImage note.

tok/s is read from the serve log; Machina does not chat.

### Parameters (Ollama and llama.cpp only)

Model combo (FreeToken names are omitted). Fields: `num_predict` (`infinite` = -1), `top_k`, `top_p`, `min_p`, `temperature`, `num_ctx`, `num_gpu` (`auto` = -1).

| Control | What |
| --- | --- |
| **Think** | Per-model think flag |
| **History** | Global. Off → Ollama `OLLAMA_NOHISTORY`, llama.cpp `--no-cache-prompt` on next start/apply. Stored in `model-params.json`. |
| **Apply to runner** | Reload with those options (`/set` / llama flags). Does not rewrite the GGUF/Modelfile. |
| **Save into model** | `ollama create` (medium) or llama.cpp `llama-preset.ini`, then restart serve if needed. |
| **Max GPU layers** | Probe (or reuse `gpu-layers.json`) the highest `num_gpu` / `-ngl` that keeps a **resident** runner. **Shift+click** re-measures. Cache is written only after a successful load. FreeToken has no probe. |

## The rest

### Storage

Machina never deletes files. KPIs: System disk, Removable / Vault, Last scan.

| Control | What |
| --- | --- |
| **Refresh directory sizes** | Background `du` of `~/Projects`, `~/Labs`, `~/models-gguf`, `~/Downloads`, caches, `~/.ollama`, `~/opt`, and `/run/media/h-livv` (Vault). Cached in `disk-scan.json`. |

Tables: Mounts, Largest watched directories, Recently growing.

### Health

Page title **Hardware health**. KPIs: CPU package, GPU, NVMe composite, Fans, Throttle (Intel counters), Battery health. Thermal list. CPU-watt / GPU-watt / RAM note.

| Button | What |
| --- | --- |
| **Read NVMe SMART (pkexec)** | `nvme smart-log /dev/nvme0n1` via the privileged helper. One-shot; not a runtime worker. |

### Network

Read-only. KPIs: Default route, VPN, TCP established, Downloads (`curl`/`wget`/huggingface/ollama pull). Interface table: Iface, Kind, State, Address, SSID, Rx, Tx. Listening line for watched ports (`:11434`, `:8080`, `:1900`, `:1919`, 8000–8099, and a few other dev ports).

### Services

Table: Unit, Scope, Active, Enabled, Why, Detail. Default units: `ollama.service`, `docker.service`, `nvidia-powerd.service`. Extra names in `~/.config/machina/services.json` can appear; **system** start/stop/enable/disable still only work for the helper allowlist.

| Button | Risk |
| --- | --- |
| **Start** | Low |
| **Stop** / **Restart** | Medium |
| **Enable** / **Disable** | High (boot persistence) |

### Logs

Source list + viewer (last 300 matching lines). **Text search** (Return to apply), severity combo (`any severity` / `info` / `warn` / `error`), **Reload**.

Sources: Machina audit, Machina events, Machina-spawned Ollama / llama.cpp / FreeToken files, journal for `ollama.service` / `nvidia-powerd.service` / `docker.service`, per-job logs.

### Events

Read-only. Correlated timeline (last 16) plus table: When, Level, Title, Detail (thermals, model load/unload, jobs, services, disk ≥ 90%, NVIDIA telemetry loss).

### Safety

Page title **Safety & log**. See [safety](safety.md) for rules.

| Control | What |
| --- | --- |
| **Thermal watchdog (auto max-fan / cool profile)** | On by default |
| **Confirm medium-risk changes** | Can be turned off |
| **Confirm high-risk changes (always recommended)** | Checkbox disabled; Save forces on |
| Warn / Trip / Critical °C | 70–105; Save requires warn < trip < critical |
| **Save guardrails** | Writes `~/.config/machina/guardrails.json` |
| **Restore safe defaults** | Medium. Balanced + auto fans + turbo on + P-state 20/100 + RAPL 45/90 W + GPU 60 W |
| Audit table | When, Reason, Result (`ok` / `cancelled` / `fail`), Detail — last 80 applies |
