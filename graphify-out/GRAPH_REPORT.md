# Graph Report - machina  (2026-08-30)

## Corpus Check
- 51 files · ~31,669 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 572 nodes · 1886 edges · 17 communities (14 shown, 3 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 157 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- main_window.py
- state.py
- telemetry.py
- machina/models.py
- gpu_layers.py
- MainWindow
- machina/storage.py
- runtime.py
- JobsPage
- run_app
- apply_actions
- Machina
- nvml.py
- machina
- machina
- ProjectsPage
- util.py

## God Nodes (most connected - your core abstractions)
1. `HostState` - 59 edges
2. `Snapshot` - 44 edges
3. `Page` - 41 edges
4. `muted()` - 39 edges
5. `MainWindow` - 31 edges
6. `Kpi` - 31 edges
7. `RuntimeResult` - 29 edges
8. `card()` - 28 edges
9. `http_json()` - 26 edges
10. `Engine` - 21 edges

## Surprising Connections (you probably didn't know these)
- `ApplyWorker` --uses--> `ApplyResult`  [INFERRED]
  src/machina/ui/main_window.py → src/machina/control.py
- `Collector` --uses--> `ApplyResult`  [INFERRED]
  src/machina/ui/main_window.py → src/machina/control.py
- `MainWindow` --uses--> `ApplyResult`  [INFERRED]
  src/machina/ui/main_window.py → src/machina/control.py
- `RuntimeWorker` --uses--> `ApplyResult`  [INFERRED]
  src/machina/ui/main_window.py → src/machina/control.py
- `HostState` --uses--> `Event`  [INFERRED]
  src/machina/state.py → src/machina/events.py

## Import Cycles
- None detected.

## Communities (17 total, 3 thin omitted)

### Community 0 - "main_window.py"
Cohesion: 0.07
Nodes (34): QTableWidget, QThread, HostState, Snapshot, ApplyWorker, Collector, RuntimeWorker, CoolingPage (+26 more)

### Community 1 - "state.py"
Cohesion: 0.13
Nodes (34): _guess_log(), Job, JobManager, _looks_like_job(), Path, ModelHub, _boot_time(), GpuProc (+26 more)

### Community 2 - "telemetry.py"
Cohesion: 0.07
Nodes (54): Engine, _project_roots(), Path, collect_models(), Last generate tok/s from ollama/llama serve logs (`ollama run` in a terminal,…, refresh_generation_rate(), NetworkSampler, ProcessSampler (+46 more)

### Community 3 - "machina/models.py"
Cohesion: 0.08
Nodes (48): log_event(), Any, read_recent(), _append(), Event, EventLog, Any, Compare consecutive HostState-like objects. prev may be None. (+40 more)

### Community 4 - "gpu_layers.py"
Cohesion: 0.14
Nodes (28): _cache_key(), find_llama_ngl(), find_ollama_num_gpu(), _fully_on_gpu(), gpu_layers_cache_path(), highest_fitting(), is_oom_text(), _llm_complete() (+20 more)

### Community 5 - "MainWindow"
Cohesion: 0.11
Nodes (18): QDialog, QMainWindow, Slot, assess(), Assessment, hottest_cpu(), load_guardrails(), _num() (+10 more)

### Community 6 - "machina/storage.py"
Cohesion: 0.23
Nodes (16): BlockDev, _blocks(), collect_storage_light(), DirUsage, _du(), _int_file(), _load_cache(), Mount (+8 more)

### Community 7 - "runtime.py"
Cohesion: 0.08
Nodes (67): Saved max `num_gpu` / `-ngl` for this model, if we trust the entry., remembered_gpu_layers(), resolve_llama_gguf(), job_manager(), _as_bool(), _as_float(), _as_int(), _from_dict() (+59 more)

### Community 8 - "JobsPage"
Cohesion: 0.19
Nodes (3): JobsPage, ProcessesPage, fmt_duration()

### Community 9 - "run_app"
Cohesion: 0.18
Nodes (6): QApplication, QColor, main(), run_app(), apply_theme(), Sparkline

### Community 10 - "apply_actions"
Cohesion: 0.18
Nodes (16): apply_actions(), ApplyResult, _helper_path(), _pkexec_apply(), Any, Path, _all_cpu_glob(), apply_all() (+8 more)

### Community 11 - "Machina"
Cohesion: 0.25
Nodes (7): Architecture, Guardrails, Hardware control (unchanged safety model), Machina, Run, What it is for, Workloads this machine actually has

### Community 12 - "nvml.py"
Cohesion: 0.27
Nodes (12): _comm(), compute_apps(), _load(), _Memory, _mw_to_w(), _ProcessV3, Any, query_gpu() (+4 more)

### Community 16 - "util.py"
Cohesion: 0.15
Nodes (25): _all_ipv4(), _default_route(), _established_count(), _guess_kind(), _listening_ports(), NetIface, NetworkInfo, _nmcli_devices() (+17 more)

## Knowledge Gaps
- **7 isolated node(s):** `machina`, `Run`, `What it is for`, `Hardware control (unchanged safety model)`, `Workloads this machine actually has` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `HostState` connect `main_window.py` to `state.py`, `telemetry.py`, `machina/models.py`, `MainWindow`, `machina/storage.py`, `runtime.py`, `JobsPage`, `ProjectsPage`, `util.py`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Why does `Snapshot` connect `main_window.py` to `state.py`, `telemetry.py`, `MainWindow`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `MainWindow` connect `MainWindow` to `main_window.py`, `telemetry.py`, `runtime.py`, `run_app`, `apply_actions`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 29 inferred relationships involving `HostState` (e.g. with `Engine` and `Event`) actually correct?**
  _`HostState` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `Snapshot` (e.g. with `Engine` and `HostState`) actually correct?**
  _`Snapshot` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `MainWindow` (e.g. with `ApplyResult` and `Engine`) actually correct?**
  _`MainWindow` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `machina`, `Run`, `What it is for` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._