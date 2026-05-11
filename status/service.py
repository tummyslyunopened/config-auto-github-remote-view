"""
Pure read functions for inspecting config-auto-github state.

Every function here is best-effort: a missing file or unreadable PID returns
an empty / "unknown" result rather than raising. The whole point of the
viewer is to keep rendering even when half the data is missing.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
from django.conf import settings


@dataclass
class ProcessStatus:
    name: str
    running: bool
    pid: int | None = None
    pid_file: str = ''
    started_at: str | None = None  # ISO 8601 UTC
    detail: str = ''


@dataclass
class QueueItem:
    filename: str
    modified: str  # ISO 8601 UTC
    size_bytes: int
    parsed: dict[str, Any] | None = None
    raw_excerpt: str = ''
    title: str = ''
    issue_number: int | None = None
    state: str = ''
    github_url: str = ''


@dataclass
class Snapshot:
    generated_at: str
    monitor: ProcessStatus
    worker: ProcessStatus
    queue: list[QueueItem] = field(default_factory=list)
    queue_dir: str = ''
    monitor_log_path: str = ''
    worker_log_path: str = ''
    monitor_log_tail: list[str] = field(default_factory=list)
    worker_log_tail: list[str] = field(default_factory=list)
    refresh_seconds: int = 5


_REPO_RE = re.compile(r'^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$')


def _github_url_for(d: dict[str, Any]) -> str:
    """Derive the upstream GitHub URL for a queue record.

    Comments carry an explicit `url`. Issues only carry `repo` + `number`, so
    we synthesise the canonical issue URL from those. Anything else (no usable
    fields, or a `repo` that doesn't look like `owner/name`) returns ''.
    """
    url = d.get('url')
    if isinstance(url, str) and url.startswith(('http://', 'https://')):
        return url
    repo = d.get('repo')
    number = d.get('number') or d.get('issue_number')
    if not isinstance(repo, str) or not _REPO_RE.match(repo):
        return ''
    try:
        n = int(number) if number is not None else None
    except (TypeError, ValueError):
        return ''
    if n is None:
        return ''
    return f'https://github.com/{repo}/issues/{n}'


def _read_pid_file(path: Path) -> int | None:
    try:
        text = path.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not text:
        return None
    try:
        return int(text.splitlines()[0].strip())
    except ValueError:
        return None


def _process_status(name: str, pid_file: Path) -> ProcessStatus:
    if not pid_file.exists():
        return ProcessStatus(
            name=name,
            running=False,
            pid_file=str(pid_file),
            detail='no pidfile',
        )

    pid = _read_pid_file(pid_file)
    if pid is None:
        return ProcessStatus(
            name=name,
            running=False,
            pid_file=str(pid_file),
            detail='pidfile unreadable',
        )

    try:
        proc = psutil.Process(pid)
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return ProcessStatus(
                name=name,
                running=False,
                pid=pid,
                pid_file=str(pid_file),
                detail='process exited',
            )
        started = datetime.fromtimestamp(proc.create_time(), tz=timezone.utc)
        return ProcessStatus(
            name=name,
            running=True,
            pid=pid,
            pid_file=str(pid_file),
            started_at=started.isoformat(timespec='seconds'),
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ProcessStatus(
            name=name,
            running=False,
            pid=pid,
            pid_file=str(pid_file),
            detail='process not found',
        )


def _tail_lines(path: Path, n: int) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        # deque keeps memory bounded for big logs
        with path.open('r', encoding='utf-8-sig', errors='replace') as fh:
            return list(deque(fh, maxlen=n))
    except OSError:
        return []


def _load_queue_item(p: Path) -> QueueItem:
    try:
        stat = p.stat()
    except OSError:
        return QueueItem(filename=p.name, modified='', size_bytes=0)

    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec='seconds')
    item = QueueItem(filename=p.name, modified=modified, size_bytes=stat.st_size)

    try:
        text = p.read_text(encoding='utf-8-sig', errors='replace')
    except OSError:
        return item

    item.raw_excerpt = text[:2000]
    try:
        data = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return item

    if isinstance(data, dict):
        item.parsed = data
        # Best-effort field extraction. config-auto-github items typically
        # carry an issue title / number / state, but the viewer must not
        # break if the schema differs.
        item.title = str(data.get('title') or data.get('issue_title') or '')
        try:
            n = data.get('number') or data.get('issue_number')
            item.issue_number = int(n) if n is not None else None
        except (TypeError, ValueError):
            item.issue_number = None
        item.state = str(data.get('state') or data.get('status') or '')
        item.github_url = _github_url_for(data)
    return item


def _queue_item_from_dict(d: dict[str, Any], modified: str) -> QueueItem:
    """Build a QueueItem from a parsed queue-record dict."""
    try:
        size = len(json.dumps(d))
    except (TypeError, ValueError):
        size = 0
    item = QueueItem(
        filename=str(d.get('id') or d.get('filename') or 'item'),
        modified=str(d.get('addedAt') or d.get('startedAt') or modified or ''),
        size_bytes=size,
        parsed=d,
    )
    item.title = str(d.get('title') or d.get('issue_title') or '')
    try:
        n = d.get('number') or d.get('issue_number')
        item.issue_number = int(n) if n is not None else None
    except (TypeError, ValueError):
        item.issue_number = None
    item.state = str(d.get('state') or d.get('status') or '')
    item.github_url = _github_url_for(d)
    return item


def _list_queue_from_file(p: Path) -> list[QueueItem]:
    """Parse one JSON file containing an array (or a single object) of queue records."""
    try:
        text = p.read_text(encoding='utf-8-sig', errors='replace')
        data = json.loads(text)
        stat = p.stat()
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec='seconds')

    if isinstance(data, list):
        records = [d for d in data if isinstance(d, dict)]
    elif isinstance(data, dict):
        records = [data]
    else:
        return []

    items = [_queue_item_from_dict(d, modified) for d in records]
    # Group by state so the dashboard surfaces the worker pickup order for
    # pending items (which preserve their array position -- that is what
    # `prioritize_item` manipulates). Everything else sorts newest-first.
    in_progress = [i for i in items if i.state == 'in_progress']
    pending = [i for i in items if i.state == 'pending']
    paused = [i for i in items if i.state == 'paused']
    other = [i for i in items if i.state not in ('pending', 'in_progress', 'paused')]
    paused.sort(key=lambda i: i.modified, reverse=True)
    other.sort(key=lambda i: i.modified, reverse=True)
    return in_progress + pending + paused + other


def _list_queue_from_dir(queue_dir: Path) -> list[QueueItem]:
    """Each file in queue_dir is treated as one queue record."""
    try:
        files = [p for p in queue_dir.iterdir() if p.is_file() and p.suffix.lower() == '.json']
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_load_queue_item(p) for p in files]


def _list_queue() -> list[QueueItem]:
    """Read the queue, preferring the single-file layout over the per-item-dir layout."""
    queue_file = Path(settings.CAG_QUEUE_FILE)
    if queue_file.is_file():
        return _list_queue_from_file(queue_file)
    queue_dir = Path(settings.CAG_QUEUE_DIR)
    if queue_dir.is_dir():
        return _list_queue_from_dir(queue_dir)
    return []


def _queue_source_path() -> str:
    """Show the user which path was actually consulted for the queue."""
    queue_file = Path(settings.CAG_QUEUE_FILE)
    if queue_file.is_file():
        return str(queue_file)
    return str(settings.CAG_QUEUE_DIR)


# ---------------------------------------------------------------------------
# Write actions (priority / pause / resume / cancel)
# ---------------------------------------------------------------------------

def _read_queue_records() -> tuple[list[dict], Path]:
    """Read queue.json into a list of dicts (preserving array order).

    Returns (records, path) where records is empty if the file is missing or
    unparseable. Path is always returned so callers can write back.
    """
    queue_file = Path(settings.CAG_QUEUE_FILE)
    if not queue_file.is_file():
        return [], queue_file
    try:
        text = queue_file.read_text(encoding='utf-8-sig', errors='replace')
        data = json.loads(text)
    except (OSError, ValueError, json.JSONDecodeError):
        return [], queue_file
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)], queue_file
    if isinstance(data, dict):
        return [data], queue_file
    return [], queue_file


def _write_queue_records(records: list[dict], queue_file: Path) -> None:
    """Atomic-ish write: tempfile + rename so a partial write can't corrupt the queue."""
    tmp = queue_file.with_suffix(queue_file.suffix + '.tmp')
    tmp.write_text(json.dumps(records, indent=4), encoding='utf-8')
    tmp.replace(queue_file)


def prioritize_item(item_id: str) -> bool:
    """Move the item with this id to position 0 in the queue array.

    The worker picks the first pending item in array order, so moving an item
    to index 0 makes it next up (if pending). Returns True if found and moved.
    """
    records, qf = _read_queue_records()
    idx = next((i for i, r in enumerate(records) if str(r.get('id')) == item_id), None)
    if idx is None:
        return False
    target = records.pop(idx)
    records.insert(0, target)
    _write_queue_records(records, qf)
    return True


def set_item_status(item_id: str, new_status: str, extra: dict | None = None) -> bool:
    """Set the status of the item with this id. Optionally merges extra fields
    (e.g. {'pausedAt': '...', 'pauseReason': '...'}). Returns True if found."""
    records, qf = _read_queue_records()
    target = next((r for r in records if str(r.get('id')) == item_id), None)
    if target is None:
        return False
    target['status'] = new_status
    if extra:
        for k, v in extra.items():
            target[k] = v
    _write_queue_records(records, qf)
    return True


def kill_runner_for_item(item_id: str) -> int:
    """Find any powershell.exe / pwsh.exe process whose command line references
    this queue item id (via cag-prompt-<id> or logs\\<id>.log) and kill the
    process plus its children (claude.exe). Returns count killed."""
    killed = 0
    needle_prompt = f'cag-prompt-{item_id}'
    needle_log = f'logs\\{item_id}.log'
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or '').lower()
            if name not in ('powershell.exe', 'pwsh.exe'):
                continue
            cmdline = ' '.join(proc.info.get('cmdline') or [])
            if needle_prompt not in cmdline and needle_log not in cmdline:
                continue
            # Kill children first (claude.exe is a child of the runner)
            for child in proc.children(recursive=True):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            proc.kill()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


# ---------------------------------------------------------------------------
# Snapshot (read)
# ---------------------------------------------------------------------------

def collect_snapshot() -> Snapshot:
    monitor = _process_status('monitor', Path(settings.CAG_MONITOR_PIDFILE))
    worker = _process_status('worker', Path(settings.CAG_WORKER_PIDFILE))
    queue = _list_queue()
    monitor_tail = _tail_lines(Path(settings.CAG_MONITOR_LOG), settings.CAG_LOG_TAIL_LINES)
    worker_tail = _tail_lines(Path(settings.CAG_WORKER_LOG), settings.CAG_LOG_TAIL_LINES)

    return Snapshot(
        generated_at=datetime.now(tz=timezone.utc).isoformat(timespec='seconds'),
        monitor=monitor,
        worker=worker,
        queue=queue,
        queue_dir=_queue_source_path(),
        monitor_log_path=str(settings.CAG_MONITOR_LOG),
        worker_log_path=str(settings.CAG_WORKER_LOG),
        monitor_log_tail=monitor_tail,
        worker_log_tail=worker_tail,
        refresh_seconds=settings.CAG_REFRESH_SECONDS,
    )
