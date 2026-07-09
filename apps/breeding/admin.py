from django.contrib import admin
from .models import HeatCycleLog, ArtificialInsemination, PregnancyRecord, BreedingAlert


@admin.register(HeatCycleLog)
class HeatCycleLogAdmin(admin.ModelAdmin):
    list_display = ("cattle", "observed_date", "intensity", "recorded_by", "created_at")
    list_filter = ("intensity",)
    search_fields = ("cattle__tag_number", "cattle__name")
    date_hierarchy = "observed_date"
    ordering = ("-observed_date",)


@admin.register(ArtificialInsemination)
class ArtificialInseminationAdmin(admin.ModelAdmin):
    list_display = ("cattle", "ai_date", "semen_bull_name", "semen_batch_id", "technician_name", "outcome")
    list_filter = ("outcome",)
    search_fields = ("cattle__tag_number", "semen_bull_name", "technician_name")
    date_hierarchy = "ai_date"
    ordering = ("-ai_date",)


@admin.register(PregnancyRecord)
class PregnancyRecordAdmin(admin.ModelAdmin):
    list_display = (
        "cattle", "confirmed_date", "expected_calving_date",
        "actual_calving_date", "calf_gender", "is_active"
    )
    list_filter = ("is_active", "calf_gender")
    search_fields = ("cattle__tag_number", "cattle__name")
    date_hierarchy = "confirmed_date"
    ordering = ("-confirmed_date",)


@admin.register(BreedingAlert)
class BreedingAlertAdmin(admin.ModelAdmin):
    list_display = ("cattle", "alert_type", "scheduled_date", "is_sent", "created_at")
    list_filter = ("alert_type", "is_sent")
    search_fields = ("cattle__tag_number",)
    date_hierarchy = "scheduled_date"
    ordering = ("scheduled_date",)
