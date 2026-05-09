# config-auto-github-remote-view

A read-only, mobile-friendly Django web app for viewing the live status of
[`config-auto-github`](https://github.com/tummyslyunopened/config-auto-github).

Vendored as a submodule of
[`tummyslyunopened/config`](https://github.com/tummyslyunopened/config).

The page renders four panes — **issues in queue**, **monitor status**,
**worker status**, and the most recent **log output** from each — and
auto-refreshes every few seconds. There are no buttons, no logins, and no
write actions: it is purely an observability pane.

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
via environment variables (or `.env`). Defaults assume the standard layout
where `config-auto-github` writes to `~/config/.data/config-auto-github/`.

| Variable             | Default                                                | Purpose                                       |
|----------------------|--------------------------------------------------------|-----------------------------------------------|
| `CAG_DATA_DIR`       | `~/config/.data/config-auto-github`                    | Base data directory                           |
| `CAG_QUEUE_DIR`      | `<CAG_DATA_DIR>/queue`                                 | Directory of `*.json` queue items             |
| `CAG_MONITOR_LOG`    | `<CAG_DATA_DIR>/monitor.log`                           | Monitor process log file                      |
| `CAG_WORKER_LOG`     | `<CAG_DATA_DIR>/worker.log`                            | Worker process log file                       |
| `CAG_MONITOR_PIDFILE`| `<CAG_DATA_DIR>/monitor.pid`                           | PID file written by the monitor while running |
| `CAG_WORKER_PIDFILE` | `<CAG_DATA_DIR>/worker.pid`                            | PID file written by the worker while running  |
| `CAG_LOG_TAIL_LINES` | `200`                                                  | Number of trailing log lines to render        |
| `CAG_REFRESH_SECONDS`| `5`                                                    | Auto-refresh interval                         |

If a configured path does not exist, the corresponding pane shows an empty /
"not running" state rather than erroring — by design, the viewer never blocks.

---

## Endpoints

| Path     | Purpose                                            |
|----------|----------------------------------------------------|
| `/`      | Combined dashboard (auto-refreshes)                |
| `/api/`  | Same data as JSON, for embedding or scripting      |
