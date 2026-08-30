# Graph Report - machina  (2026-08-29)

## Corpus Check
- 50 files · ~29,566 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 547 nodes · 1830 edges · 17 communities (13 shown, 4 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 157 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- main_window.py
- machina/projects.py
- telemetry.py
- paths.py
- machina/models.py
- MainWindow
- machina/storage.py
- runtime.py
- JobsPage
- CircularGauge
- apply_actions
- Machina
- ModelsPage
- machina
- machina
- ProjectsPage
- host.py

## God Nodes (most connected - your core abstractions)
1. `HostState` - 58 edges
2. `Snapshot` - 44 edges
3. `Page` - 41 edges
4. `muted()` - 39 edges
5. `Kpi` - 31 edges
6. `RuntimeResult` - 29 edges
7. `MainWindow` - 29 edges
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

## Communities (17 total, 4 thin omitted)

### Community 0 - "main_window.py"
Cohesion: 0.08
Nodes (37): QTableWidget, QThread, assess(), Assessment, hottest_cpu(), load_guardrails(), _num(), Any (+29 more)

### Community 1 - "machina/projects.py"
Cohesion: 0.19
Nodes (23): _guess_log(), Job, JobManager, _looks_like_job(), Path, Process, _binary(), _cmake_tasks() (+15 more)

### Community 2 - "telemetry.py"
Cohesion: 0.09
Nodes (43): QApplication, main(), BacklightInfo, BatteryInfo, _collect_backlight(), _collect_battery(), _collect_cpu(), _collect_fans() (+35 more)

### Community 3 - "paths.py"
Cohesion: 0.13
Nodes (30): log_event(), Any, read_recent(), _append(), Event, EventLog, Any, Compare consecutive HostState-like objects. prev may be None. (+22 more)

### Community 4 - "machina/models.py"
Cohesion: 0.09
Nodes (49): _cache_key(), find_llama_ngl(), find_ollama_num_gpu(), _fully_on_gpu(), gpu_layers_cache_path(), highest_fitting(), is_oom_text(), _llm_complete() (+41 more)

### Community 5 - "MainWindow"
Cohesion: 0.14
Nodes (9): QDialog, QMainWindow, Slot, MainWindow, Any, QFrame, QLabel, _runtime_risk() (+1 more)

### Community 6 - "machina/storage.py"
Cohesion: 0.18
Nodes (19): disk_cache_path(), BlockDev, _blocks(), collect_storage_light(), DirUsage, _du(), _int_file(), _load_cache() (+11 more)

### Community 7 - "runtime.py"
Cohesion: 0.08
Nodes (67): Saved max `num_gpu` / `-ngl` for this model, if we trust the entry., remembered_gpu_layers(), resolve_llama_gguf(), job_manager(), _as_bool(), _as_float(), _as_int(), _from_dict() (+59 more)

### Community 8 - "JobsPage"
Cohesion: 0.19
Nodes (3): JobsPage, ProcessesPage, fmt_duration()

### Community 9 - "CircularGauge"
Cohesion: 0.13
Nodes (7): QColor, CircularGauge, CoreBar, ModeCard, QLabel, QWidget, Sparkline

### Community 10 - "apply_actions"
Cohesion: 0.18
Nodes (16): apply_actions(), ApplyResult, _helper_path(), _pkexec_apply(), Any, Path, _all_cpu_glob(), apply_all() (+8 more)

### Community 11 - "Machina"
Cohesion: 0.25
Nodes (7): Architecture, Guardrails, Hardware control (unchanged safety model), Machina, Run, What it is for, Workloads this machine actually has

### Community 16 - "host.py"
Cohesion: 0.10
Nodes (35): Engine, _all_ipv4(), _default_route(), _established_count(), _guess_kind(), _listening_ports(), NetIface, NetworkInfo (+27 more)

## Knowledge Gaps
- **7 isolated node(s):** `machina`, `Run`, `What it is for`, `Hardware control (unchanged safety model)`, `Workloads this machine actually has` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `HostState` connect `main_window.py` to `machina/projects.py`, `paths.py`, `machina/models.py`, `MainWindow`, `machina/storage.py`, `runtime.py`, `JobsPage`, `ModelsPage`, `ProjectsPage`, `host.py`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `Snapshot` connect `main_window.py` to `host.py`, `machina/projects.py`, `telemetry.py`, `MainWindow`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `MainWindow` connect `MainWindow` to `main_window.py`, `telemetry.py`, `runtime.py`, `apply_actions`, `host.py`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 29 inferred relationships involving `HostState` (e.g. with `Engine` and `Event`) actually correct?**
  _`HostState` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `Snapshot` (e.g. with `Engine` and `HostState`) actually correct?**
  _`Snapshot` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `Kpi` (e.g. with `CoolingPage` and `CpuPage`) actually correct?**
  _`Kpi` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `machina`, `Run`, `What it is for` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._