from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from machina.paths import logs_dir
from machina.util import http_json, which


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
if "://" in OLLAMA_HOST:
    OLLAMA_BASE = OLLAMA_HOST.rstrip("/")
else:
    OLLAMA_BASE = f"http://{OLLAMA_HOST}"
LLAMA_BASE = os.environ.get("LLAMA_SERVER", "http://127.0.0.1:8080")


@dataclass
class ModelWeight:
    name: str
    size_b: int | None
    digest: str | None = None
    family: str | None = None
    source: str = "ollama"


@dataclass
class LoadedModel:
    name: str
    size_vram_b: int | None
    size_b: int | None
    expires: str | None
    processor: str | None = None
    context_length: int | None = None
    source: str = "ollama"


def processor_split(size_b: int | None, size_vram_b: int | None) -> str | None:
    """CPU/GPU split as printed by `ollama ps` (ListRunningHandler)."""
    if size_b is None or size_vram_b is None:
        return None
    if size_vram_b == 0:
        return "100% CPU"
    if size_vram_b == size_b:
        return "100% GPU"
    if size_vram_b > size_b or size_b == 0:
        return "Unknown"
    cpu_percent = int((size_b - size_vram_b) / size_b * 100 + 0.5)
    return f"{cpu_percent}%/{100 - cpu_percent}% CPU/GPU"


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


@dataclass
class ModelHub:
    ollama_installed: bool
    ollama_running: bool
    ollama_version: str | None
    ollama_error: str | None
    models: list[ModelWeight] = field(default_factory=list)
    loaded: list[LoadedModel] = field(default_factory=list)
    llama_running: bool = False
    llama_error: str | None = None
    llama_models: list[str] = field(default_factory=list)
    models_dir: str | None = None
    llama_models_dir: str | None = None
    freetoken_installed: bool = False
    freetoken_running: bool = False
    freetoken_ui: bool = False
    freetoken_engine: bool = False
    freetoken_version: str | None = None
    freetoken_error: str | None = None
    freetoken_models_dir: str | None = None
    freetoken_model: str | None = None
    note: str = ""
    ts: float = 0.0
    gen_tok_s: float | None = None
    gen_tokens: int | None = None
    prompt_tok_s: float | None = None


def collect_models() -> ModelHub:
    ollama_bin = which("ollama")
    models_dir = os.environ.get("OLLAMA_MODELS")
    llama_dir = os.environ.get("LLAMA_ARG_MODELS_DIR")
    hub = ModelHub(
        ollama_installed=bool(ollama_bin),
        ollama_running=False,
        ollama_version=None,
        ollama_error=None if ollama_bin else "ollama is not on PATH",
        models_dir=models_dir,
        llama_models_dir=llama_dir,
        ts=time.time(),
    )
    disk_note = ""
    if ollama_bin:
        ok, data, err = http_json(f"{OLLAMA_BASE}/api/version", timeout=0.8)
        if ok and isinstance(data, dict):
            hub.ollama_running = True
            hub.ollama_version = str(data.get("version") or "")
            _fill_ollama(hub)
        else:
            hub.ollama_running = False
            hub.ollama_error = err or "Ollama API is not reachable"
            if models_dir:
                hub.models = _models_from_disk(models_dir)
                disk_note = (
                    f"Ollama is installed but not serving. {len(hub.models)} models on disk at {models_dir}."
                )
            else:
                disk_note = "Ollama is installed but not serving."
    _fill_llama(hub)
    _fill_freetoken(hub)
    hub.note = _compose_note(hub, disk_note)
    refresh_generation_rate(hub)
    return hub


def _fill_ollama(hub: ModelHub) -> None:
    ok, data, err = http_json(f"{OLLAMA_BASE}/api/tags", timeout=1.5)
    if not ok:
        hub.ollama_error = err
        return
    if isinstance(data, dict):
        for item in data.get("models") or []:
            if not isinstance(item, dict):
                continue
            details = item.get("details") or {}
            hub.models.append(
                ModelWeight(
                    name=str(item.get("name") or item.get("model") or ""),
                    size_b=int(item["size"]) if isinstance(item.get("size"), int) else None,
                    digest=item.get("digest"),
                    family=(details.get("family") if isinstance(details, dict) else None),
                    source="ollama",
                )
            )
    ok, data, err = http_json(f"{OLLAMA_BASE}/api/ps", timeout=1.0)
    if not ok:
        hub.ollama_error = hub.ollama_error or err
        return
    if isinstance(data, dict):
        for item in data.get("models") or []:
            if not isinstance(item, dict):
                continue
            size_vram = _as_int(item.get("size_vram"))
            size = _as_int(item.get("size"))
            hub.loaded.append(
                LoadedModel(
                    name=str(item.get("name") or item.get("model") or ""),
                    size_vram_b=size_vram,
                    size_b=size,
                    expires=str(item["expires_at"]) if item.get("expires_at") else None,
                    processor=processor_split(size, size_vram),
                    context_length=_as_int(item.get("context_length")),
                    source="ollama",
                )
            )


