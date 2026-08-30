"""Unprivileged runtime actions: processes, jobs, models, user services.

Hardware writes still go through control.apply_actions / privileged.py.
"""
from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from machina.control import apply_actions
from machina.jobs import job_manager
from machina.models import (
    LLAMA_BASE,
    OLLAMA_BASE,
    is_freetoken_source,
    is_llama_source,
    llama_log_path,
    ollama_log_path,
)
from machina.projects import Task, discover_projects
from machina.services import ALLOWED_VERBS, is_allowed_unit
from machina.util import http_json, run_cmd, which

PROTECTED_NAMES = {
    "systemd",
    "kwin_wayland",
    "plasmashell",
    "init",
    "sshd",
    "Xorg",
    "login",
}
PROTECTED_PIDS = {1, os.getpid(), os.getppid()}
ALLOWED_SIGNALS = {
    "term": signal.SIGTERM,
    "kill": signal.SIGKILL,
    "stop": signal.SIGSTOP,
    "cont": signal.SIGCONT,
}


@dataclass
class RuntimeResult:
    ok: bool
    message: str
    privileged: bool = False
    cancelled: bool = False
    payload: dict[str, Any] | None = None


def dispatch(kind: str, payload: dict[str, Any]) -> RuntimeResult:
    try:
        if kind == "process.signal":
            return signal_process(int(payload["pid"]), str(payload.get("signal", "term")), str(payload.get("name") or ""))
        if kind == "job.launch":
            return launch_task(str(payload["project"]), str(payload["task_id"]))
        if kind == "job.signal":
            return signal_job(str(payload["job_id"]), str(payload.get("signal", "term")))
        if kind == "model.start_ollama":
            return start_ollama()
        if kind == "model.stop_ollama":
            return stop_ollama()
        if kind == "model.start_freetoken":
            return start_freetoken_ui()
        if kind == "model.load":
            name = str(payload["name"])
            source = str(payload.get("source") or "")
            if is_freetoken_source(source):
                return RuntimeResult(
                    False,
                    "Load FreeToken models in the FreeToken UI. Machina only starts the desktop and unloads the engine.",
                )
            if is_llama_source(source):
                return llama_load_with_params(name)
            return ollama_load(name)
        if kind == "model.load_max_gpu":
            if is_freetoken_source(str(payload.get("source") or "")):
                return RuntimeResult(False, "FreeToken has no Machina GPU-layer probe.")
            return load_max_gpu(
                str(payload["name"]),
                str(payload.get("source") or ""),
                force=bool(payload.get("force")),
            )
        if kind == "model.unload":
            name = str(payload["name"])
            if is_freetoken_source(str(payload.get("source") or "")):
                return freetoken_unload(name)
            if is_llama_source(str(payload.get("source") or "")):
                return llama_unload(name)
            return ollama_unload(name)
        if kind == "model.unload_resident":
            return unload_resident()
        if kind == "model.apply_params":
            return apply_model_params(dict(payload), write=False)
        if kind == "model.write_params":
            return apply_model_params(dict(payload), write=True)
        if kind == "model.start_llama":
            return start_llama()
        if kind == "model.stop_llama":
            return stop_named("llama serve", "llama")
        if kind == "service":
            return service_verb(str(payload["unit"]), str(payload["scope"]), str(payload["verb"]))
        if kind == "storage.refresh":
            from machina.host import Engine  # noqa: F401 — caller refreshes via engine

            return RuntimeResult(True, "Disk scan requested.")
        return RuntimeResult(False, f"Unknown runtime action {kind!r}")
    except Exception as exc:  # noqa: BLE001
        return RuntimeResult(False, str(exc))


def signal_process(pid: int, sig_name: str, name: str = "") -> RuntimeResult:
    if pid in PROTECTED_PIDS or pid <= 1:
        return RuntimeResult(False, f"Refusing to signal pid {pid}.")
    if name in PROTECTED_NAMES:
        return RuntimeResult(False, f"Refusing to signal protected process {name}.")
    sig = ALLOWED_SIGNALS.get(sig_name)
    if sig is None:
        return RuntimeResult(False, f"Signal {sig_name!r} is not allowed.")
    try:
        os.kill(pid, sig)
        return RuntimeResult(True, f"Sent SIG{sig_name.upper()} to {pid}.")
    except ProcessLookupError:
        return RuntimeResult(False, "Process already gone.")
    except PermissionError:
        result = apply_actions(
            [{"op": "signal_process", "pid": pid, "signal": sig_name, "name": name}],
            reason=f"signal:{sig_name}",
        )
        return RuntimeResult(result.ok, result.message, privileged=True, cancelled=result.cancelled)
    except OSError as exc:
        return RuntimeResult(False, str(exc))


