from django.apps import AppConfig


class HealthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.health"
    verbose_name = "Health Alerts"

    def ready(self):
        """
        Import signal receivers when the app is ready so they are connected
        before any task fires.  The import itself registers the receivers via
        the @receiver decorator in receivers.py.
        """
        import apps.health.receivers  # noqa: F401
