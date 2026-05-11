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
        # the file-based reader must split that into individual items, with the
        # display order grouping pending in array order (worker pickup order)
        # then everything else newest-first.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([
                    {
                        'id': 'issue-config-2',
                        'number': 2,
                        'title': 'older done issue',
                        'status': 'done',
                        'addedAt': '2026-05-09T00:00:00Z',
                    },
                    {
                        'id': 'issue-config-4',
                        'number': 4,
                        'title': 'pending in array order',
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
        # Pending comes first (worker pickup order), then done.
        self.assertEqual(snap.queue[0].issue_number, 4)
        self.assertEqual(snap.queue[0].state, 'pending')
        self.assertEqual(snap.queue[0].filename, 'issue-config-4')
        self.assertEqual(snap.queue[1].issue_number, 2)
        self.assertEqual(snap.queue[1].state, 'done')
        self.assertEqual(snap.queue_dir, str(tmp / 'queue.json'))

    def test_dashboard_orders_in_progress_before_pending_before_paused_before_done(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([
                    {'id': 'a-done',        'status': 'done',        'addedAt': '2026-05-09T01:00:00Z'},
                    {'id': 'b-pending-1',   'status': 'pending',     'addedAt': '2026-05-09T02:00:00Z'},
                    {'id': 'c-in-prog',     'status': 'in_progress', 'addedAt': '2026-05-09T03:00:00Z'},
                    {'id': 'd-paused',      'status': 'paused',      'addedAt': '2026-05-09T04:00:00Z'},
                    {'id': 'e-pending-2',   'status': 'pending',     'addedAt': '2026-05-09T05:00:00Z'},
                ]),
                encoding='utf-8',
            )
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()

        ids = [it.filename for it in snap.queue]
        # in_progress -> pending (array order preserved) -> paused -> done
        self.assertEqual(ids, ['c-in-prog', 'b-pending-1', 'e-pending-2', 'd-paused', 'a-done'])

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

    def test_github_url_built_from_repo_and_number_for_issue(self):
        # Issue records carry repo + number but no `url`; we synthesise the
        # canonical github issue URL so the dashboard can link out.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([{
                    'id': 'issue-config-7',
                    'type': 'new_issue',
                    'repo': 'tummyslyunopened/config',
                    'number': 7,
                    'title': 'something',
                    'status': 'pending',
                }]),
                encoding='utf-8',
            )
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()
        self.assertEqual(snap.queue[0].github_url, 'https://github.com/tummyslyunopened/config/issues/7')

    def test_github_url_uses_explicit_url_for_comment(self):
        # Comment records carry an explicit `url` (which deep-links to the
        # comment anchor); we should pass that through verbatim.
        comment_url = 'https://github.com/tummyslyunopened/config/issues/4#issuecomment-4412095325'
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([{
                    'id': 'comment-4412095325',
                    'type': 'issue_comment',
                    'repo': 'tummyslyunopened/config',
                    'number': 4,
                    'url': comment_url,
                    'status': 'pending',
                }]),
                encoding='utf-8',
            )
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()
        self.assertEqual(snap.queue[0].github_url, comment_url)

    def test_github_url_empty_when_no_repo_or_number(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([{'id': 'orphan', 'title': 'no repo info', 'status': 'pending'}]),
                encoding='utf-8',
            )
            with override_settings(**_settings_for(tmp)):
                from status.service import collect_snapshot
                snap = collect_snapshot()
        self.assertEqual(snap.queue[0].github_url, '')

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
        # No more meta-refresh; refresh happens via fetch against /fragment/.
        self.assertNotContains(resp, 'http-equiv="refresh"')
        self.assertContains(resp, 'data-fragment-url')
        self.assertContains(resp, 'rel="manifest"')

    def test_dashboard_fragment_returns_panes_only(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            with override_settings(**_settings_for(tmp)):
                resp = self.client.get('/fragment/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        # Fragment is the bare panes — no <html>/<head>/<script> wrapper.
        self.assertNotIn('<html', body)
        self.assertNotIn('<script', body)
        self.assertIn('data-slug="monitor"', body)
        self.assertIn('data-slug="worker"', body)
        self.assertIn('data-slug="queue"', body)

    def test_dashboard_renders_github_link_for_items_with_url(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / 'queue.json').write_text(
                json.dumps([{
                    'id': 'issue-config-7',
                    'type': 'new_issue',
                    'repo': 'tummyslyunopened/config',
                    'number': 7,
                    'title': 'something',
                    'status': 'pending',
                }]),
                encoding='utf-8',
            )
            with override_settings(**_settings_for(tmp)):
                resp = self.client.get('/')
        self.assertContains(resp, 'https://github.com/tummyslyunopened/config/issues/7')
        self.assertContains(resp, 'target="_blank"')

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


def _write_queue(tmp: Path, records: list[dict]) -> None:
    (tmp / 'queue.json').write_text(json.dumps(records), encoding='utf-8')


def _read_queue(tmp: Path) -> list[dict]:
    return json.loads((tmp / 'queue.json').read_text(encoding='utf-8'))


class QueueWriteActionsTests(TestCase):
    """The 4 dashboard write actions. Each POST should mutate queue.json and
    redirect back to the dashboard."""

    def test_priority_moves_item_to_array_top(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _write_queue(tmp, [
                {'id': 'first',  'status': 'pending'},
                {'id': 'middle', 'status': 'pending'},
                {'id': 'last',   'status': 'pending'},
            ])
            with override_settings(**_settings_for(tmp)):
                resp = self.client.post('/queue/last/priority')
            after = _read_queue(tmp)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual([r['id'] for r in after], ['last', 'first', 'middle'])

    def test_pause_sets_status_and_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _write_queue(tmp, [{'id': 'x', 'status': 'pending'}])
            with override_settings(**_settings_for(tmp)):
                resp = self.client.post('/queue/x/pause')
            after = _read_queue(tmp)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(after[0]['status'], 'paused')
        self.assertIn('pausedAt', after[0])
        self.assertIn('pauseReason', after[0])

    def test_resume_flips_paused_back_to_pending(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _write_queue(tmp, [{'id': 'x', 'status': 'paused', 'pausedAt': '2026-01-01T00:00:00Z'}])
            with override_settings(**_settings_for(tmp)):
                resp = self.client.post('/queue/x/resume')
            after = _read_queue(tmp)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(after[0]['status'], 'pending')

    def test_cancel_sets_status_and_calls_kill_runner(self):
        # We don't have a real runner to kill in tests, but we verify the
        # status flip and that the kill_runner_for_item call did not raise.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _write_queue(tmp, [{'id': 'x', 'status': 'in_progress'}])
            with override_settings(**_settings_for(tmp)):
                resp = self.client.post('/queue/x/cancel')
            after = _read_queue(tmp)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(after[0]['status'], 'cancelled')
        self.assertIn('cancelReason', after[0])

    def test_missing_item_redirects_without_changes(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _write_queue(tmp, [{'id': 'real', 'status': 'pending'}])
            with override_settings(**_settings_for(tmp)):
                resp = self.client.post('/queue/missing/pause')
            after = _read_queue(tmp)
        # Still redirects (idempotent / forgiving), queue untouched
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]['status'], 'pending')

    def test_get_requests_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _write_queue(tmp, [{'id': 'x', 'status': 'pending'}])
            with override_settings(**_settings_for(tmp)):
                resp = self.client.get('/queue/x/pause')
        # require_POST returns 405 for GET
        self.assertEqual(resp.status_code, 405)
