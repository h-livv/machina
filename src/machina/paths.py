from __future__ import annotations

from pathlib import Path


def app_root() -> Path:
    return Path(__file__).resolve().parent


def assets_dir() -> Path:
    bundled = app_root() / "assets"
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parents[2] / "assets"


def icon_path() -> Path:
    return assets_dir() / "machina.svg"


def config_dir() -> Path:
    base = Path.home() / ".config" / "machina"
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_dir() -> Path:
    base = Path.home() / ".local" / "share" / "machina"
    base.mkdir(parents=True, exist_ok=True)
    return base


def guardrails_path() -> Path:
    return config_dir() / "guardrails.json"


def audit_path() -> Path:
    return data_dir() / "audit.jsonl"


def events_path() -> Path:
    return data_dir() / "events.jsonl"


def jobs_dir() -> Path:
    path = data_dir() / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def disk_cache_path() -> Path:
    return data_dir() / "disk-scan.json"


def projects_config_path() -> Path:
    return config_dir() / "projects.json"


def services_config_path() -> Path:
    return config_dir() / "services.json"


def model_params_path() -> Path:
    return config_dir() / "model-params.json"


def llama_preset_path() -> Path:
    return config_dir() / "llama-preset.ini"
