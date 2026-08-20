import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "channels",
    "apps.common",
    "apps.identity",
    "apps.catalog",
    "apps.fleet",
    "apps.orders",
    "apps.shipments",
    "apps.routing",
    "apps.billing",
    "apps.tracking",
    "apps.events",
    "apps.telemetry",
    "apps.search",
    "apps.dispatch",
    "apps.ai",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.api.middleware.RequestIdMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "http://localhost:4000",
    "http://127.0.0.1:4000",
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "http://localhost:4000",
    "http://127.0.0.1:4000",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.api.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.api.permissions.IsTenantAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardLimitOffsetPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.api.exceptions.exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "300/min", "gps": "30/min"},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "apps.common.logging.RequestContextFilter",
        }
    },
    "formatters": {
        "json": {
            "()": "apps.common.logging.JsonFormatter",
        },
        "simple": {
            "format": "%(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "json" if os.environ.get("LOG_FORMAT", "json") == "json" else "simple",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.request": {"level": "WARNING", "propagate": True},
        "apps": {"level": os.environ.get("LOG_LEVEL", "INFO"), "propagate": True},
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "FleetIQ API",
    "VERSION": "v1",
}

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-change-me-please-use-32b+")
JWT_ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_MINUTES", "60"))
JWT_REFRESH_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "7"))
JWT_KID = os.environ.get("JWT_KID", "fleetiq-hs256")
FLEETIQ_ROLE = os.environ.get("FLEETIQ_ROLE", "all")
CORE_GRAPHQL_URL = os.environ.get("CORE_GRAPHQL_URL", "http://127.0.0.1:8000/graphql")
TRACKING_GRAPHQL_URL = os.environ.get("TRACKING_GRAPHQL_URL", "http://127.0.0.1:8001/graphql")
AI_GRAPHQL_URL = os.environ.get("AI_GRAPHQL_URL", "http://127.0.0.1:8002/graphql")
ANALYTICS_GRAPHQL_URL = os.environ.get("ANALYTICS_GRAPHQL_URL", "http://127.0.0.1:8003/graphql")
GATEWAY_HTTP = os.environ.get("GATEWAY_HTTP", "false").lower() == "true"
CORE_API_URL = os.environ.get("CORE_API_URL", "")
TRACKING_API_URL = os.environ.get("TRACKING_API_URL", "")

ROOT_URLCONF = {
    "all": "config.urls",
    "core": "config.urls_core",
    "tracking": "config.urls_tracking",
    "ai": "config.urls_ai",
    "analytics": "config.urls_analytics",
    "gateway": "config.urls_gateway",
}.get(FLEETIQ_ROLE, "config.urls")
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = {
    "tracking": "config.asgi_tracking.application",
    "all": "config.asgi.application",
}.get(FLEETIQ_ROLE, "config.asgi_core.application")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "fleetiq"),
        "USER": os.environ.get("POSTGRES_USER", "fleetiq"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "fleetiq"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5434"),
        "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE", "60")),
        "OPTIONS": {
            "connect_timeout": int(os.environ.get("POSTGRES_CONNECT_TIMEOUT", "5")),
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"

AUTH_PASSWORD_VALIDATORS = []

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "capacity": 1000,
            "expiry": 15,
        },
    }
}

KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() == "true"
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:19092")
KAFKA_CLIENT_ID = os.environ.get("KAFKA_CLIENT_ID", "fleetiq")

MONGO_ENABLED = os.environ.get("MONGO_ENABLED", "false").lower() == "true"
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27018")
MONGO_DB = os.environ.get("MONGO_DB", "fleetiq")
MONGO_RAW_TTL_SECONDS = int(os.environ.get("MONGO_RAW_TTL_SECONDS", "604800"))
MONGO_MINUTE_TTL_SECONDS = int(os.environ.get("MONGO_MINUTE_TTL_SECONDS", "7776000"))
TELEMETRY_BATCH_SIZE = int(os.environ.get("TELEMETRY_BATCH_SIZE", "500"))

ES_ENABLED = os.environ.get("ES_ENABLED", "false").lower() == "true"
ES_URL = os.environ.get("ES_URL", "http://127.0.0.1:9201")
