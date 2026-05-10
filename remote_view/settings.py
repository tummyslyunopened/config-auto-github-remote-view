"""
Django settings for the config-auto-github remote-view project.

This is a read-only viewer; there are no logins, forms, or write actions.
Sensitive paths (where config-auto-github writes its queue and logs) are
sourced from environment variables so they can be overridden per host.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'insecure-default-change-me')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# This viewer is meant to be reachable from a phone on the LAN, so we don't
# pin to localhost. The reverse proxy / firewall is responsible for who can
# actually reach it.
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'status',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'remote_view.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'remote_view.wsgi.application'

# A nominal SQLite DB so Django is happy. The viewer itself stores no state.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# config-auto-github observation paths
# ---------------------------------------------------------------------------

def _default_data_dir() -> Path:
    # config-auto-github writes its queue and logs directly inside the submodule
    # checkout (e.g. ~/config/config-auto-github), not into a separate .data dir.
    home = Path(os.path.expanduser('~'))
    return home / 'config' / 'config-auto-github'

CAG_DATA_DIR = Path(os.environ.get('CAG_DATA_DIR', str(_default_data_dir())))

# Queue can be exposed two ways:
#   - CAG_QUEUE_FILE: a single JSON file containing an array of queue items
#     (this is the layout config-auto-github currently produces)
#   - CAG_QUEUE_DIR : a directory of per-item *.json files (alternative layout)
# Both are checked at read time; whichever exists wins, with the file taking
# precedence so the simpler single-file layout is the default.
CAG_QUEUE_FILE = Path(os.environ.get('CAG_QUEUE_FILE', str(CAG_DATA_DIR / 'queue.json')))
CAG_QUEUE_DIR = Path(os.environ.get('CAG_QUEUE_DIR', str(CAG_DATA_DIR / 'queue')))

CAG_MONITOR_LOG = Path(os.environ.get('CAG_MONITOR_LOG', str(CAG_DATA_DIR / 'logs' / 'monitor.log')))
CAG_WORKER_LOG = Path(os.environ.get('CAG_WORKER_LOG', str(CAG_DATA_DIR / 'logs' / 'worker.log')))
CAG_MONITOR_PIDFILE = Path(os.environ.get('CAG_MONITOR_PIDFILE', str(CAG_DATA_DIR / 'monitor.pid')))
CAG_WORKER_PIDFILE = Path(os.environ.get('CAG_WORKER_PIDFILE', str(CAG_DATA_DIR / 'worker.pid')))
CAG_LOG_TAIL_LINES = int(os.environ.get('CAG_LOG_TAIL_LINES', '200'))
CAG_REFRESH_SECONDS = int(os.environ.get('CAG_REFRESH_SECONDS', '5'))