def signal_job(job_id: str, sig_name: str) -> RuntimeResult:
    sig = ALLOWED_SIGNALS.get(sig_name)
    if sig is None:
        return RuntimeResult(False, f"Signal {sig_name!r} is not allowed.")
    job = job_manager().get(job_id)
    if job is None:
        return RuntimeResult(False, "Unknown job.")
    if job.pid is None:
        return RuntimeResult(False, "Job has no pid.")
    try:
        msg = job_manager().signal(job_id, sig)
        if msg != "ok":
            return RuntimeResult(False, msg)
        return RuntimeResult(True, f"Sent SIG{sig_name.upper()} to {job.name}.")
    except PermissionError:
        result = apply_actions(
            [{"op": "signal_process", "pid": job.pid, "signal": sig_name, "name": job.name}],
            reason=f"job:{sig_name}",
        )
        return RuntimeResult(result.ok, result.message, privileged=True, cancelled=result.cancelled)


def launch_task(project_name: str, task_id: str) -> RuntimeResult:
    projects = discover_projects()
    project = next((p for p in projects if p.name == project_name), None)
    if project is None:
        return RuntimeResult(False, f"Project {project_name!r} not found.")
    task = next((t for t in project.tasks if t.id == task_id), None)
    if task is None:
        return RuntimeResult(False, "Unknown task.")
    python = project.venv if task.needs_venv else None
    job = job_manager().launch(task, python=python)
    if job.status == "failed":
        return RuntimeResult(False, f"Failed to start {task.title}. See {job.log_path}")
    return RuntimeResult(True, f"Started {task.title} (pid {job.pid}).", payload={"job_id": job.id, "log": job.log_path})


def start_ollama() -> RuntimeResult:
    ok, _, _ = http_json(f"{OLLAMA_BASE}/api/version", timeout=0.6)
    if ok:
        return RuntimeResult(True, "Ollama is already running.")
    binary = which("ollama")
    if not binary:
        return RuntimeResult(False, "ollama is not installed.")
    env: dict[str, str] = {}
    models = os.environ.get("OLLAMA_MODELS")
    if models:
        env["OLLAMA_MODELS"] = models
    from machina.model_params import history_enabled

    if not history_enabled():
        env["OLLAMA_NOHISTORY"] = "1"
    job = job_manager().spawn_logged("ollama serve", [binary, "serve"], ollama_log_path(), extra_env=env)
    extra = "" if history_enabled() else " (OLLAMA_NOHISTORY)"
    if not _wait_ollama(8.0):
        return RuntimeResult(
            False,
            f"Started ollama serve as pid {job.pid} but /api/version never answered.{extra}",
        )
    return RuntimeResult(True, f"Started ollama serve as pid {job.pid} (your user, Vault models if OLLAMA_MODELS is set).{extra}")


def stop_ollama() -> RuntimeResult:
    ok, _, _ = http_json(f"{OLLAMA_BASE}/api/version", timeout=0.6)
    if not ok:
        return RuntimeResult(True, "Ollama is not running.")
    return stop_named("ollama serve", "ollama")


def stop_named(needle: str, name: str) -> RuntimeResult:
    import pathlib

    killed = 0
    uid = os.getuid()
    proc = pathlib.Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in PROTECTED_PIDS:
            continue
        try:
            raw = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace")
            status = (entry / "status").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle not in raw:
            continue
        uid_line = next((ln for ln in status.splitlines() if ln.startswith("Uid:")), "")
        try:
            puid = int(uid_line.split()[1])
        except (IndexError, ValueError):
            puid = -1
        if puid != uid:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
        except OSError:
            continue
    if killed:
        return RuntimeResult(True, f"Sent SIGTERM to {killed} {name} process(es).")
    return RuntimeResult(False, f"No {name} process owned by you was found. System units need Services → stop.")


def ollama_load(name: str, *, num_gpu: int | None = None) -> RuntimeResult:
    body = _ollama_generate_body(name, keep_alive=-1, num_gpu=num_gpu)
    extra = ""
    timeout = 8.0
    options = body.get("options") or {}
    if num_gpu is not None or options.get("num_gpu") is not None or options.get("num_ctx") is not None:
        timeout = 180.0
    if num_gpu is not None:
        extra = f" (num_gpu {num_gpu})"
    elif "num_gpu" in options:
        extra = f" (num_gpu {options['num_gpu']})"
    ok, _, err = http_json(f"{OLLAMA_BASE}/api/generate", timeout=timeout, data=body)
    if not ok:
        return RuntimeResult(False, err or "load failed")
    return RuntimeResult(True, f"Requested load of {name}{extra}.")


