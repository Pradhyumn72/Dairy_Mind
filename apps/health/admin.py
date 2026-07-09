from django.contrib import admin
from .models import HealthAlert, HealthRecord


@admin.register(HealthAlert)
class HealthAlertAdmin(admin.ModelAdmin):
    list_display = ("cattle", "alert_date", "alert_type", "severity", "is_resolved", "created_at")
    list_filter = ("alert_type", "severity", "is_resolved")
    search_fields = ("cattle__tag_number", "cattle__name")
    date_hierarchy = "alert_date"
    ordering = ("-created_at",)


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("cattle", "record_date", "temperature", "vet_name", "created_at")
    list_filter = ("record_date",)
    search_fields = ("cattle__tag_number", "cattle__name", "vet_name")
    date_hierarchy = "record_date"
    ordering = ("-record_date",)
