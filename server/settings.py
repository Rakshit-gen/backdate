"""Settings for running backdate as a service.

Everything that differs between environments comes from env vars. Defaults
are for local development only; ``BACKDATE_ENV=production`` refuses to start
with the development secret key.
"""

from __future__ import annotations

from pathlib import Path

from server.env import ConfigError, env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

ENVIRONMENT = env_str("BACKDATE_ENV", "development")
_DEV_SECRET = "dev-only-not-a-secret"  # noqa: S105
SECRET_KEY = env_str("DJANGO_SECRET_KEY", _DEV_SECRET)
if ENVIRONMENT == "production" and SECRET_KEY == _DEV_SECRET:
    raise ConfigError("DJANGO_SECRET_KEY must be set in production")

DEBUG = env_bool("DJANGO_DEBUG", ENVIRONMENT == "development")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "backdate",
    "examples.payroll",
]

MIDDLEWARE = [
    "backdate.api.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "backdate.api.middleware.ApiKeyAuthMiddleware",
]

ROOT_URLCONF = "server.urls"
WSGI_APPLICATION = "server.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("PGDATABASE", "backdate"),
        "USER": env_str("PGUSER", ""),
        "PASSWORD": env_str("PGPASSWORD", ""),
        "HOST": env_str("PGHOST", "localhost"),
        "PORT": env_str("PGPORT", "5433"),
        # Short-lived connections by default. Behind pgbouncer in transaction
        # mode, keep this at 0 and leave server-side cursors off.
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 0),
        "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {
            "connect_timeout": env_int("DB_CONNECT_TIMEOUT", 5),
            # A statement that runs longer than this is a bug or a stuck lock.
            "options": f"-c statement_timeout={env_int('DB_STATEMENT_TIMEOUT_MS', 15000)}"
            f" -c lock_timeout={env_int('DB_LOCK_TIMEOUT_MS', 5000)}"
            f" -c idle_in_transaction_session_timeout="
            f"{env_int('DB_IDLE_TX_TIMEOUT_MS', 30000)}",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"
X_FRAME_OPTIONS = "DENY"

BACKDATE = {
    # How long a worker owns a claimed computation before someone else may take it.
    "LEASE_SECONDS": env_int("BACKDATE_LEASE_SECONDS", 30),
    "MAX_ATTEMPTS": env_int("BACKDATE_MAX_ATTEMPTS", 5),
    # Writes are refused with 503 once a tenant has this many results waiting
    # to be recomputed. 0 turns the check off.
    "MAX_STALE_BACKLOG": env_int("BACKDATE_MAX_STALE_BACKLOG", 50000),
    "MAX_OPS_PER_CHANGESET": env_int("BACKDATE_MAX_OPS_PER_CHANGESET", 500),
    "MAX_BODY_BYTES": env_int("BACKDATE_MAX_BODY_BYTES", 1_000_000),
    "DERIVATION_MODULES": env_list("BACKDATE_DERIVATION_MODULES", ["examples.payroll.derivations"]),
}

DATA_UPLOAD_MAX_MEMORY_SIZE = BACKDATE["MAX_BODY_BYTES"]

LOG_LEVEL = env_str("LOG_LEVEL", "INFO")
LOG_JSON = env_bool("LOG_JSON", ENVIRONMENT != "development")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}
