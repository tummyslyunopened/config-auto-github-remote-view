from dataclasses import asdict

from django.http import JsonResponse
from django.shortcuts import render

from .service import collect_snapshot


def dashboard(request):
    snapshot = collect_snapshot()
    return render(request, 'status/dashboard.html', {'s': snapshot})


def dashboard_json(request):
    snapshot = collect_snapshot()
    return JsonResponse(asdict(snapshot))
