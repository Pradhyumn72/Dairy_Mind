"""
Production Forecast model.

ProductionForecast — Prophet-generated per-day prediction for a Cattle record.
cattle=NULL stores a herd-level aggregate forecast.
"""
from django.db import models
from apps.cattle.models import Cattle


class ProductionForecast(models.Model):
    # NULL = herd-level forecast
    cattle = models.ForeignKey(
        Cattle,
        on_delete=models.CASCADE,
        related_name="forecasts",
        null=True, blank=True,
    )
    forecast_date = models.DateField()
    predicted_litres = models.DecimalField(max_digits=8, decimal_places=2)
    confidence_lower = models.DecimalField(max_digits=8, decimal_places=2)
    confidence_upper = models.DecimalField(max_digits=8, decimal_places=2)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "production_forecasts"
        ordering = ["forecast_date"]
        verbose_name = "Production Forecast"
        verbose_name_plural = "Production Forecasts"

    def __str__(self):
        target = self.cattle.tag_number if self.cattle else "Herd"
        return f"Forecast [{target}] {self.forecast_date} — {self.predicted_litres} L"
