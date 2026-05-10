# config-auto-github-remote-view

A mobile-friendly Django web app for viewing **and lightly managing** the live
status of [`config-auto-github`](https://github.com/tummyslyunopened/config-auto-github).

Vendored as a submodule of
[`tummyslyunopened/config`](https://github.com/tummyslyunopened/config).

The page renders four panes — **issues in queue**, **monitor status**,
**worker status**, and the most recent **log output** from each — and
auto-refreshes every few seconds.

Each queue item also exposes a small action row for queue management:

| State | Available actions |
|-------|-------------------|
| `pending` | **↑ Top** (move to front of queue), **⏸ Pause**, **✕ Cancel** |
| `paused` | **▶ Resume**, **✕ Cancel** |
| `in_progress` | **✕ Cancel** (kills the runner and any spawned `claude.exe`) |
| `done` / `error` / `cancelled` | — |

The dashboard remains read-only for everything except those four queue mutations.
No logins; bind to LAN and let your firewall handle access. CSRF protection is
enabled on the POST forms.

---

## Setup

**Requirements:** Python 3.11+

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env       # then edit paths to match your setup
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

Then open `http://<host>:8001/` from any phone or laptop on the LAN.

---

## Configuration

The viewer reads files written by `config-auto-github`. Paths are configurable
via environment variables (or `.env`). Defaults assume `config-auto-github`
writes its queue and logs directly inside the submodule checkout at
`~/config/config-auto-github/` (the layout it produces today).

| Variable             | Default                                                | Purpose                                                                |
|----------------------|--------------------------------------------------------|------------------------------------------------------------------------|
| `CAG_DATA_DIR`       | `~/config/config-auto-github`                          | Base data directory                                                    |
| `CAG_QUEUE_FILE`     | `<CAG_DATA_DIR>/queue.json`                            | Single JSON file containing an array of queue items (preferred layout) |
| `CAG_QUEUE_DIR`      | `<CAG_DATA_DIR>/queue`                                 | Fallback: directory of per-item `*.json` files                         |
| `CAG_MONITOR_LOG`    | `<CAG_DATA_DIR>/logs/monitor.log`                      | Monitor process log file                                               |
| `CAG_WORKER_LOG`     | `<CAG_DATA_DIR>/logs/worker.log`                       | Worker process log file                                                |
| `CAG_MONITOR_PIDFILE`| `<CAG_DATA_DIR>/monitor.pid`                           | PID file written by the monitor while running                          |
| `CAG_WORKER_PIDFILE` | `<CAG_DATA_DIR>/worker.pid`                            | PID file written by the worker while running                           |
| `CAG_LOG_TAIL_LINES` | `200`                                                  | Number of trailing log lines to render                                 |
| `CAG_REFRESH_SECONDS`| `5`                                                    | Auto-refresh interval                                                  |

`CAG_QUEUE_FILE` takes precedence over `CAG_QUEUE_DIR`: if the file exists it
is parsed as a JSON array (or a single object), otherwise the per-item
directory is consulted.

If a configured path does not exist, the corresponding pane shows an empty /
"not running" state rather than erroring — by design, the viewer never blocks.

---

## Endpoints

| Path     | Purpose                                            |
|----------|----------------------------------------------------|
| `/`      | Combined dashboard (auto-refreshes)                |
| `/api/`  | Same data as JSON, for embedding or scripting      |
