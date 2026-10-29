import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()

# Serve local CSS/JS with Uvicorn during development, just as runserver does.
from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

if settings.DEBUG:
    application = ASGIStaticFilesHandler(application)

