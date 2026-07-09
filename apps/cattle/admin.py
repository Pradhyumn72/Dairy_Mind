from django.contrib import admin
from .models import Cattle, AnimalHistory


@admin.register(Cattle)
class CattleAdmin(admin.ModelAdmin):
    list_display = ("tag_number", "name", "breed", "gender", "date_of_birth", "weight_kg", "is_active")
    list_filter = ("gender", "breed", "is_active")
    search_fields = ("tag_number", "name", "breed")
    date_hierarchy = "date_of_birth"
    ordering = ("tag_number",)


@admin.register(AnimalHistory)
class AnimalHistoryAdmin(admin.ModelAdmin):
    list_display = ("cattle", "action_type", "changed_by", "changed_at")
    list_filter = ("action_type",)
    search_fields = ("cattle__tag_number",)
    readonly_fields = ("cattle", "changed_by", "action_type", "changed_at", "previous_values", "changed_fields")
    ordering = ("-changed_at",)
