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
    return dict(
        CAG_DATA_DIR=tmp,
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

    def test_collect_snapshot_reads_queue_and_logs(self):
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
