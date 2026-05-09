Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\Activate.ps1"
python manage.py migrate --run-syncdb
python manage.py runserver 0.0.0.0:8001
