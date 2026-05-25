"""
WSGI template for PythonAnywhere manual configuration.

Copy the contents of this file into the WSGI configuration file that
PythonAnywhere creates for your web app, then replace `yourusername`
with your PythonAnywhere username.
"""

import os
import sys
from pathlib import Path


USERNAME = "yourusername"
PROJECT_NAME = "Student-Tracker"

project_home = Path(f"/home/{USERNAME}/{PROJECT_NAME}")
if str(project_home) not in sys.path:
    sys.path.insert(0, str(project_home))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "student_case_tracker.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "replace-with-a-long-random-secret")
os.environ.setdefault("DJANGO_DEBUG", "False")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", f"{USERNAME}.pythonanywhere.com")
os.environ.setdefault("DJANGO_CSRF_TRUSTED_ORIGINS", f"https://{USERNAME}.pythonanywhere.com")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{project_home / 'db.sqlite3'}")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
