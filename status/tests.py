"""
Smoke tests for the read-only status viewer.

These exercise the service-layer reads against a tmp directory, plus a
basic render of the dashboard view.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings


def _settings_for(tmp: Path) -> dict:
    # Pin every CAG_* path inside tmp so a stray default doesn't leak into the
    # user's real config-auto-github checkout while tests run.
    return dict(
        CAG_DATA_DIR=tmp,
        CAG_QUEUE_FILE=tmp / 'queue.json',
        CAG_QUEUE_DIR=tmp / 'queue',
        CAG_MONITOR_LOG=tmp / 'monitor.log',
        CAG_WORKER_LOG=tmp / 'worker.log',
        CAG_MONITOR_PIDFILE=tmp / 'monitor.pid',
        CAG_WORKER_PIDFILE=tmp / 'worker.pid',
        CAG_LOG_TAIL_LINES=10,
        CAG_REFRESH_SECONDS=5,
    )


class ServiceTests(TestCase):
    def test_collect_snapshot_handles_missing_paths(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()

        self.assertFalse(snap.monitor.running)
        self.assertFalse(snap.worker.running)
        self.assertEqual(snap.queue, [])
        self.assertEqual(snap.monitor_log_tail, [])
        self.assertEqual(snap.worker_log_tail, [])

    def test_reads_dir_queue_and_logs(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue').mkdir()
            (tmp / 'queue' / '0001.json').write_text(
                json.dumps({'number': 6, 'title': 'demo', 'state': 'open'}),
                encoding='utf-8',
            )
            (tmp / 'queue' / 'note.txt').write_text('ignored', encoding='utf-8')
            (tmp / 'monitor.log').write_text(
                '\n'.join(f'm-line-{i}' for i in range(20)) + '\n',
                encoding='utf-8',
            )
            (tmp / 'worker.log').write_text('w1\nw2\n', encoding='utf-8')

            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()

        self.assertEqual(len(snap.queue), 1)
        self.assertEqual(snap.queue[0].issue_number, 6)
        self.assertEqual(snap.queue[0].title, 'demo')
        self.assertEqual(snap.queue[0].state, 'open')
        self.assertEqual(len(snap.monitor_log_tail), 10)
        self.assertEqual(snap.worker_log_tail[-1].rstrip('\n'), 'w2')

    def test_reads_file_queue(self):
        # config-auto-github writes a single queue.json containing an array;
        # the file-based reader must split that into individual items, sorted
        # newest first.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([
                    {
                        'id': 'issue-config-2',
                        'number': 2,
                        'title': 'older issue',
                        'status': 'done',
                        'addedAt': '2026-05-09T00:00:00Z',
                    },
                    {
                        'id': 'issue-config-4',
                        'number': 4,
                        'title': 'newer issue',
                        'status': 'pending',
                        'addedAt': '2026-05-09T04:00:00Z',
                    },
                ]),
                encoding='utf-8',
            )
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()

        self.assertEqual(len(snap.queue), 2)
        # Newest-first ordering by addedAt.
        self.assertEqual(snap.queue[0].issue_number, 4)
        self.assertEqual(snap.queue[0].state, 'pending')
        self.assertEqual(snap.queue[0].filename, 'issue-config-4')
        self.assertEqual(snap.queue[1].issue_number, 2)
        self.assertEqual(snap.queue[1].state, 'done')
        self.assertEqual(snap.queue_dir, str(tmp / 'queue.json'))

    def test_file_queue_takes_precedence_over_dir(self):
        # If both layouts are present, the single file wins.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([{'id': 'from-file', 'number': 1, 'title': 'file', 'status': 'pending'}]),
                encoding='utf-8',
            )
            (tmp / 'queue').mkdir()
            (tmp / 'queue' / 'a.json').write_text(
                json.dumps({'number': 99, 'title': 'should-be-ignored', 'state': 'pending'}),
                encoding='utf-8',
            )
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()

        self.assertEqual(len(snap.queue), 1)
        self.assertEqual(snap.queue[0].title, 'file')

    def test_pidfile_with_dead_pid_reports_not_running(self):
        import psutil
        # Pick a PID well above any plausible OS pid_max that is also not
        # currently in use, so psutil reliably raises NoSuchProcess.
        candidate = 2_147_480_000
        while psutil.pid_exists(candidate):
            candidate -= 1
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'monitor.pid').write_text(f'{candidate}\n', encoding='utf-8')
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()
        self.assertFalse(snap.monitor.running)
        self.assertEqual(snap.monitor.pid, candidate)

    def test_pidfile_with_live_pid_reports_running(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'worker.pid').write_text(str(os.getpid()), encoding='utf-8')
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()
        self.assertTrue(snap.worker.running)
        self.assertEqual(snap.worker.pid, os.getpid())


class ViewTests(TestCase):
    def test_dashboard_renders(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            with override_settings(**_settings_for(tmp)):
                resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'config-auto-github')

    def test_dashboard_json(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            with override_settings(**_settings_for(tmp)):
                resp = self.client.get('/api/')
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn('monitor', payload)
        self.assertIn('worker', payload)
        self.assertIn('queue', payload)