def _ollama_generate_body(name: str, *, keep_alive: int = -1, num_gpu: int | None = None) -> dict[str, Any]:
    from machina.gpu_layers import remembered_gpu_layers
    from machina.model_params import params_for

    saved = params_for(name)
    options = saved.options() if saved else {}
    if num_gpu is not None:
        options["num_gpu"] = num_gpu
    elif "num_gpu" not in options:
        cached = remembered_gpu_layers("ollama", name)
        if cached:
            options["num_gpu"] = cached[0]
    body: dict[str, Any] = {"model": name, "prompt": "", "keep_alive": keep_alive, "stream": False}
    if options:
        body["options"] = options
    if saved and saved.system.strip():
        body["system"] = saved.system.strip()
    if saved and saved.think is not None:
        body["think"] = bool(saved.think)
    return body


def apply_model_params(payload: dict[str, Any], *, write: bool) -> RuntimeResult:
    from machina.model_params import (
        params_for,
        params_from_payload,
        save_params,
        set_history,
    )

    name = str(payload.get("name") or "").strip()
    if not name:
        return RuntimeResult(False, "No model selected.")
    source = str(payload.get("source") or "")
    if is_freetoken_source(source):
        return RuntimeResult(False, "FreeToken has no Machina parameter editor.")
    raw = payload.get("params")
    if not isinstance(raw, dict):
        return RuntimeResult(False, "Missing parameter payload.")
    params = params_from_payload(raw)
    previous = params_for(name, source)
    if previous is not None:
        params.system = previous.system
    if is_llama_source(source):
        return apply_llama_params(name, params, payload, write=write)
    save_params(name, params, source)
    if "history" in payload:
        set_history(bool(payload.get("history")))

    body = {
        "model": name,
        "prompt": "",
        "keep_alive": -1,
        "stream": False,
        "options": params.options(),
    }
    if params.system.strip():
        body["system"] = params.system.strip()
    if params.think is not None:
        body["think"] = bool(params.think)
    ok, _, err = http_json(f"{OLLAMA_BASE}/api/generate", timeout=180.0, data=body)
    if not ok:
        return RuntimeResult(False, err or "failed to apply parameters to the runner")

    bits = [f"Applied /set options to {name} (runner kept alive)"]
    if write:
        created = _ollama_create_params(name, params)
        if not created.ok:
            return RuntimeResult(False, f"{bits[0]}, but ollama create failed: {created.message}")
        bits.append(created.message)
    if payload.get("history") is False:
        bits.append("history off — restart Ollama (or export OLLAMA_NOHISTORY=1) for `ollama run`")
    return RuntimeResult(True, ". ".join(bits) + ".")


def _ollama_create_params(name: str, params: object) -> RuntimeResult:
    from machina.model_params import ModelParams, to_modelfile

    assert isinstance(params, ModelParams)
    binary = which("ollama")
    if not binary:
        return RuntimeResult(False, "ollama is not installed.")
    modelfile = to_modelfile(name, params)
    code, out, err = run_cmd([binary, "create", name, "-f", "-"], timeout=180.0, input_text=modelfile)
    if code != 0:
        # Older Ollama rejects PARAMETER think.
        if "think" in (err or out).lower() and "PARAMETER think" in modelfile:
            stripped = "\n".join(ln for ln in modelfile.splitlines() if not ln.startswith("PARAMETER think")) + "\n"
            code, out, err = run_cmd([binary, "create", name, "-f", "-"], timeout=180.0, input_text=stripped)
        if code != 0:
            return RuntimeResult(False, (err or out or "ollama create failed").strip()[:400])
    return RuntimeResult(True, f"Wrote parameters into model {name} (ollama create)")


