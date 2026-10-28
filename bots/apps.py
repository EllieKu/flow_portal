from django.apps import AppConfig


class BotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bots"
    verbose_name = "Bot 管理"

    def ready(self):
        from . import signals  # noqa: F401

