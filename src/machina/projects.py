from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from machina.paths import projects_config_path


SCAN_ROOTS = (Path.home() / "Projects", Path.home() / "Labs", Path.home() / "opt" / "machina")
SKIP_NAMES = {"misc", "__pycache__", "node_modules", ".venv"}


@dataclass
class Task:
    id: str
    title: str
    argv: list[str]
    group: str
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    needs_venv: bool = True
    note: str = ""


@dataclass
class Project:
    name: str
    path: str
    kind: str
    venv: str | None
    tasks: list[Task]
    note: str = ""


def discover_projects() -> list[Project]:
    found: list[Project] = []
    extra = _config_roots()
    roots = list(SCAN_ROOTS) + extra
    seen: set[Path] = set()
    for root in roots:
        try:
            root = root.expanduser().resolve()
        except OSError:
            continue
        if not root.exists() or not root.is_dir():
            continue
        children: list[Path]
        if root.name in {"Projects", "Labs"}:
            try:
                children = [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP_NAMES]
            except OSError:
                children = []
        else:
            children = [root]
        for path in children:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(_inspect(path))
    found.sort(key=lambda p: p.name.lower())
    return found


def _config_roots() -> list[Path]:
    path = projects_config_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    roots: list[Path] = []
    if isinstance(data, dict):
        for item in data.get("roots") or []:
            roots.append(Path(str(item)))
    return roots


def _inspect(path: Path) -> Project:
    name = path.name
    venv = path / ".venv" / "bin" / "python"
    venv_s = str(venv) if venv.exists() else None
    kind = _kind(path)
    tasks = _tasks(path, name)
    note = ""
    readme = path / "README.md"
    if readme.exists():
        try:
            first = readme.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in first[:8]:
                if line.startswith("# "):
                    note = line[2:].strip()
                    break
        except OSError:
            pass
    return Project(name=name, path=str(path), kind=kind, venv=venv_s, tasks=tasks, note=note)


def _kind(path: Path) -> str:
    if (path / "CMakeLists.txt").exists():
        return "cmake"
    if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists() or (path / "main.py").exists():
        return "python"
    if (path / "package.json").exists():
        return "node"
    if (path / "Cargo.toml").exists():
        return "rust"
    return "dir"


def _tasks(path: Path, name: str) -> list[Task]:
    tasks: list[Task] = []
    justfile = path / "justfile" if (path / "justfile").exists() else path / "Justfile"
    if justfile.exists():
        tasks.extend(_just_tasks(path, justfile))
    tasks.extend(_recipe_tasks(path, name))
    tasks.extend(_pyproject_scripts(path))
    tasks.extend(_cmake_tasks(path))
    if (path / "package.json").exists():
        tasks.extend(_npm_tasks(path))
    # de-dupe by id
    seen: set[str] = set()
    out: list[Task] = []
    for task in tasks:
        if task.id in seen:
            continue
        seen.add(task.id)
        out.append(task)
    return out


def _just_tasks(path: Path, justfile: Path) -> list[Task]:
    tasks: list[Task] = []
    try:
        text = justfile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return tasks
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        if ":" in stripped and not stripped.startswith("@") and not stripped.startswith("export"):
            recipe = stripped.split(":", 1)[0].strip()
            if recipe and " " not in recipe and recipe.replace("-", "_").isidentifier():
                if recipe in {"set", "alias", "import"}:
                    continue
                tasks.append(
                    Task(
                        id=f"{path.name}:just:{recipe}",
                        title=recipe,
                        argv=["just", recipe],
                        group="just",
                        cwd=str(path),
                        needs_venv=False,
                        note="From justfile",
                    )
                )
    return tasks[:30]


