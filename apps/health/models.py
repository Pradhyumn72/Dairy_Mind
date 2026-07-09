"""
Health Alert Engine models.

HealthAlert  — system or manual alert tied to a Cattle record
HealthRecord — veterinary examination record
"""
from django.conf import settings
from django.db import models
from apps.cattle.models import Cattle


class HealthAlert(models.Model):

    class AlertType(models.TextChoices):
        ANOMALY = "ANOMALY", "Anomaly (ML-detected)"
        MANUAL = "MANUAL", "Manual"
        FORECAST = "FORECAST", "Forecast-based"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="health_alerts"
    )
    alert_date = models.DateField()
    alert_type = models.CharField(max_length=10, choices=AlertType.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    message = models.TextField()

    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="resolved_alerts",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "health_alerts"
        ordering = ["-created_at"]
        verbose_name = "Health Alert"
        verbose_name_plural = "Health Alerts"

    def __str__(self):
        return f"[{self.severity}] {self.alert_type} — {self.cattle.tag_number} | {self.alert_date}"


class HealthRecord(models.Model):
    """Manual veterinary examination entry."""

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="health_records"
    )
    record_date = models.DateField()
    temperature = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="Body temperature in °C"
    )
    symptoms = models.TextField(blank=True, default="")
    treatment = models.TextField(blank=True, default="")
    vet_name = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "health_records"
        ordering = ["-record_date"]
        verbose_name = "Health Record"
        verbose_name_plural = "Health Records"

    def __str__(self):
        return f"{self.cattle.tag_number} | {self.record_date} | Vet: {self.vet_name or 'N/A'}"
