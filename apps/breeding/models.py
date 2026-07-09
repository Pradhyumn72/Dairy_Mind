"""
Breeding Manager models.

HeatCycleLog         — observed estrus events
ArtificialInsemination — AI events with outcome tracking
PregnancyRecord      — gestation tracking (expected_calving_date auto-computed)
BreedingAlert        — scheduled alerts for heat / pregnancy milestones
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from apps.cattle.models import Cattle


class HeatCycleLog(models.Model):

    class Intensity(models.TextChoices):
        WEAK = "WEAK", "Weak"
        MODERATE = "MODERATE", "Moderate"
        STRONG = "STRONG", "Strong"

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="heat_cycles"
    )
    observed_date = models.DateField()
    signs = models.TextField(blank=True, default="")
    intensity = models.CharField(max_length=10, choices=Intensity.choices)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="heat_cycles_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "heat_cycle_logs"
        ordering = ["-observed_date"]
        verbose_name = "Heat Cycle Log"
        verbose_name_plural = "Heat Cycle Logs"

    def __str__(self):
        return f"{self.cattle.tag_number} | {self.observed_date} | {self.intensity}"


class ArtificialInsemination(models.Model):

    class Outcome(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED_PREGNANT = "CONFIRMED_PREGNANT", "Confirmed Pregnant"
        FAILED = "FAILED", "Failed"

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="ai_events"
    )
    ai_date = models.DateField()
    semen_bull_name = models.CharField(max_length=150)
    semen_batch_id = models.CharField(max_length=100)
    technician_name = models.CharField(max_length=150)
    notes = models.TextField(blank=True, default="")
    outcome = models.CharField(
        max_length=20, choices=Outcome.choices, default=Outcome.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "artificial_inseminations"
        ordering = ["-ai_date"]
        verbose_name = "Artificial Insemination"
        verbose_name_plural = "Artificial Inseminations"

    def __str__(self):
        return f"{self.cattle.tag_number} | {self.ai_date} | {self.outcome}"


class PregnancyRecord(models.Model):

    class CalfGender(models.TextChoices):
        MALE = "Male", "Male"
        FEMALE = "Female", "Female"
        UNKNOWN = "Unknown", "Unknown"

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="pregnancies"
    )
    # Optional link back to the AI event that caused this pregnancy
    ai_event = models.OneToOneField(
        ArtificialInsemination,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="pregnancy",
    )
    confirmed_date = models.DateField()
    # Auto-computed as confirmed_date + 280 days if not provided explicitly
    expected_calving_date = models.DateField()
    actual_calving_date = models.DateField(null=True, blank=True)
    calf_gender = models.CharField(
        max_length=10, choices=CalfGender.choices, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pregnancy_records"
        ordering = ["-confirmed_date"]
        verbose_name = "Pregnancy Record"
        verbose_name_plural = "Pregnancy Records"

    def save(self, *args, **kwargs):
        # Auto-compute expected calving date if not explicitly set (Req 8 AC4)
        if not self.expected_calving_date:
            self.expected_calving_date = self.confirmed_date + timedelta(days=280)
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.cattle.tag_number} | confirmed {self.confirmed_date} "
            f"| due {self.expected_calving_date}"
        )


class BreedingAlert(models.Model):

    class AlertType(models.TextChoices):
        HEAT_DUE = "HEAT_DUE", "Heat Due"
        BEST_BREED_WINDOW = "BEST_BREED_WINDOW", "Best Breeding Window"
        PREGNANCY_CHECK_DUE = "PREGNANCY_CHECK_DUE", "Pregnancy Check Due"
        CALVING_SOON = "CALVING_SOON", "Calving Soon"

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="breeding_alerts"
    )
    alert_type = models.CharField(max_length=25, choices=AlertType.choices)
    scheduled_date = models.DateField()
    message = models.TextField()
    is_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "breeding_alerts"
        ordering = ["scheduled_date"]
        verbose_name = "Breeding Alert"
        verbose_name_plural = "Breeding Alerts"

    def __str__(self):
        return f"{self.cattle.tag_number} | {self.alert_type} | {self.scheduled_date} | sent={self.is_sent}"