def _recipe_tasks(path: Path, name: str) -> list[Task]:
    key = name.lower()
    cwd = str(path)
    recipes: dict[str, list[Task]] = {
        "tempest": _tempest_tasks(path),
        "janus": [
            Task(f"{key}:collision", "Collision", ["python", "collision/run.py"], "run", cwd),
            Task(f"{key}:transport", "Transport", ["python", "transport/run.py"], "run", cwd),
            Task(f"{key}:test-transport", "Test transport", ["python", "-m", "pytest", "tests/transport/"], "test", cwd),
            Task(f"{key}:validate", "Validate collision", ["python", "collision/validation/validate.py"], "test", cwd),
            Task(f"{key}:physics", "Collision phenomenology", ["python", "collision/validation/physical_validation.py"], "test", cwd),
        ],
        "penrose": [
            Task(f"{key}:build", "Build", ["cmake", "--build", "build"], "build", cwd, needs_venv=False),
            Task(f"{key}:benchmark", "Benchmark", [_binary(path, "physics_benchmark")], "benchmark", cwd, needs_venv=False, note="CPU geodesic benchmark"),
            Task(f"{key}:viewer", "Viewer", [_binary(path, "visualization_viewer")], "run", cwd, needs_venv=False),
            Task(f"{key}:export", "Export frames", [_binary(path, "visualization_export")], "run", cwd, needs_venv=False),
            Task(f"{key}:plot", "Plot benchmarks", ["python", "physics/analysis/plot_benchmarks.py"], "plots", cwd),
        ],
        "sgl": [
            Task(f"{key}:build", "Build", ["cmake", "--build", "build"], "build", cwd, needs_venv=False),
            Task(f"{key}:test", "Test", ["ctest", "--test-dir", "build", "--output-on-failure"], "test", cwd, needs_venv=False),
            Task(
                f"{key}:canonical",
                "Canonical image",
                [_binary(path, "sgl_canonical_sgl_image"), "--output-dir", "outputs/sgl_forward"],
                "run",
                cwd,
                needs_venv=False,
            ),
            Task(f"{key}:sweep", "Parameter sweep", ["python3", "experiments/parameter_sweep.py"], "experiment", cwd, needs_venv=False),
        ],
        "geantpy": [
            Task(f"{key}:run", "Run simulation", ["python", "run/run.py"], "run", cwd),
            Task(f"{key}:batches", "Run batches", ["python", "run/run_batches.py"], "run", cwd),
        ],
        "lattice-gauge-qcd": [
            Task(f"{key}:lgt", "Launch lgt", ["lgt"], "run", cwd),
            Task(f"{key}:test", "Test", ["python", "-m", "pytest"], "test", cwd),
        ],
        "nanofiber-lab": [
            Task(f"{key}:nlab", "Launch nlab", ["nlab"], "run", cwd),
            Task(f"{key}:test", "Test", ["python", "-m", "pytest"], "test", cwd),
        ],
        "mechint-lab": [
            Task(f"{key}:mechint", "Launch mechint", ["mechint"], "run", cwd),
            Task(f"{key}:test", "Test", ["python", "-m", "pytest"], "test", cwd),
        ],
        "machina": [
            Task(f"{key}:run", "Open Machina", ["python", "-m", "machina"], "run", cwd, needs_venv=False),
            Task(f"{key}:once", "Telemetry snapshot", ["python", "-m", "machina", "--once"], "run", cwd, needs_venv=False),
        ],
    }
    extra: list[Task] = []
    if (path / "test_simulation.py").exists() and key != "tempest":
        extra.append(Task(f"{key}:test_simulation", "test_simulation.py", ["python", "test_simulation.py"], "test", cwd))
    if (path / "tests").is_dir() and not any(t.group == "test" for t in recipes.get(key, [])):
        extra.append(Task(f"{key}:pytest", "pytest", ["python", "-m", "pytest"], "test", cwd))
    return recipes.get(key, []) + extra


def _tempest_tasks(path: Path) -> list[Task]:
    cwd = str(path)
    tasks = [
        Task("tempest:test", "Test simulation", ["python", "test_simulation.py"], "test", cwd),
    ]
    configs = path / "configs"
    if configs.is_dir():
        for cfg in sorted(configs.rglob("*.py")):
            if "__pycache__" in cfg.parts or cfg.name.startswith("_"):
                continue
            rel = cfg.relative_to(path)
            rel_cfg = cfg.relative_to(configs)
            group = rel_cfg.parts[1] if len(rel_cfg.parts) > 1 else cfg.stem
            kind = cfg.stem
            title = f"{kind} · {'/'.join(rel_cfg.parts[:-1])}" if rel_cfg.parts[:-1] else kind
            tasks.append(
                Task(
                    id=f"tempest:{rel}",
                    title=title,
                    argv=["python", "main.py", str(rel)],
                    group=kind,
                    cwd=cwd,
                    note=str(rel),
                )
            )
    surrogate = path / "surrogate" / "experiments"
    if surrogate.is_dir():
        for run in sorted(surrogate.glob("*/run.py")):
            rel = run.relative_to(path)
            tasks.append(
                Task(
                    id=f"tempest:surr:{rel}",
                    title=f"Surrogate {run.parent.name}",
                    argv=["python", str(rel)],
                    group="surrogate",
                    cwd=cwd,
                )
            )
    return tasks


def _binary(path: Path, name: str) -> str:
    candidate = path / "build" / name
    if candidate.exists():
        return str(candidate)
    return str(Path("build") / name)


def _pyproject_scripts(path: Path) -> list[Task]:
    pyproject = path / "pyproject.toml"
    if not pyproject.exists():
        return []
    try:
        text = pyproject.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    tasks: list[Task] = []
    in_scripts = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[project.scripts]"):
            in_scripts = True
            continue
        if in_scripts and stripped.startswith("["):
            break
        if in_scripts and "=" in stripped and not stripped.startswith("#"):
            script = stripped.split("=", 1)[0].strip().strip('"')
            if script:
                tasks.append(
                    Task(
                        id=f"{path.name}:script:{script}",
                        title=script,
                        argv=[script],
                        group="cli",
                        cwd=str(path),
                    )
                )
    return tasks


def _cmake_tasks(path: Path) -> list[Task]:
    if not (path / "CMakeLists.txt").exists():
        return []
    if any(t.group == "build" for t in _recipe_tasks(path, path.name)):
        return []
    return [
        Task(
            id=f"{path.name}:cmake-build",
            title="Build",
            argv=["cmake", "--build", "build"],
            group="build",
            cwd=str(path),
            needs_venv=False,
        )
    ]


def _npm_tasks(path: Path) -> list[Task]:
    pkg = path / "package.json"
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return []
    tasks = []
    for name in scripts:
        if name.startswith("pre") or name.startswith("post"):
            continue
        tasks.append(
            Task(
                id=f"{path.name}:npm:{name}",
                title=f"npm {name}",
                argv=["npm", "run", name],
                group="npm",
                cwd=str(path),
                needs_venv=False,
            )
        )
    return tasks[:12]
