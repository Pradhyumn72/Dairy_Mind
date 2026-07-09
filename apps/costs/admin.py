from django.contrib import admin
from .models import FeedLog, CostSummary


@admin.register(FeedLog)
class FeedLogAdmin(admin.ModelAdmin):
    list_display = ("cattle", "date", "feed_type", "quantity_kg", "cost_per_kg", "total_cost")
    list_filter = ("feed_type", "date")
    search_fields = ("cattle__tag_number", "cattle__name", "feed_type")
    date_hierarchy = "date"
    ordering = ("-date",)


@admin.register(CostSummary)
class CostSummaryAdmin(admin.ModelAdmin):
    list_display = ("cattle", "month", "year", "total_feed_cost", "total_milk_litres", "cost_per_litre", "profit_margin")
    list_filter = ("year", "month")
    search_fields = ("cattle__tag_number", "cattle__name")
    ordering = ("-year", "-month")
