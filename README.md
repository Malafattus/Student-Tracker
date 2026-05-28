# UIS Student Record System

UIS Student Record System is a Django web app for an international high school counselling and recruitment team. It uses form-based data entry, role-based access, and a deployment-friendly structure that starts with SQLite for local development while staying ready to move to PostgreSQL later through standard Django ORM patterns.

## What is included

- User authentication with three roles: `Admin`, `Counsellor`, and `Viewer`
- Staff login using either username or email address
- Dashboard with operational summary cards
- Student intake and update workflow through web forms
- Student list with filters
- Student profile with tabs for overview, notes, tasks, requests, sessions, documents, and communication log
- Student request intake form for transcript, counselling, and support requests
- Student portal with student-specific logins, request history, and session history
- Staff request queue and counselling session timetable
- Email-ready request confirmations, session confirmations, reminder tooling, and session reschedule links
- Admin backup/export tools for SQLite and CSV downloads
- Reports page with weekly, counsellor, case, and overdue follow-up summaries
- Admin user management page
- Audit logging for key create, update, and delete actions
- Security Center with account lockouts, forced password resets, staff email policy, password age review, and MFA controls
- Seed data command with fake users and students

## Stage coverage

- Stage 1 complete: login, roles, add student, student list, student profile, notes, tasks
- Stage 2 complete in MVP form: documents, communication logs, risk levels, filters, dashboard cards
- Stage 3 complete in MVP form: weekly management summary, counsellor activity summary, student case summary, overdue follow-up report
- Stage 4 now partially covered: better UI, student request intake, session booking, login-by-email, and email-ready notification plumbing
- Remaining future enhancement work: Word/PDF export, richer email automation, more granular permissions, and deployment upgrades

## Local setup

1. Create and activate a virtual environment.
2. Install requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Apply migrations:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

4. Seed roles, users, and fake students:

```powershell
.\.venv\Scripts\python.exe manage.py seed_data
```

5. Run the development server:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

6. Open `http://127.0.0.1:8000/`

## Production deployment

The project is prepared for production deployment with:

- Environment-driven Django settings
- WhiteNoise static file serving
- PostgreSQL support through `DATABASE_URL`
- `gunicorn` application server
- A `render.yaml` blueprint for Render
- A generic `Procfile` for platforms that support it

### Render deployment

1. Push this project to GitHub.
2. In Render, create a new Blueprint and point it to the repository.
3. Render will read [render.yaml](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/render.yaml), create the web service and PostgreSQL database, and use:
   - Build command: `bash build.sh`
   - Start command: `gunicorn student_case_tracker.wsgi:application`
4. After the first deploy, open a Render shell or use the web service shell and create an admin user:

```bash
python manage.py createsuperuser
```

5. Optionally run:

```bash
python manage.py seed_data
```

### Environment variables

Use [.env.example](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/.env.example) as the local reference for:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `DJANGO_SITE_URL`
- `DJANGO_EMAIL_BACKEND`
- `DJANGO_DEFAULT_FROM_EMAIL`
- `DJANGO_EMAIL_HOST`
- `DJANGO_EMAIL_PORT`
- `DJANGO_EMAIL_HOST_USER`
- `DJANGO_EMAIL_HOST_PASSWORD`
- `DJANGO_EMAIL_USE_TLS`

## GitHub + Firebase deployment

This repository is also prepared for a Firebase-backed deployment path using:

- [Dockerfile](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/Dockerfile) for a Cloud Run container
- [firebase.json](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/firebase.json) to route Hosting traffic to Cloud Run
- [.firebaserc.example](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/.firebaserc.example) as the Firebase project template
- [.github/workflows/deploy-firebase-cloudrun.yml](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/.github/workflows/deploy-firebase-cloudrun.yml) for GitHub Actions deployment

## PythonAnywhere free deployment