def ollama_layer_count(name: str) -> int | None:
    """Transformer block count from `/api/show` — the `num_gpu` ceiling for a full offload."""
    ok, data, _ = http_json(f"{OLLAMA_BASE}/api/show", timeout=8.0, data={"model": name})
    if not ok or not isinstance(data, dict):
        ok, data, _ = http_json(f"{OLLAMA_BASE}/api/show", timeout=8.0, data={"name": name})
    if not ok or not isinstance(data, dict):
        return None
    info = data.get("model_info") or {}
    if not isinstance(info, dict):
        return None
    for key, val in info.items():
        if str(key).endswith(".block_count"):
            count = _as_int(val)
            if count:
                return count
    return None


def is_llama_source(source: str | None) -> bool:
    return (source or "").lower().replace(" ", "") in {"llama.cpp", "llama", "llamacpp"}


def is_freetoken_source(source: str | None) -> bool:
    return (source or "").lower().replace(" ", "") in {"freetoken", "ft"}


def _fill_freetoken(hub: ModelHub) -> None:
    from machina.freetoken import (
        appimage_path,
        daemon_health,
        desktop_config,
        engine_status,
        list_weights,
        model_basename,
        models_dir,
        ui_running,
    )

    root = models_dir()
    hub.freetoken_models_dir = str(root)
    image = appimage_path()
    weights = list_weights(root)
    seen = {m.name for m in hub.models}
    for weight in weights:
        name = str(weight.get("name") or "")
        if not name or name in seen:
            continue
        hub.models.append(ModelWeight(name=name, size_b=None, family="freetoken", source="freetoken"))
        seen.add(name)

    health = daemon_health()
    hub.freetoken_running = bool(health.get("ok"))
    hub.freetoken_version = health.get("version") if hub.freetoken_running else None
    hub.freetoken_ui = ui_running()
    hub.freetoken_installed = bool(image or hub.freetoken_running or weights)
    if not hub.freetoken_running:
        if hub.freetoken_installed:
            hub.freetoken_error = str(health.get("error") or "FreeToken daemon is not reachable")
        else:
            hub.freetoken_error = "FreeToken AppImage not found"
        return

    status = engine_status()
    if status.get("error") and not status.get("running"):
        hub.freetoken_error = str(status.get("error"))
        return
    name = model_basename(status.get("model") if isinstance(status.get("model"), str) else None)
    last = desktop_config().get("lastActiveId")
    hub.freetoken_model = name or (str(last) if isinstance(last, str) and last else None)
    busy = bool(status.get("running") or status.get("starting") or status.get("stopping"))
    hub.freetoken_engine = busy
    if not busy:
        return
    phase = "engine"
    if status.get("starting"):
        phase = "starting"
    elif status.get("stopping"):
        phase = "stopping"
    pid = status.get("pid")
    processor = f"{phase} pid {pid}" if pid else phase
    uptime = status.get("uptime_s")
    expires = f"up {int(uptime)}s" if isinstance(uptime, (int, float)) and uptime else None
    shown = name or "freetoken"
    hub.loaded.append(
        LoadedModel(
            name=shown,
            size_vram_b=None,
            size_b=None,
            expires=expires,
            processor=processor,
            context_length=None,
            source="freetoken",
        )
    )


