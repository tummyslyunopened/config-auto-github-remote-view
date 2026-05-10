from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.urls import include, path, re_path

urlpatterns = [
    path('', include('status.urls')),
    # Always serve /static/ via the staticfiles app (insecure=True bypasses
    # the DEBUG check). This viewer is LAN-only by design — see settings.py.
    re_path(r'^static/(?P<path>.*)$', staticfiles_serve, {'insecure': True}),
]
