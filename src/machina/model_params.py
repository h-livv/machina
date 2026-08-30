"""Per-model `/set` parameters for Ollama and llama.cpp, saved under ~/.config/machina/."""
from __future__ import annotations

import json
from configparser import ConfigParser
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from machina.models import OLLAMA_BASE, is_llama_source
from machina.paths import llama_preset_path, model_params_path
from machina.util import http_json


@dataclass
class ModelParams:
    num_predict: int | None = -1
    top_k: int | None = 40
    top_p: float | None = 0.9
    min_p: float | None = 0.0
    num_ctx: int | None = 4096
    temperature: float | None = 0.8
    num_gpu: int | None = None
    think: bool | None = True
    system: str = ""

    def options(self) -> dict:
        out: dict = {}
        if self.num_predict is not None:
            out["num_predict"] = int(self.num_predict)
        if self.top_k is not None:
            out["top_k"] = int(self.top_k)
        if self.top_p is not None:
            out["top_p"] = float(self.top_p)
        if self.min_p is not None:
            out["min_p"] = float(self.min_p)
        if self.num_ctx is not None:
            out["num_ctx"] = int(self.num_ctx)
        if self.temperature is not None:
            out["temperature"] = float(self.temperature)
        if self.num_gpu is not None and int(self.num_gpu) >= 0:
            out["num_gpu"] = int(self.num_gpu)
        return out


def _store() -> dict:
    path = model_params_path()
    if not path.is_file():
        return {"history": True, "models": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"history": True, "models": {}}
    if not isinstance(data, dict):
        return {"history": True, "models": {}}
    models = data.get("models")
    if not isinstance(models, dict):
        data["models"] = {}
    return data


def _write_store(data: dict) -> None:
    path = model_params_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def history_enabled() -> bool:
    return bool(_store().get("history", True))


def set_history(enabled: bool) -> None:
    data = _store()
    data["history"] = bool(enabled)
    _write_store(data)


def params_key(source: str, name: str) -> str:
    if is_llama_source(source):
        return f"llama.cpp:{name}"
    return name


def llama_last_model() -> str | None:
    last = _store().get("llama_last")
    return str(last) if last else None


def set_llama_last(name: str) -> None:
    data = _store()
    data["llama_last"] = name
    _write_store(data)


def params_for(name: str, source: str = "") -> ModelParams | None:
    models = _store().get("models") or {}
    if not isinstance(models, dict):
        return None
    key = params_key(source, name)
    raw = models.get(key)
    if raw is None and not is_llama_source(source):
        raw = models.get(name)
    if isinstance(raw, dict):
        return _from_dict(raw)
    return None


def save_params(name: str, params: ModelParams, source: str = "") -> None:
    data = _store()
    models = data.setdefault("models", {})
    models[params_key(source, name)] = asdict(params)
    if is_llama_source(source):
        data["llama_last"] = name
    _write_store(data)


def merge_num_gpu(name: str, source: str, layers: int) -> None:
    params = params_for(name, source) or ModelParams()
    params.num_gpu = int(layers)
    save_params(name, params, source)


def _from_dict(raw: dict) -> ModelParams:
    allowed = {f.name for f in fields(ModelParams)}
    kwargs: dict = {}
    for key, val in raw.items():
        if key not in allowed:
            continue
        kwargs[key] = val
    return ModelParams(**kwargs)


def parse_parameter_block(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[0]] = parts[1].strip()
    return out


def _as_int(value: object) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def from_show(name: str, source: str = "") -> ModelParams:
    """Defaults from the backend, then overlay Machina's saved values."""
    if is_llama_source(source):
        params = params_for(name, source) or ModelParams()
        if params.num_gpu is None:
            from machina.gpu_layers import remembered_gpu_layers

            cached = remembered_gpu_layers("llama.cpp", name)
            if cached:
                params.num_gpu = cached[0]
        return params
    params = ModelParams()
    ok, data, _ = http_json(f"{OLLAMA_BASE}/api/show", timeout=3.0, data={"model": name})
    if ok and isinstance(data, dict):
        parsed = parse_parameter_block(str(data.get("parameters") or ""))
        if "num_predict" in parsed:
            params.num_predict = _as_int(parsed["num_predict"])
        if "top_k" in parsed:
            params.top_k = _as_int(parsed["top_k"])
        if "top_p" in parsed:
            params.top_p = _as_float(parsed["top_p"])
        if "min_p" in parsed:
            params.min_p = _as_float(parsed["min_p"])
        if "num_ctx" in parsed:
            params.num_ctx = _as_int(parsed["num_ctx"])
        if "temperature" in parsed:
            params.temperature = _as_float(parsed["temperature"])
        if "num_gpu" in parsed:
            params.num_gpu = _as_int(parsed["num_gpu"])
        if "think" in parsed:
            params.think = _as_bool(parsed["think"])
        system = data.get("system")
        if isinstance(system, str):
            params.system = system
        caps = data.get("capabilities") or []
        if params.think is None and isinstance(caps, list) and "thinking" in caps:
            params.think = True
    saved = params_for(name, source)
    if saved is not None:
        overlay = asdict(saved)
        for field in fields(ModelParams):
            if field.name in overlay:
                setattr(params, field.name, getattr(saved, field.name))
    return params


