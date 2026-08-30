"""Find the highest GPU layer count that actually fits in VRAM.

Ollama's auto estimator is conservative; people end up doing
`/set parameter num_gpu N` by trial and error. This module probes that N
the same way the REPL does, scoring a load by the last `offloaded X/Y`
line and a resident runner — not by OOM strings left over from a recovered
vision-projector retry.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from machina.models import OLLAMA_BASE, _as_int, ollama_layer_count, ollama_log_path
from machina.paths import config_dir
from machina.util import http_json, run_cmd, which


OFFLOAD_RE = re.compile(r"offloaded\s+(\d+)\s*/\s*(\d+)\s+layers", re.I)
N_LAYER_RE = re.compile(r"n_layer(?:_all)?\s*=\s*(\d+)", re.I)
OOM_MARKERS = (
    "out of memory",
    "cuda malloc",
    "cudamalloc",
    "insufficient memory",
    "failed to allocate",
    "ggml_gallocr",
    "cuda error",
    "hipblas",
)


CACHE_VERSION = 2


def gpu_layers_cache_path() -> Path:
    return config_dir() / "gpu-layers.json"


def _cache_key(source: str, name: str) -> str:
    return f"{source}:{name}"


def _read_gpu_layers_cache() -> dict:
    path = gpu_layers_cache_path()
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def remembered_gpu_layers(source: str, name: str) -> tuple[int, int | None] | None:
    """Saved max `num_gpu` / `-ngl` for this model, if we trust the entry."""
    entry = _read_gpu_layers_cache().get(_cache_key(source, name))
    if not isinstance(entry, dict):
        return None
    layers = entry.get("layers")
    if not isinstance(layers, int) or layers <= 0:
        return None
    total = entry.get("total")
    total_i = total if isinstance(total, int) else None
    version = entry.get("v")
    if isinstance(version, int) and version >= CACHE_VERSION:
        return layers, total_i
    # Unversioned file: keep real partial offloads (e.g. 41/66). Skip N/N —
    # that was the old search capping at block_count (32/32).
    if total_i is not None and layers != total_i:
        return layers, total_i
    return None


def parse_offload(text: str) -> tuple[int, int] | None:
    found: tuple[int, int] | None = None
    for match in OFFLOAD_RE.finditer(text):
        found = (int(match.group(1)), int(match.group(2)))
    return found


def is_oom_text(text: str) -> bool:
    blob = text.lower()
    return any(marker in blob for marker in OOM_MARKERS)


def highest_fitting(
    low: int,
    high: int,
    probe: Callable[[int], bool],
) -> int:
    """Highest n in [low, high] where probe(n) is True."""
    best = low - 1
    lo = low
    hi = high
    while lo <= hi:
        mid = (lo + hi) // 2
        if probe(mid):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _log_offset(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _log_since(path: Path, offset: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            return handle.read()
    except OSError:
        return ""


def _ollama_generate(name: str, num_gpu: int | None, keep_alive: int, timeout: float) -> tuple[bool, str]:
    body: dict = {"model": name, "prompt": "", "keep_alive": keep_alive, "stream": False}
    if num_gpu is not None:
        body["options"] = {"num_gpu": num_gpu}
    ok, data, err = http_json(f"{OLLAMA_BASE}/api/generate", timeout=timeout, data=body)
    if not ok:
        return False, err or ""
    if isinstance(data, dict) and data.get("error"):
        return False, str(data.get("error"))[:240]
    return True, ""


def _ollama_ps(name: str) -> dict | None:
    ok, data, _ = http_json(f"{OLLAMA_BASE}/api/ps", timeout=1.5)
    if not ok or not isinstance(data, dict):
        return None
    items: list[tuple[str, dict]] = []
    for item in data.get("models") or []:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("name") or item.get("model") or "")
        if tag:
            items.append((tag, item))
    for tag, item in items:
        if tag == name:
            return item
    for tag, item in items:
        if name in tag or tag in name:
            return item
    if len(items) == 1:
        return items[0][1]
    return None


def _fully_on_gpu(entry: dict | None) -> bool:
    if not entry:
        return False
    size = _as_int(entry.get("size"))
    vram = _as_int(entry.get("size_vram"))
    if size is None or vram is None or size <= 0:
        return False
    return vram >= size


def _ollama_unload(name: str) -> None:
    http_json(
        f"{OLLAMA_BASE}/api/generate",
        timeout=8.0,
        data={"model": name, "prompt": "", "keep_alive": 0, "stream": False},
    )


def _ollama_unload_all() -> None:
    ok, data, _ = http_json(f"{OLLAMA_BASE}/api/ps", timeout=1.5)
    if not ok or not isinstance(data, dict):
        return
    for item in data.get("models") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "")
        if name:
            _ollama_unload(name)


@dataclass
class _OllamaProbe:
    loaded: bool
    offloaded: int | None
    llm_layers: int | None
    fully_ps: bool


def _run_ollama_probe(name: str, num_gpu: int | None, log_path: Path, timeout: float) -> _OllamaProbe:
    """Load once. Ollama may OOM the mmproj, retry with it on CPU, and still serve.

    That first cudaMalloc failure must not count as "does not fit".
    """
    _ollama_unload(name)
    time.sleep(0.35)
    offset = _log_offset(log_path)
    ok, _err = _ollama_generate(name, num_gpu, 20, timeout)
    chunk = _log_since(log_path, offset)
    time.sleep(0.25)
    entry = _ollama_ps(name)
    parsed = parse_offload(chunk)
    # Resident runner is the signal. Log OOM from a recovered mmproj retry is ignored.
    loaded = bool(entry) or (ok and parsed is not None)
    if not loaded:
        time.sleep(0.7)
    return _OllamaProbe(
        loaded=loaded,
        offloaded=parsed[0] if parsed else None,
        llm_layers=parsed[1] if parsed else None,
        fully_ps=_fully_on_gpu(entry),
    )


def _llm_complete(probe: _OllamaProbe) -> bool:
    if probe.offloaded is None or probe.llm_layers is None:
        return False
    return probe.offloaded >= probe.llm_layers


def find_ollama_num_gpu(name: str, timeout: float = 90.0) -> tuple[int, int, str]:
    """Find `/set parameter num_gpu N` the way a human would, not via log OOM.

    `qwen35.block_count` is 32; llama.cpp logs `offloaded 32/33` — the extra
    slot is the output head. 33 (or 35) is a full LLM offload. A vision
    projector OOM + `--no-mmproj-offload` retry still counts as success.
    """
    blocks = ollama_layer_count(name)
    log_path = ollama_log_path()
    _ollama_unload_all()
    time.sleep(0.4)

    def probe(n: int | None) -> _OllamaProbe:
        return _run_ollama_probe(name, n, log_path, timeout)

    auto = probe(None)
    llm_n = auto.llm_layers or ((blocks + 1) if blocks else 32)
    auto_off = auto.offloaded or 0
    best_n = 0
    best_off = 0

    def consider(n: int, result: _OllamaProbe) -> None:
        nonlocal best_n, best_off, llm_n
        if result.llm_layers:
            llm_n = result.llm_layers
        if not result.loaded:
            return
        off = result.offloaded if result.offloaded is not None else 0
        if off > best_off:
            best_off = off
            best_n = n
        elif off == best_off and off > 0 and (best_n == 0 or n < best_n):
            best_n = n
        elif best_n == 0:
            best_n = n

    consider(auto_off, auto)
    if _llm_complete(auto):
        _ollama_unload(name)
        return llm_n, llm_n, f"auto already offloaded {auto.offloaded}/{auto.llm_layers}"

    full = probe(llm_n)
    consider(llm_n, full)
    if full.loaded and _llm_complete(full):
        _ollama_unload(name)
        return llm_n, llm_n, f"offloaded {full.offloaded}/{full.llm_layers} (block_count {blocks})"

    if not full.loaded:
        def fits(n: int) -> bool:
            result = probe(n)
            consider(n, result)
            return result.loaded

        found = highest_fitting(max(auto_off, 1), max(llm_n - 1, 1), fits)
        _ollama_unload(name)
        if found < 1:
            return 0, llm_n, "could not keep a runner resident"
        return found, llm_n, f"offloaded {best_off}/{llm_n}; {llm_n} did not stay loaded"

    # Loaded at llama.cpp's layer count but still not X/Y — climb a few, like num_gpu 35.
    stall = 0
    for n in range(llm_n + 1, llm_n + 9):
        result = probe(n)
        if not result.loaded:
            break
        prev = best_off
        consider(n, result)
        if _llm_complete(result) or result.fully_ps:
            _ollama_unload(name)
            return n, llm_n, f"offloaded {result.offloaded}/{result.llm_layers or llm_n}"
        if best_off > prev:
            stall = 0
        else:
            stall += 1
            if stall >= 2:
                break

    _ollama_unload(name)
    note = f"offloaded {best_off}/{llm_n}"
    if auto.fully_ps or full.fully_ps:
        note += "; ollama ps 100% GPU"
    return best_n, llm_n, note


def resolve_llama_gguf(name: str) -> Path | None:
    candidate = Path(name)
    if candidate.is_file():
        return candidate
    models_dir = os.environ.get("LLAMA_ARG_MODELS_DIR")
    if not models_dir:
        return None
    root = Path(models_dir)
    direct = root / name
    if direct.is_file():
        return direct
    if not name.endswith(".gguf"):
        alt = root / f"{name}.gguf"
        if alt.is_file():
            return alt
    try:
        matches = sorted(root.glob(f"{name}*"))
    except OSError:
        return None
    files = [p for p in matches if p.is_file() and p.suffix.lower() == ".gguf"]
    return files[0] if files else None


def find_llama_ngl(model_path: Path, timeout: float = 120.0) -> tuple[int, int, str]:
    """Binary-search `-ngl` with `llama cli --fit off`, same idea as Ollama num_gpu."""
    binary = which("llama")
    if not binary:
        return 0, 0, "llama is not installed"

    def run(args: list[str]) -> tuple[int, str]:
        code, out, err = run_cmd([binary, "cli", *args], timeout=timeout)
        return code, f"{out}\n{err}"

    code, text = run(
        [
            "-m",
            str(model_path),
            "-ngl",
            "auto",
            "--fit",
            "on",
            "--fit-target",
            "32",
            "-n",
            "1",
            "--no-display-prompt",
            "-p",
            ".",
        ]
    )
    parsed = parse_offload(text)
    n_layer_match = N_LAYER_RE.search(text)
    total = parsed[1] if parsed else (int(n_layer_match.group(1)) if n_layer_match else 32)
    floor = parsed[0] if parsed and code == 0 and not is_oom_text(text) else 0
    cap = max(total + 16, 48)

    def probe(mid: int) -> bool:
        probe_code, probe_text = run(
            [
                "-m",
                str(model_path),
                "-ngl",
                str(mid),
                "--fit",
                "off",
                "-n",
                "1",
                "--no-display-prompt",
                "-p",
                ".",
            ]
        )
        return probe_code == 0 and not is_oom_text(probe_text)

    best = highest_fitting(max(floor, 1), cap, probe)
    best = max(best, floor)
    return best, total, f"binary-searched -ngl up to {cap}"


def remember_gpu_layers(source: str, name: str, layers: int, total: int | None) -> None:
    path = gpu_layers_cache_path()
    data = _read_gpu_layers_cache()
    data[_cache_key(source, name)] = {
        "layers": layers,
        "total": total,
        "ts": time.time(),
        "v": CACHE_VERSION,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
