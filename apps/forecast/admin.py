from django.contrib import admin
from .models import ProductionForecast


@admin.register(ProductionForecast)
class ProductionForecastAdmin(admin.ModelAdmin):
    list_display = ("cattle", "forecast_date", "predicted_litres", "confidence_lower", "confidence_upper", "generated_at")
    list_filter = ("generated_at",)
    search_fields = ("cattle__tag_number",)
    date_hierarchy = "forecast_date"
    ordering = ("forecast_date",)
