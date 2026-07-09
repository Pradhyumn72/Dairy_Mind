from django.contrib import admin
from .models import VetReport


@admin.register(VetReport)
class VetReportAdmin(admin.ModelAdmin):
    list_display = ("cattle", "original_filename", "status", "uploaded_by", "upload_date", "processed_at")
    list_filter = ("status",)
    search_fields = ("cattle__tag_number", "original_filename")
    date_hierarchy = "upload_date"
    ordering = ("-upload_date",)
    readonly_fields = ("upload_date", "processed_at", "raw_text", "ai_summary", "error_reason")
