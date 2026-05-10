from dataclasses import asdict
from datetime import datetime, timezone

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import service


def dashboard(request):
    snapshot = service.collect_snapshot()
    return render(request, 'status/dashboard.html', {'s': snapshot})


def dashboard_fragment(request):
    snapshot = service.collect_snapshot()
    return render(request, 'status/_panes.html', {'s': snapshot})


def dashboard_json(request):
    snapshot = service.collect_snapshot()
    return JsonResponse(asdict(snapshot))


# ---------------------------------------------------------------------------
# Write actions on the queue. Each one redirects back to the dashboard so the
# user sees the new state immediately (HTML-form-based; no JS required).
# ---------------------------------------------------------------------------

@require_POST
def queue_priority(request, item_id):
    service.prioritize_item(item_id)
    return redirect('dashboard')


@require_POST
def queue_pause(request, item_id):
    now = datetime.now(tz=timezone.utc).isoformat(timespec='seconds')
    service.set_item_status(item_id, 'paused', extra={
        'pausedAt': now,
        'pauseReason': 'paused from dashboard',
    })
    return redirect('dashboard')


@require_POST
def queue_resume(request, item_id):
    service.set_item_status(item_id, 'pending')
    return redirect('dashboard')


@require_POST
def queue_cancel(request, item_id):
    now = datetime.now(tz=timezone.utc).isoformat(timespec='seconds')
    service.set_item_status(item_id, 'cancelled', extra={
        'completedAt': now,
        'cancelReason': 'cancelled from dashboard',
    })
    # Best-effort kill of any runner/claude process for this item; safe to call
    # for non-in-progress items (just returns 0).
    service.kill_runner_for_item(item_id)
    return redirect('dashboard')