def apply_llama_params(name: str, params: object, payload: dict[str, Any], *, write: bool) -> RuntimeResult:
    from machina.model_params import ModelParams, save_params, set_history, write_llama_preset

    assert isinstance(params, ModelParams)
    save_params(name, params, "llama.cpp")
    if "history" in payload:
        set_history(bool(payload.get("history")))
    preset_note = ""
    if write:
        preset = write_llama_preset(name, params)
        preset_note = f"Wrote llama.cpp preset {preset}"

    _stop_llama_wait()
    if _llama_reachable():
        return RuntimeResult(False, "Could not stop llama serve to apply flags.")
    ngl = params.num_gpu if params.num_gpu is not None and int(params.num_gpu) >= 0 else None
    started = start_llama(ngl=ngl, params=params)
    if not started.ok:
        return started
    if not _wait_llama(20.0):
        return RuntimeResult(False, "llama serve did not come up in time.")
    loaded = llama_load(name, timeout=180.0)
    if not loaded.ok:
        return loaded
    props_note = _llama_push_props(name, params)
    bits = [f"Applied llama.cpp flags to {name} (serve restarted, model loaded)"]
    if preset_note:
        bits.append(preset_note)
    if props_note:
        bits.append(props_note)
    if payload.get("history") is False:
        bits.append("history off — serve started with --no-cache-prompt")
    return RuntimeResult(True, ". ".join(bits) + ".")


def _llama_push_props(name: str, params: object) -> str:
    from machina.model_params import ModelParams

    assert isinstance(params, ModelParams)
    system = (params.system or "").strip()
    if not system:
        return ""
    ok, _, err = http_json(
        f"{LLAMA_BASE}/props",
        timeout=2.0,
        data={"model": name, "system_prompt": system},
    )
    if not ok:
        return f"system prompt saved; POST /props skipped ({(err or 'failed')[:160]})"
    return "system prompt posted to /props"


def ollama_unload(name: str) -> RuntimeResult:
    ok, _, err = http_json(
        f"{OLLAMA_BASE}/api/generate",
        timeout=4.0,
        data={"model": name, "prompt": "", "keep_alive": 0, "stream": False},
    )
    if not ok:
        return RuntimeResult(False, err or "unload failed")
    return RuntimeResult(True, f"Requested unload of {name}.")


def unload_resident() -> RuntimeResult:
    """Drop whatever is currently in VRAM (ollama ps + llama.cpp loaded + FreeToken engine)."""
    names: list[str] = []
    ok, data, _ = http_json(f"{OLLAMA_BASE}/api/ps", timeout=1.5)
    if ok and isinstance(data, dict):
        for item in data.get("models") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "")
            if not name:
                continue
            ollama_unload(name)
            names.append(name)
    llama_ok, llama_data, _ = http_json(f"{LLAMA_BASE}/models", timeout=0.6)
    if not llama_ok:
        llama_ok, llama_data, _ = http_json(f"{LLAMA_BASE}/v1/models", timeout=0.4)
    if llama_ok and isinstance(llama_data, dict):
        for item in llama_data.get("data") or llama_data.get("models") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("id") or item.get("name") or "")
            status = item.get("status")
            if isinstance(status, dict):
                status = status.get("value")
            if name and str(status or "") in {"loaded", "loading", "sleeping", "running"}:
                llama_unload(name)
                names.append(name)
    ft = freetoken_unload_result()
    if ft.get("error"):
        extra = str(ft["error"])
        if names:
            return RuntimeResult(False, f"Unloaded {', '.join(names)}, but FreeToken: {extra}")
        return RuntimeResult(False, extra)
    if ft.get("stopped") and not ft.get("already"):
        names.append(str(ft.get("model") or "freetoken"))
    if not names:
        return RuntimeResult(True, "No model is resident in VRAM.")
    return RuntimeResult(True, f"Unloaded from VRAM: {', '.join(names)}.")


