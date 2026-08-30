# Getting started

Machina is a **personal** app for one specific laptop. Read [not for other machines](not-for-other-machines.md) before you do anything else. Running the stock tree on different hardware can apply the wrong fan, RAPL, or GPU power limits.

If this is that Victus on Fedora KDE, the steps below are enough.

## Requirements

- Linux with a graphical session (built and used on Fedora KDE)
- Python 3.11+
- PySide6
- `pkexec` if you want to change hardware settings (telemetry and the rest of the UI work without it)

On Fedora:

```bash
sudo dnf install python3-pyside6
```

NVIDIA telemetry uses the driver library when present (`libnvidia-ml`). `nvidia-smi` is only a fallback. Ollama / llama.cpp / FreeToken pages need those stacks only if you use them.

Optional for the desktop icon PNG set: ImageMagick `magick` (`./scripts/install-desktop.sh` still installs the SVG without it).

## CLI

All of these are from the **repo root**. `./scripts/machina` puts `src/` on `PYTHONPATH` and sets `argv[0]` to `machina` so the taskbar can pin it.

```text
usage: machina [--once] [--dump] [--help]
```

| Invocation | Effect |
| --- | --- |
| `./scripts/machina` | Open the Qt window. Close the window to exit. |
| `./scripts/machina --once` | Sleep 0.35 s, print one `Sampler().snapshot()` as JSON, exit 0. No GUI. |
| `./scripts/machina --dump` | Same as `--once`. |
| `./scripts/machina --help` | Print argparse help. |
| `./scripts/install-desktop.sh` | Install `~/.local/share/applications/machina.desktop` and icons. `Exec`/`Path` in the desktop file are `/home/h-livv/opt/machina`. |
| `python -m unittest discover -s tests -v` | Run stdlib tests. No pytest extra in `pyproject.toml`. |
| `pip install -e .` then `machina` | Same entry as the script (`machina = machina.__main__:main`). Unused here. |

There is no CLI for Apply, start Ollama, or kill. Those are window actions only (see [features](features.md)).

`--once` is a live sensor dump, not a golden fixture. Use it to see whether CPU/GPU/fans exist before touching Apply. `sources.*.ok` in that JSON is the honesty flag for each collector.

## App menu / taskbar

Same pattern as Citehop on this machine:

```bash
./scripts/install-desktop.sh
```

That puts **Machina** in the KDE Application Launcher. Right-click it there → **Pin to Task Manager**. Change `Exec` and `Path` in `packaging/machina.desktop` if the repo is anywhere else, then re-run the install script.

## First launch

- The window reads sensors as your user. No password prompt for looking.
- Applying a profile, fan mode, RAPL, GPU watts, or similar asks for admin via `pkexec` the first time (and as polkit’s `auth_admin_keep` allows after that).
- Confirmations appear for medium/high-risk changes (see [safety](safety.md)): **OK** / **Cancel**. High-risk also requires **I understand this can increase heat, noise, or wear.** A confirm dialog blocks other Applies, including the watchdog, until you accept or cancel.
- The thermal watchdog (on by default) will not write for about four seconds after launch, then only after three consecutive hot samples. Turn it off on Safety if you do not want unattended writes.
- Config lands in `~/.config/machina/`. Logs, job output, and the audit trail land in `~/.local/share/machina/`.
- Sidebar pills: **Status**, **Profile**, **Fans**, **Power** (AC or Battery). A banner appears for watchdog warnings and apply results. The status bar repeats the last action.

Looking is cheap. **Writing is not.** If the summary, CPU, or GPU numbers look sane on this machine, you are fine. If they look empty or absurd, stop and do not press Apply.

## Privileged helper

Hardware writes go through `src/machina/privileged.py` under `pkexec`. There is a polkit policy at `packaging/org.machina.control.policy` if you want a named Machina prompt; `./scripts/install-desktop.sh` does **not** install it. KDE can still prompt without it. The helper **refuses** values outside its baked-in ranges even if the UI is edited.

Some knobs (for example backlight) can succeed as your user **before** the polkit dialog. If you dismiss the dialog after that, the status line says unprivileged writes already applied — not “nothing changed.”