def _compose_note(hub: ModelHub, disk_note: str) -> str:
    bits: list[str] = []
    if disk_note:
        bits.append(disk_note)
    ollama_loaded = [
        m for m in hub.loaded if not is_llama_source(m.source) and not is_freetoken_source(m.source)
    ]
    if hub.ollama_running and ollama_loaded:
        bits.append("Ollama has loaded: " + ", ".join(m.name for m in ollama_loaded))
    elif hub.ollama_running:
        bits.append("Ollama is idle — no model is resident in VRAM.")
    elif not hub.ollama_running and hub.ollama_installed and not disk_note:
        bits.append("Ollama is installed but not serving.")
    if hub.llama_running:
        names = ", ".join(hub.llama_models) if hub.llama_models else "llama serve"
        bits.append(f"llama.cpp: {names}")
    if hub.freetoken_engine:
        bits.append(f"FreeToken engine: {hub.freetoken_model or 'running'}")
    elif hub.freetoken_running:
        last = f" (last {hub.freetoken_model})" if hub.freetoken_model else ""
        bits.append(f"FreeToken daemon is up; engine idle{last}")
    elif hub.freetoken_ui:
        bits.append("FreeToken UI is running")
    elif hub.freetoken_error and hub.freetoken_installed:
        bits.append(hub.freetoken_error)
    if not bits and hub.ollama_installed and not hub.ollama_running and not hub.llama_running:
        bits.append("No local model server is listening.")
    return "  ·  ".join(bits)


def _fill_llama(hub: ModelHub) -> None:
    ok, data, _ = http_json(f"{LLAMA_BASE}/models", timeout=0.5)
    if not ok:
        ok, data, _ = http_json(f"{LLAMA_BASE}/v1/models", timeout=0.4)
    if ok and isinstance(data, dict):
        hub.llama_running = True
        names: list[str] = []
        seen = {m.name for m in hub.models}
        for item in data.get("data") or data.get("models") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("id") or item.get("name") or "")
            if not name:
                continue
            names.append(name)
            status = _llama_status(item)
            if status in {"loaded", "loading", "sleeping", "running"}:
                hub.loaded.append(
                    LoadedModel(
                        name=name,
                        size_vram_b=None,
                        size_b=None,
                        expires=None,
                        processor="GPU auto-fit",
                        context_length=None,
                        source="llama.cpp",
                    )
                )
            if name not in seen:
                hub.models.append(
                    ModelWeight(name=name, size_b=None, family="gguf", source="llama.cpp")
                )
                seen.add(name)
        hub.llama_models = names
        if hub.llama_models_dir:
            for weight in _llama_from_disk(hub.llama_models_dir):
                if weight.name not in seen:
                    hub.models.append(weight)
                    seen.add(weight.name)
        return
    hub.llama_running = False
    if hub.llama_models_dir:
        disk = _llama_from_disk(hub.llama_models_dir)
        hub.models.extend(disk)
        hub.llama_models = [m.name for m in disk]


def _llama_status(item: dict) -> str:
    status = item.get("status")
    if isinstance(status, dict):
        return str(status.get("value") or "")
    return str(status or "")


def _llama_from_disk(models_dir: str) -> list[ModelWeight]:
    root = Path(models_dir)
    if not root.is_dir():
        return []
    found: list[ModelWeight] = []
    try:
        paths = sorted(root.glob("*.gguf"))
    except OSError:
        return []
    for path in paths[:80]:
        name = path.name
        lower = name.lower()
        if "-of-" in lower and "00001-of-" not in lower:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        found.append(ModelWeight(name=name, size_b=size, family="gguf", source="llama.cpp"))
    return found


def _models_from_disk(models_dir: str) -> list[ModelWeight]:
    import json

    root = Path(models_dir) / "manifests"
    if not root.is_dir():
        return []
    found: list[ModelWeight] = []
    try:
        manifests = [p for p in root.rglob("*") if p.is_file()]
    except OSError:
        return []
    for manifest in manifests[:80]:
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rel = str(manifest.relative_to(root))
            found.append(ModelWeight(name=rel, size_b=None, source="disk"))
            continue
        rel = str(manifest.relative_to(root))
        size = 0
        for layer in data.get("layers") or []:
            if isinstance(layer, dict) and isinstance(layer.get("size"), int):
                size += layer["size"]
        cfg = data.get("config")
        if isinstance(cfg, dict) and isinstance(cfg.get("size"), int):
            size += cfg["size"]
        found.append(
            ModelWeight(
                name=rel.replace("registry.ollama.ai/library/", ""),
                size_b=size or None,
                digest=(data.get("config") or {}).get("digest") if isinstance(data.get("config"), dict) else None,
                source="disk",
            )
        )
    found.sort(key=lambda m: m.name)
    return found


