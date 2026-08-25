from django.apps import AppConfig


class BreedingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.breeding"
    verbose_name = "Breeding Manager"

    def ready(self):
        """
        Import signal receivers when the app is ready so they are connected
        before any request or task fires.  The import registers the
        @receiver-decorated functions in breeding/signals.py.
        """
        import apps.breeding.signals  # noqa: F401
