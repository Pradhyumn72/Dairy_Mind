"""
Cattle Registry models.

Cattle        — core animal record
AnimalHistory — versioned audit log (create/update/delete)
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Cattle(models.Model):
    """Single dairy animal record."""

    class Gender(models.TextChoices):
        MALE = "Male", "Male"
        FEMALE = "Female", "Female"

    tag_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    breed = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender.choices)
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(max_length=1000, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cattle"
        ordering = ["tag_number"]
        verbose_name = "Cattle"
        verbose_name_plural = "Cattle"

    def __str__(self):
        return f"{self.tag_number} — {self.name}"


class AnimalHistory(models.Model):
    """
    Versioned audit log written on every create / update / delete of a Cattle record.
    """

    class ActionType(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="history"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cattle_changes",
    )
    action_type = models.CharField(max_length=10, choices=ActionType.choices)
    changed_at = models.DateTimeField(default=timezone.now)
    previous_values = models.JSONField(default=dict)
    changed_fields = models.JSONField(default=list)

    class Meta:
        db_table = "animal_history"
        ordering = ["-changed_at"]
        verbose_name = "Animal History"
        verbose_name_plural = "Animal Histories"

    def __str__(self):
        return f"[{self.action_type}] {self.cattle.tag_number} at {self.changed_at:%Y-%m-%d %H:%M}"