def ollama_log_path() -> Path:
    return logs_dir() / "ollama.log"


def llama_log_path() -> Path:
    return logs_dir() / "llama-serve.log"


_LOG_TAIL = 196608
_GEN_TG = re.compile(
    r"n_decoded\s*=\s*(?P<n>\d+)\s*,\s*tg\s*=\s*(?P<tps>[\d.]+)\s*t/s",
    re.IGNORECASE,
)
_GEN_EVAL = re.compile(
    r"(?<!prompt )eval time\s*=\s*[\d.]+\s*ms\s*/\s*(?P<n>\d+)\s*tokens\s*\([^)]*?,\s*(?P<tps>[\d.]+)\s*tokens per second",
    re.IGNORECASE,
)
_PREFILL = re.compile(
    r"prompt eval time\s*=\s*[\d.]+\s*ms\s*/\s*(?P<n>\d+)\s*tokens\s*\([^)]*?,\s*(?P<tps>[\d.]+)\s*tokens per second",
    re.IGNORECASE,
)
_GIN_TS = re.compile(r"\[GIN\]\s+(\d{4}/\d{2}/\d{2})\s+-\s+(\d{2}:\d{2}:\d{2})")


def refresh_generation_rate(hub: ModelHub) -> None:
    """Last generate tok/s from ollama/llama serve logs (`ollama run` in a terminal, etc.)."""
    gen, n, prefill = last_generation_rate()
    hub.gen_tok_s = gen
    hub.gen_tokens = n
    hub.prompt_tok_s = prefill


_LOG_SIG: tuple[tuple[int, int], tuple[int, int]] | None = None
_LOG_CACHE: tuple[float | None, int | None, float | None] = (None, None, None)


def last_generation_rate() -> tuple[float | None, int | None, float | None]:
    global _LOG_SIG, _LOG_CACHE
    sig: list[tuple[int, int]] = []
    for path in (ollama_log_path(), llama_log_path()):
        try:
            st = path.stat()
            sig.append((st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((0, 0))
    packed = (sig[0], sig[1])
    if packed == _LOG_SIG:
        return _LOG_CACHE
    scored: list[tuple[float, float, int, float, int | None, float | None]] = []
    for path in (ollama_log_path(), llama_log_path()):
        text = _tail_text(path)
        parsed = _parse_generation_rate(text)
        if parsed is None:
            continue
        pos, gen, n, prefill = parsed
        scored.append((_timestamp_before(text, pos), _log_mtime(path), pos, gen, n, prefill))
    if not scored:
        _LOG_SIG = packed
        _LOG_CACHE = (None, None, None)
        return _LOG_CACHE
    if any(row[0] > 0 for row in scored):
        scored.sort(key=lambda row: (row[0], row[2]))
    else:
        scored.sort(key=lambda row: (row[1], row[2]))
    *_, gen, n, prefill = scored[-1]
    _LOG_SIG = packed
    _LOG_CACHE = (gen, n, prefill)
    return _LOG_CACHE


def _log_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _timestamp_before(text: str, pos: int) -> float:
    chunk = text[max(0, pos - 1200) : pos]
    last = None
    for match in _GIN_TS.finditer(chunk):
        last = match
    if last is None:
        return 0.0
    try:
        return time.mktime(time.strptime(f"{last.group(1)} {last.group(2)}", "%Y/%m/%d %H:%M:%S"))
    except ValueError:
        return 0.0


def _tail_text(path: Path, nbytes: int = _LOG_TAIL) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - nbytes))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _parse_generation_rate(text: str) -> tuple[int, float, int | None, float | None] | None:
    hits: list[tuple[int, float, int | None]] = []
    for match in _GEN_TG.finditer(text):
        hits.append((match.start(), float(match.group("tps")), int(match.group("n"))))
    for match in _GEN_EVAL.finditer(text):
        hits.append((match.start(), float(match.group("tps")), int(match.group("n"))))
    if not hits:
        return None
    hits.sort(key=lambda h: h[0])
    pos, gen, n = hits[-1]
    prefill: float | None = None
    for match in _PREFILL.finditer(text):
        if match.start() <= pos:
            prefill = float(match.group("tps"))
    return pos, gen, n, prefill
