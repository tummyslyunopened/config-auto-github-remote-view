"""
Pure read functions for inspecting config-auto-github state.

Every function here is best-effort: a missing file or unreadable PID returns
an empty / "unknown" result rather than raising. The whole point of the
viewer is to keep rendering even when half the data is missing.
"""

from __future__ import annotations

import json
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
        with path.open('r', encoding='utf-8', errors='replace') as fh:
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
        text = p.read_text(encoding='utf-8', errors='replace')
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
    return item


def _list_queue(queue_dir: Path) -> list[QueueItem]:
    if not queue_dir.exists() or not queue_dir.is_dir():
        return []
    try:
        files = [p for p in queue_dir.iterdir() if p.is_file() and p.suffix.lower() == '.json']
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_load_queue_item(p) for p in files]


def collect_snapshot() -> Snapshot:
    monitor = _process_status('monitor', Path(settings.CAG_MONITOR_PIDFILE))
    worker = _process_status('worker', Path(settings.CAG_WORKER_PIDFILE))
    queue = _list_queue(Path(settings.CAG_QUEUE_DIR))
    monitor_tail = _tail_lines(Path(settings.CAG_MONITOR_LOG), settings.CAG_LOG_TAIL_LINES)
    worker_tail = _tail_lines(Path(settings.CAG_WORKER_LOG), settings.CAG_LOG_TAIL_LINES)

    return Snapshot(
        generated_at=datetime.now(tz=timezone.utc).isoformat(timespec='seconds'),
        monitor=monitor,
        worker=worker,
        queue=queue,
        queue_dir=str(settings.CAG_QUEUE_DIR),
        monitor_log_path=str(settings.CAG_MONITOR_LOG),
        worker_log_path=str(settings.CAG_WORKER_LOG),
        monitor_log_tail=monitor_tail,
        worker_log_tail=worker_tail,
        refresh_seconds=settings.CAG_REFRESH_SECONDS,
    )
