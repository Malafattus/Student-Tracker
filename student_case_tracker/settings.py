import os
from pathlib import Path

import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-local-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"

allowed_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts.split(",") if host.strip()]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cases',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'cases.middleware.TrustedIdentityHeaderMiddleware',
    'cases.middleware.SessionIdleTimeoutMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'student_case_tracker.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cases.context_processors.app_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'student_case_tracker.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/Toronto'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'
SITE_URL = os.environ.get("DJANGO_SITE_URL", "http://127.0.0.1:8000")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_IDLE_TIMEOUT_SECONDS = int(os.environ.get("DJANGO_SESSION_IDLE_TIMEOUT_SECONDS", "1800"))
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
LOGIN_FAILURE_LIMIT = int(os.environ.get("DJANGO_LOGIN_FAILURE_LIMIT", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("DJANGO_LOGIN_LOCKOUT_SECONDS", "900"))
MFA_FAILURE_LIMIT = int(os.environ.get("DJANGO_MFA_FAILURE_LIMIT", "5"))
MFA_LOCKOUT_SECONDS = int(os.environ.get("DJANGO_MFA_LOCKOUT_SECONDS", "900"))
SENSITIVE_ACTION_REVERIFY_SECONDS = int(os.environ.get("DJANGO_SENSITIVE_ACTION_REVERIFY_SECONDS", "600"))
TRUSTED_IDENTITY_ENABLED = os.environ.get("DJANGO_TRUSTED_IDENTITY_ENABLED", "False").lower() == "true"
TRUSTED_IDENTITY_PROVIDER_NAME = os.environ.get("DJANGO_TRUSTED_IDENTITY_PROVIDER_NAME", "School SSO")
TRUSTED_IDENTITY_EMAIL_HEADER = os.environ.get("DJANGO_TRUSTED_IDENTITY_EMAIL_HEADER", "HTTP_X_AUTHENTICATED_EMAIL")
TRUSTED_IDENTITY_NAME_HEADER = os.environ.get("DJANGO_TRUSTED_IDENTITY_NAME_HEADER", "HTTP_X_AUTHENTICATED_NAME")
MAX_UPLOAD_FILE_SIZE_BYTES = int(os.environ.get("DJANGO_MAX_UPLOAD_FILE_SIZE_BYTES", str(10 * 1024 * 1024)))
ALLOWED_UPLOAD_EXTENSIONS = [
    item.strip().lower()
    for item in os.environ.get("DJANGO_ALLOWED_UPLOAD_EXTENSIONS", ".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.jpg,.jpeg,.png").split(",")
    if item.strip()
]
CSP_DEFAULT_SRC = ("'self'",)
CSP_IMG_SRC = ("'self'", "data:")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net")
CSP_FONT_SRC = ("'self'", "data:", "https://cdn.jsdelivr.net")
CSP_SCRIPT_SRC = ("'self'",)

EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "noreply@studenttracker.local")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("DJANGO_EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_TIMEOUT = int(os.environ.get("DJANGO_EMAIL_TIMEOUT", "10"))

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true"
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_BROWSER_XSS_FILTER = True

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