def start_freetoken_ui() -> RuntimeResult:
    import subprocess

    from machina.freetoken import appimage_path, log_path, ui_running

    if ui_running():
        return RuntimeResult(True, "FreeToken UI is already running.")
    image = appimage_path()
    if image is None:
        return RuntimeResult(
            False,
            "FreeToken AppImage not found. Expected ~/opt/freetoken-desktop*.appimage (or FREETOKEN_APPIMAGE).",
        )
    log = log_path()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"\n$ {image}\n")
            handle.flush()
        proc = subprocess.Popen(
            [str(image)],
            cwd=str(image.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return RuntimeResult(False, str(exc))
    return RuntimeResult(True, f"Started FreeToken UI as pid {proc.pid}.")


def freetoken_unload(name: str = "") -> RuntimeResult:
    result = freetoken_unload_result()
    if result.get("error"):
        return RuntimeResult(False, str(result["error"]))
    if result.get("skipped"):
        return RuntimeResult(True, "FreeToken daemon is not reachable.")
    shown = name or result.get("model") or "freetoken"
    if result.get("already"):
        return RuntimeResult(True, f"FreeToken engine was not running ({shown}).")
    return RuntimeResult(True, f"Stopped FreeToken engine ({shown}).")


def freetoken_unload_result() -> dict:
    from machina.freetoken import stop_engine

    return stop_engine()


def _llama_reachable(timeout: float = 0.5) -> bool:
    ok, _, _ = http_json(f"{LLAMA_BASE}/v1/models", timeout=timeout)
    if ok:
        return True
    return _llama_health_up(timeout)


def _llama_health_up(timeout: float) -> bool:
    """llama.cpp /health is often plain 'OK', not JSON."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{LLAMA_BASE}/health", timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _stop_llama_wait(seconds: float = 8.0) -> None:
    if not _llama_reachable(0.4):
        return
    stop_named("llama serve", "llama")
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not _llama_reachable(0.3):
            return
        time.sleep(0.2)


def start_llama(*, ngl: int | None = None, params: object | None = None) -> RuntimeResult:
    from machina.model_params import ModelParams, llama_last_model, llama_serve_flags, params_for

    binary = which("llama")
    if not binary:
        return RuntimeResult(False, "llama is not installed.")
    if _llama_reachable():
        return RuntimeResult(True, "llama serve is already reachable.")
    saved = params if isinstance(params, ModelParams) else None
    if saved is None:
        last = llama_last_model()
        if last:
            saved = params_for(last, "llama.cpp")
            if ngl is None and saved is None:
                from machina.gpu_layers import remembered_gpu_layers

                cached = remembered_gpu_layers("llama.cpp", last)
                if cached:
                    ngl = cached[0]
    env = {}
    models = os.environ.get("LLAMA_ARG_MODELS_DIR")
    if models:
        env["LLAMA_ARG_MODELS_DIR"] = models
    argv = [binary, "serve", *llama_serve_flags(saved, ngl)]
    job = job_manager().spawn_logged("llama serve", argv, llama_log_path(), extra_env=env)
    extra = f" (-ngl {ngl})" if ngl is not None else " with auto GPU fit"
    if not _wait_llama(20.0):
        return RuntimeResult(False, f"Started llama serve as pid {job.pid} but it never became reachable.{extra}")
    return RuntimeResult(True, f"Started llama serve as pid {job.pid}{extra}.")


def llama_load(name: str, timeout: float = 8.0) -> RuntimeResult:
    ok, _, err = http_json(f"{LLAMA_BASE}/models/load", timeout=timeout, data={"model": name})
    if not ok:
        if err and "already running" in err.lower():
            return RuntimeResult(True, f"{name} is already loaded.")
        return RuntimeResult(False, err or "llama.cpp load failed")
    return RuntimeResult(True, f"Requested llama.cpp load of {name}.")


def llama_load_with_params(name: str) -> RuntimeResult:
    """Load a GGUF using the last saved Parameters (and remembered -ngl)."""
    from machina.gpu_layers import remembered_gpu_layers
    from machina.model_params import params_for

    params = params_for(name, "llama.cpp")
    ngl = None
    if params is not None and params.num_gpu is not None and int(params.num_gpu) >= 0:
        ngl = int(params.num_gpu)
    else:
        cached = remembered_gpu_layers("llama.cpp", name)
        if cached:
            ngl = cached[0]
    if params is None and ngl is None:
        if not _llama_reachable():
            started = start_llama()
            if not started.ok:
                return started
            if not _wait_llama(20.0):
                return RuntimeResult(False, "llama serve did not come up in time.")
        return llama_load(name, timeout=180.0)
    _stop_llama_wait()
    if _llama_reachable():
        return RuntimeResult(False, "Could not stop llama serve to apply saved flags.")
    started = start_llama(ngl=ngl, params=params)
    if not started.ok:
        return started
    if not _wait_llama(20.0):
        return RuntimeResult(False, "llama serve did not come up in time.")
    loaded = llama_load(name, timeout=180.0)
    if not loaded.ok:
        return loaded
    extra = _llama_push_props(name, params) if params is not None else ""
    if extra:
        return RuntimeResult(True, f"{loaded.message} {extra}")
    return loaded


def llama_unload(name: str) -> RuntimeResult:
    ok, _, err = http_json(f"{LLAMA_BASE}/models/unload", timeout=8.0, data={"model": name})
    if not ok:
        return RuntimeResult(False, err or "llama.cpp unload failed")
    return RuntimeResult(True, f"Requested llama.cpp unload of {name}.")


def load_max_gpu(name: str, source: str = "", *, force: bool = False) -> RuntimeResult:
    from machina.gpu_layers import (
        find_llama_ngl,
        find_ollama_num_gpu,
        remembered_gpu_layers,
        resolve_llama_gguf,
    )

    if is_freetoken_source(source):
        return RuntimeResult(False, "FreeToken has no Machina GPU-layer probe.")
    if is_llama_source(source):
        path = resolve_llama_gguf(name)
        if path is None:
            return RuntimeResult(False, f"Could not find GGUF for {name!r} (set LLAMA_ARG_MODELS_DIR).")
        cached = None if force else remembered_gpu_layers("llama.cpp", name)
        if cached:
            ngl, total = cached
            applied = _apply_llama_ngl(name, ngl, total, "remembered")
            if applied.ok:
                _store_gpu_layers("llama.cpp", name, ngl, total)
                return applied
        ngl, total, detail = find_llama_ngl(path)
        if ngl <= 0:
            return RuntimeResult(False, f"Could not fit any GPU layers for {name}. {detail}")
        applied = _apply_llama_ngl(name, ngl, total, detail)
        if applied.ok:
            _store_gpu_layers("llama.cpp", name, ngl, total)
        return applied

    cached = None if force else remembered_gpu_layers("ollama", name)
    if cached:
        layers, total = cached
        loaded = ollama_load(name, num_gpu=layers)
        if loaded.ok:
            _store_gpu_layers("ollama", name, layers, total)
            shown = f"{layers}/{total}" if total else str(layers)
            return RuntimeResult(True, f"Loaded {name} with remembered num_gpu {shown}.")
    layers, total, detail = find_ollama_num_gpu(name)
    if layers <= 0:
        return RuntimeResult(False, f"Could not fit any GPU layers for {name}. {detail}")
    loaded = ollama_load(name, num_gpu=layers)
    if not loaded.ok:
        return loaded
    _store_gpu_layers("ollama", name, layers, total)
    return RuntimeResult(True, f"Loaded {name} with num_gpu {layers}/{total} — same as `/set parameter num_gpu {layers}`. {detail}.")


def _store_gpu_layers(source: str, name: str, layers: int, total: int | None) -> None:
    from machina.gpu_layers import remember_gpu_layers
    from machina.model_params import merge_num_gpu

    remember_gpu_layers(source, name, layers, total)
    merge_num_gpu(name, source, layers)


def _apply_llama_ngl(name: str, ngl: int, total: int | None, detail: str) -> RuntimeResult:
    from machina.model_params import params_for, set_llama_last

    set_llama_last(name)
    _stop_llama_wait()
    if _llama_reachable():
        return RuntimeResult(False, "Could not stop llama serve to apply -ngl.")
    started = start_llama(ngl=ngl, params=params_for(name, "llama.cpp"))
    if not started.ok:
        return started
    if not _wait_llama(20.0):
        return RuntimeResult(False, "llama serve did not come up in time.")
    loaded = llama_load(name, timeout=180.0)
    if not loaded.ok:
        return loaded
    shown = f"{ngl}/{total}" if total else str(ngl)
    return RuntimeResult(True, f"Loaded {name} with -ngl {shown} ({detail}).")


def _wait_llama(seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _llama_reachable(0.4):
            return True
        time.sleep(0.3)
    return _llama_reachable(0.4)


def _wait_ollama(seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        ok, _, _ = http_json(f"{OLLAMA_BASE}/api/version", timeout=0.4)
        if ok:
            return True
        time.sleep(0.2)
    ok, _, _ = http_json(f"{OLLAMA_BASE}/api/version", timeout=0.4)
    return bool(ok)


def service_verb(unit: str, scope: str, verb: str) -> RuntimeResult:
    if verb not in ALLOWED_VERBS:
        return RuntimeResult(False, f"Verb {verb!r} is not allowed.")
    if not is_allowed_unit(unit, scope):
        return RuntimeResult(False, f"{unit} is not on the allowlist.")
    if scope == "user":
        from machina.util import run_cmd

        code, out, err = run_cmd(["systemctl", "--user", verb, unit], timeout=8.0)
        ok = code == 0
        return RuntimeResult(ok, (out or err or f"systemctl --user {verb} {unit}").strip()[:400])
    result = apply_actions([{"op": "systemctl", "unit": unit, "scope": scope, "verb": verb}], reason=f"service:{verb}")
    return RuntimeResult(result.ok, result.message, privileged=True, cancelled=result.cancelled)
