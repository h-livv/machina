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

## Run

From the repo root:

```bash
./scripts/machina
```

That sets `PYTHONPATH` and starts the window. Close the window to exit.

One hardware snapshot as JSON, no GUI:

```bash
./scripts/machina --once
```

You can also `pip install -e .` from the repo and run `machina` if you prefer an installed script. That is unused on this machine; the `scripts/machina` launcher is the usual path.

## App menu / taskbar

Same pattern as Citehop on this machine:

```bash
./scripts/install-desktop.sh
```

That puts **Machina** in the KDE Application Launcher. Right-click it there → **Pin to Task Manager**. The `.desktop` file hardcodes `/home/h-livv/opt/machina`; change `Exec` if the repo is anywhere else.

## First launch

- The window reads sensors as your user. No password prompt for looking.
- Applying a profile, fan mode, RAPL, GPU watts, or similar asks for admin via `pkexec` the first time (and as polkit’s `auth_admin_keep` allows after that).
- Confirmations appear for medium/high-risk changes (see [safety](safety.md)).
- Config lands in `~/.config/machina/`. Logs, job output, and the audit trail land in `~/.local/share/machina/`.

Looking is cheap. **Writing is not.** If the summary, CPU, or GPU numbers look sane on this machine, you are fine. If they look empty or absurd, stop and do not press Apply.

## Privileged helper

Hardware writes go through `src/machina/privileged.py` under `pkexec`. There is a polkit policy at `packaging/org.machina.control.policy` if you want a named Machina prompt; KDE can still prompt without installing it. The helper **refuses** values outside its baked-in ranges even if the UI is edited.
