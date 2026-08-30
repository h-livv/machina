# Safety

Machina can change real hardware. Looking at sensors does not. **Apply**, performance cards, fan override, RAPL, GPU watts, turbo, process kill, and service enable/disable do.

## What it will not do

- Arbitrary sysfs writes
- Arbitrary `systemctl` units (only `ollama.service`, `docker.service`, `nvidia-powerd.service` in the privileged helper)
- Arbitrary signals beyond TERM / KILL / STOP / CONT
- Signal pid ≤ 1, Machina’s own pid, or protected names (`systemd`, `kwin_wayland`, `plasmashell`, `init`, `sshd`, `Xorg`, `login`)
- Pretend this HP has a fan percent curve
- Flash BIOS or expose HP “Vantage” firmware attributes this kernel does not export
- Delete files (storage refresh is read-only `du`)
- Report Apply success when a nested restore step failed (`FAIL` in the helper detail)
- Report “nothing changed” on polkit cancel if an unprivileged write already committed
- Treat Start Ollama / llama as success until the HTTP API answers
- Remember a max GPU layer count until a load actually stays resident
- Turn off high-risk confirmation from the Safety page (the checkbox is disabled; Save writes `confirm_high: true`)

The privileged helper refuses values outside its baked-in ranges even if you edit the UI:

| Knob | Helper range |
| --- | --- |
| RAPL PL1 / PL2 | 15–45 W / 30–90 W, PL2 ≥ PL1 |
| NVIDIA power | 30–75 W |
| P-state min/max % | ≥ 10, min ≤ max |
| Backlight | 1–100% |
| Platform profile | `cool` `quiet` `balanced` `performance` |
| Governor | `performance` `powersave` |
| EPP | `default` `performance` `balance_performance` `balance_power` `power` |

**Restore safe defaults** on this laptop is: balanced profile, governor `performance`, EPP `balance_performance`, auto fans, turbo on, P-state 20/100%, RAPL 45/90 W, GPU 60 W. If any nested restore step fails, Apply is **not** ok.

If a name is supplied with an elevated `signal_process`, the helper checks `/proc/<pid>/comm` (15-character kernel truncation) and refuses a mismatch.

## Confirmations

Medium- and high-risk actions ask first. Dialog is **OK** / **Cancel**. High-risk also requires **I understand this can increase heat, noise, or wear.**

You can turn off **medium** confirmation on Safety. **High-risk confirmation cannot be turned off in the UI.** While a confirm dialog is open, other Applies including the watchdog wait (`_busy` is set before `exec()`).

Typical high: Performance on battery, GPU above 70 W, SIGKILL, `systemctl enable`/`disable`. Typical medium: max fans, turbo off, restore, GPU above 60 W or below 40 W, RAPL at the 45/90 W ceiling, SIGTERM, `ollama create`.

Watchdog writes skip the dialog (`skip_confirm`). Runtime polkit cancel always reports “Authorization cancelled — nothing changed.” Hardware Apply is more precise: cancel with nothing committed vs cancel after an unprivileged write already landed.

## Thermal watchdog

Uses **CPU package temperature and GPU temperature only**. If both are missing, a banner says the watchdog is idle; it does not write. Coretemp/acpitz-only heat is ignored by the watchdog (the Overview **WARM** line can still use hottest of package/GPU).

If enabled (default):

- first ~4 s after launch: no watchdog writes (sensors still settling)
- warn around 90 °C (banner only)
- after **three consecutive** ~1 s samples at 97 °C (trip), force max fans
- at 100 °C (critical), force cool profile, max fans, EPP `power`, and a 45 W GPU cap

**Save guardrails** refuses inverted temps (warn must be &lt; trip &lt; critical). Spinboxes are 70–105 °C. Cooldown seconds default to 45 (`watchdog_cooldown_s` in the JSON; not a UI control).

Cooldown starts only after that watchdog Apply **succeeds**. A cancelled or failed thermal write can retry on the next hot streak instead of going silent. Turn the watchdog off on Safety if you do not want unattended writes.

## Audit

Hardware applies are appended to `~/.local/share/machina/audit.jsonl` (including cancel vs ok vs fail, and whether unprivileged writes already ran). The Safety table shows the last 80. Events (throttling, model load/unload, jobs, disk nearly full) go to `~/.local/share/machina/events.jsonl`. Guardrail numbers live in `~/.config/machina/guardrails.json`.
