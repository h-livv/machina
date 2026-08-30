# Not for other machines

**Severity: high.** Machina is not a portable app. It was written for one HP Victus 15 on Fedora KDE. Cloning the repo and running it elsewhere is not “unsupported” in a mild sense — it can **change fans, CPU power limits, and GPU watts using numbers and sysfs nodes that only exist here.**

If you are not on that laptop, **do not apply hardware settings** until you have rewritten the machine-specific pieces. Telemetry might still look interesting; the Apply buttons are the danger.

## What is hard-wired

You will have to change at least:

| Area | What is assumed |
|---|---|
| Chassis | HP Victus 15, `hp-wmi` fans (`pwm1_enable` auto vs max), ACPI profiles `cool` / `quiet` / `balanced` / `performance` |
| CPU | Intel P-state, RAPL PL1 15–45 W, PL2 30–90 W (this 13420H) |
| GPU | NVIDIA, power cap 30–75 W, OEM default 60 W, `nvidia-smi` / NVML |
| Desktop launcher | `Exec` and `Icon` are `/home/h-livv/opt/machina/...` |
| Projects | `~/Projects`, `~/Labs`, `~/opt/machina` |
| Disk scan | those trees plus `~/models-gguf`, `~/Downloads`, `~/.ollama`, and **`/run/media/h-livv`** (Vault) |
| Models | Vault Ollama store, `llama serve` on localhost |
| Jobs | command hints for this machine’s experiments (`geant4`, `sgl_`, `collision/run.py`, …) |
| Services | `ollama.service`, `docker.service`, `nvidia-powerd.service` |
| Polkit policy | `vendor_url` points at `/home/h-livv/opt/machina` |

UI copy also names this chassis, Omen-style behavior, and Vault. That is documentation in the window, not a second config file.

## If you still want to try

1. Run `./scripts/machina --once` and see whether CPU/GPU/fans even exist on your kernel.
2. Fix `packaging/machina.desktop` paths if you want a launcher.
3. Edit project roots, scan targets, and service names so they match your disk.
4. **Rewrite** RAPL / GPU / fan / profile ranges in the guardrails and in `privileged.py` so they match *your* hardware. The helper will refuse values outside its ranges; the worse outcome is ranges that *are* legal on this Victus and **wrong** on yours.
5. Do not turn on the thermal watchdog until those limits are yours.

There is no install wizard. Generalizing this so it runs on any machine is planned and **not done**. Until then, treat the repo as source for one computer, not a release.