PythonAnywhere free is the best no-cost fit for this project because it can run a small Django site on a free subdomain without requiring Cloud Run billing. PythonAnywhere documents that free accounts include one web app and 512 MiB of disk space: [Free account features](https://help.pythonanywhere.com/pages/FreeAccountsFeatures)

### Before you start

1. Create a free PythonAnywhere account.
2. Open a Bash console in PythonAnywhere.
3. Clone this GitHub repo:

```bash
git clone https://github.com/Malafattus/Student-Tracker.git
cd Student-Tracker
```

### Create a virtual environment

PythonAnywhere recommends using a virtualenv for modern Django versions:
[Deploying an existing Django project](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/)

```bash
python3.13 -m venv ~/.virtualenvs/student-tracker
source ~/.virtualenvs/student-tracker/bin/activate
pip install --upgrade pip
pip install -r ~/Student-Tracker/requirements.txt
```

If `python3.13` is not available on your account, use the Python version shown in the PythonAnywhere web app setup screen and create the virtualenv with that version instead.

### Create the web app

1. Go to the `Web` tab.
2. Click `Add a new web app`.
3. Choose your free domain: `yourusername.pythonanywhere.com`
4. Choose `Manual configuration`
5. Choose the same Python version you used for the virtualenv.

### Configure the virtualenv

On the `Web` tab, set the virtualenv path to:

```text
/home/yourusername/.virtualenvs/student-tracker
```

### Configure the WSGI file

1. On the `Web` tab, open the WSGI configuration file.
2. Replace its contents with the contents of:
   [pythonanywhere_wsgi.py](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/pythonanywhere_wsgi.py)
3. Replace `yourusername` with your actual PythonAnywhere username.
4. Save the file.

### Prepare the database

In a Bash console on PythonAnywhere:

```bash
cd ~/Student-Tracker
source ~/.virtualenvs/student-tracker/bin/activate
python manage.py migrate
python manage.py createsuperuser
```

Optional demo data:

```bash
python manage.py seed_data
```

### Student portal accounts

Staff can create student-specific portal logins from each student profile using the `Portal Access` button.

Each portal account can:

- sign in through the same login page
- see that student's own request history
- see upcoming sessions
- submit new support requests
- request a session time change from the portal or the email link

### Configure static files

PythonAnywhere's Django static-file setup requires:
- setting `STATIC_ROOT`
- running `collectstatic`
- adding a static files mapping on the `Web` tab

Official guide:
[Django static files on PythonAnywhere](https://help.pythonanywhere.com/pages/DjangoStaticFiles)

Run:

```bash
cd ~/Student-Tracker
source ~/.virtualenvs/student-tracker/bin/activate
python manage.py collectstatic --no-input
```

Then on the `Web` tab, add this static mapping:

- URL: `/static/`
- Directory: `/home/yourusername/Student-Tracker/staticfiles`

### Optional email setup

The request and session tools can send confirmation and reminder emails, but only if you configure an email backend. By default, Django uses a console backend in development, which means emails print to logs instead of being delivered.

Set these environment variables in your PythonAnywhere WSGI file if you want real delivery through an SMTP provider:

```python
os.environ.setdefault("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
os.environ.setdefault("DJANGO_SITE_URL", "https://yourusername.pythonanywhere.com")
os.environ.setdefault("DJANGO_DEFAULT_FROM_EMAIL", "noreply@yourschool.org")
os.environ.setdefault("DJANGO_EMAIL_HOST", "smtp.your-provider.com")
os.environ.setdefault("DJANGO_EMAIL_PORT", "587")
os.environ.setdefault("DJANGO_EMAIL_HOST_USER", "smtp-username")
os.environ.setdefault("DJANGO_EMAIL_HOST_PASSWORD", "smtp-password")
os.environ.setdefault("DJANGO_EMAIL_USE_TLS", "True")
```

### Optional reminder task

Session reminder emails can be sent automatically by running this command on a schedule:

```bash
cd ~/Student-Tracker
source ~/.virtualenvs/student-tracker/bin/activate
python manage.py send_session_reminders
```

On PythonAnywhere, you can add that command as a scheduled task from the `Tasks` tab to run every hour or every day.

### Backup and export tools

Admin users can use the in-app `Admin Tools` page to:

- download the live SQLite database file
- download a zip bundle of CSV exports for students, requests, sessions, and tasks

### Reload the site

Back on the `Web` tab:

1. Click `Reload`
2. Open `https://yourusername.pythonanywhere.com`

### Free-plan notes

- The app will live on a `pythonanywhere.com` subdomain, not a custom domain, on the free plan.
- SQLite is acceptable for this small MVP on PythonAnywhere free.
- If the team grows, you can later move the same codebase to a paid host and PostgreSQL with the existing `DATABASE_URL` support.

## Demo accounts

- Admin: `admin` / `admin123!`
- Counsellor: `counsellor1` / `counsellor123!`
- Counsellor: `counsellor2` / `counsellor123!`
- Viewer: `viewer1` / `viewer123!`

## Superuser creation

Create a Django superuser for the built-in admin site with:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

If you want that account to also use the in-app Admin role pages, assign it to the `Admin` group in Django admin or through the shell.

## PostgreSQL-ready direction

The app supports PostgreSQL directly through `DATABASE_URL`. SQLite remains the default for local development and is acceptable for a small internal PythonAnywhere MVP.

## Notes for maintainers

- The app is intentionally template-driven for a simple small-team workflow.
- Most business rules live in `cases/views.py`, `cases/forms.py`, and `cases/permissions.py`.
- Email behavior lives in `cases/notifications.py`.
- Audit log entries are created manually for user-facing actions and automatically for deletes.

## Governance and security operations

This repository now includes operational documentation for safer institutional use:

- [PRODUCTION_SECURITY_BASELINE.md](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/PRODUCTION_SECURITY_BASELINE.md)
- [PRIVACY_GOVERNANCE_CHECKLIST.md](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/PRIVACY_GOVERNANCE_CHECKLIST.md)
- [OPERATIONS_RUNBOOK.md](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/OPERATIONS_RUNBOOK.md)

There is also an automated security validation workflow at:

- [.github/workflows/security-validation.yml](C:/Users/uistu/Documents/Codex/2026-05-25/build-a-multi-user-student-case/.github/workflows/security-validation.yml)
