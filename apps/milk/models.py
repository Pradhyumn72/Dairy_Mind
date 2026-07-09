"""
Milk Tracker model.

MilkLog — daily per-cattle production record.
total_litres is auto-computed from morning + evening on save.
"""
from django.conf import settings
from django.db import models
from apps.cattle.models import Cattle


class MilkLog(models.Model):
    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="milk_logs"
    )
    date = models.DateField()
    morning_litres = models.DecimalField(max_digits=6, decimal_places=2)
    evening_litres = models.DecimalField(max_digits=6, decimal_places=2)
    total_litres = models.DecimalField(
        max_digits=7, decimal_places=2, editable=False
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="milk_logs_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "milk_logs"
        unique_together = [("cattle", "date")]
        ordering = ["-date"]
        verbose_name = "Milk Log"
        verbose_name_plural = "Milk Logs"

    def save(self, *args, **kwargs):
        # Auto-compute total (Req 3 AC2)
        self.total_litres = self.morning_litres + self.evening_litres
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cattle.tag_number} | {self.date} | {self.total_litres} L"
