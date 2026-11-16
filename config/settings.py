"""
Django settings for the Vigil project.

All sensitive values (SECRET_KEY, DATABASE_URL, ...) are read from a `.env`
file in the project root. See `.env.example` for the list of variables.
The `.env` file itself is never committed to Git.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from the .env file into os.environ.
load_dotenv(BASE_DIR / ".env")


def env(name, default=None, required=False):
    """Read a setting from the environment, failing loudly if it is required but missing."""
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Missing required environment variable: {name} (see .env.example)")
    return value


# --- Core security settings ---------------------------------------------------

SECRET_KEY = env("SECRET_KEY", required=True)
DEBUG = env("DEBUG", "False").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]


# --- Applications ---------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # CSRF protection for every POST form
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database: PostgreSQL (Supabase) -------------------------------------------
# DATABASE_URL looks like: postgresql://USER:PASSWORD@HOST:PORT/DBNAME
# There is intentionally no SQLite fallback.

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", required=True),
        conn_max_age=60,
        ssl_require=env("DB_SSL_REQUIRE", "True").lower() in ("1", "true", "yes"),
    )
}
if not DATABASES["default"]["ENGINE"].endswith("postgresql"):
    raise ImproperlyConfigured("DATABASE_URL must point to a PostgreSQL database.")


# --- Authentication -----------------------------------------------------------

# Django hashes passwords with PBKDF2-SHA256 by default; these validators enforce strong passwords.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Log the user out when the browser closes, and after 2 weeks at most.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"


# --- Internationalization -----------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True


# --- Static and media files ---------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded profile photos
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
