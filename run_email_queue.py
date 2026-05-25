import os
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "student_case_tracker.settings")

import django  # noqa: E402


django.setup()

from django.core.management import call_command  # noqa: E402


def main():
    while True:
        call_command("send_outbound_emails")
        time.sleep(60)


if __name__ == "__main__":
    main()
