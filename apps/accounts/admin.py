from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import FarmUser


@admin.register(FarmUser)
class FarmUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("DairyMind Role", {"fields": ("role",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("DairyMind Role", {"fields": ("role",)}),
    )
