# Safety

Machina can change real hardware. Looking at sensors does not. **Apply**, performance cards, fan override, RAPL, GPU watts, turbo, process kill, and service enable/disable do.

## What it will not do

- Arbitrary sysfs writes
- Arbitrary `systemctl` units (only the allowlisted compute/GPU/model units)
- Arbitrary signals beyond TERM / KILL / STOP / CONT
- Pretend this HP has a fan percent curve
- Flash BIOS or expose HP “Vantage” firmware attributes this kernel does not export
- Delete files (storage refresh is read-only `du`)

The privileged helper refuses values outside its baked-in ranges even if you edit the UI. “Restore safe defaults” on this laptop is: balanced profile, auto fans, turbo on, RAPL 45/90 W, GPU 60 W.

## Confirmations

Medium- and high-risk actions ask first (performance on battery, max fans, GPU above 60 W, turbo off, restore, SIGKILL, enable/disable units). You can loosen that in Safety; high-risk confirmation is meant to stay on.

## Thermal watchdog

If enabled:

- warn around 90 °C
- after **three consecutive** samples at 97 °C, force max fans
- at 100 °C, force the cool profile and 45 W GPU

Cooldown is 45 seconds so it does not fight you in a loop. Turn it off on Safety if you do not want unattended writes.

## Audit

Hardware applies are appended to `~/.local/share/machina/audit.jsonl`. Events (throttling, model load/unload, jobs, disk nearly full) go to `~/.local/share/machina/events.jsonl`. Guardrail numbers live in `~/.config/machina/guardrails.json`.