def llama_serve_flags(params: ModelParams | None, ngl: int | None = None) -> list[str]:
    """CLI flags for `llama serve` that match the Parameters tab."""
    flags = ["--props"]
    preset = llama_preset_path()
    if preset.is_file():
        flags.extend(["--models-preset", str(preset)])
    gpu = ngl
    if gpu is None and params is not None and params.num_gpu is not None and int(params.num_gpu) >= 0:
        gpu = int(params.num_gpu)
    if gpu is not None:
        flags.extend(["-ngl", str(gpu), "--fit", "off"])
    else:
        flags.extend(["-ngl", "auto", "--fit", "on", "--fit-target", "256"])
    if params is not None:
        if params.num_ctx is not None:
            flags.extend(["-c", str(int(params.num_ctx))])
        if params.num_predict is not None:
            flags.extend(["-n", str(int(params.num_predict))])
        if params.temperature is not None:
            flags.extend(["--temp", str(params.temperature)])
        if params.top_k is not None:
            flags.extend(["--top-k", str(int(params.top_k))])
        if params.top_p is not None:
            flags.extend(["--top-p", str(params.top_p)])
        if params.min_p is not None:
            flags.extend(["--min-p", str(params.min_p)])
        if params.think is True:
            flags.extend(["--reasoning", "on"])
        elif params.think is False:
            flags.extend(["--reasoning", "off"])
    if not history_enabled():
        flags.append("--no-cache-prompt")
    return flags


def write_llama_preset(name: str, params: ModelParams) -> Path:
    """Write/update a llama.cpp `--models-preset` section for this GGUF."""
    from machina.gpu_layers import resolve_llama_gguf

    path = llama_preset_path()
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    if path.is_file():
        parser.read(path, encoding="utf-8")
    if parser.has_section(name):
        parser.remove_section(name)
    parser.add_section(name)
    gguf = resolve_llama_gguf(name)
    if gguf is not None:
        parser.set(name, "model", str(gguf))
    if params.num_ctx is not None:
        parser.set(name, "ctx-size", str(int(params.num_ctx)))
    if params.num_predict is not None:
        parser.set(name, "n-predict", str(int(params.num_predict)))
    if params.num_gpu is not None and int(params.num_gpu) >= 0:
        parser.set(name, "n-gpu-layers", str(int(params.num_gpu)))
    else:
        parser.set(name, "n-gpu-layers", "auto")
    if params.temperature is not None:
        parser.set(name, "temp", str(params.temperature))
    if params.top_k is not None:
        parser.set(name, "top-k", str(int(params.top_k)))
    if params.top_p is not None:
        parser.set(name, "top-p", str(params.top_p))
    if params.min_p is not None:
        parser.set(name, "min-p", str(params.min_p))
    if params.think is True:
        parser.set(name, "reasoning", "on")
    elif params.think is False:
        parser.set(name, "reasoning", "off")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    return path


def to_modelfile(name: str, params: ModelParams) -> str:
    lines = [f"FROM {name}"]
    opts = params.options()
    for key in ("num_predict", "top_k", "top_p", "min_p", "num_ctx", "temperature", "num_gpu"):
        if key in opts:
            lines.append(f"PARAMETER {key} {opts[key]}")
    if params.think is True:
        lines.append("PARAMETER think true")
    elif params.think is False:
        lines.append("PARAMETER think false")
    system = (params.system or "").strip()
    if system:
        escaped = system.replace('"""', "'''")
        lines.append(f'SYSTEM """\n{escaped}\n"""')
    return "\n".join(lines) + "\n"


def params_from_payload(raw: dict) -> ModelParams:
    return _from_dict(raw)
