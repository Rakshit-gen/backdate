from django.apps import AppConfig


class BackdateConfig(AppConfig):
    name = "backdate"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "backdate"

    def ready(self) -> None:
        from backdate.derive.registry import load_configured_modules

        load_configured_modules()
