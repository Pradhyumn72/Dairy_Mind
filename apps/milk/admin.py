from django.contrib import admin
from .models import MilkLog


@admin.register(MilkLog)
class MilkLogAdmin(admin.ModelAdmin):
    list_display = ("cattle", "date", "morning_litres", "evening_litres", "total_litres", "recorded_by")
    list_filter = ("date",)
    search_fields = ("cattle__tag_number", "cattle__name")
    date_hierarchy = "date"
    ordering = ("-date",)
