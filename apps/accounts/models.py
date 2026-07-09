"""
Custom user model with role-based access control for DairyMind.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class FarmUser(AbstractUser):
    """
    Extends Django's AbstractUser with a role field.
    Roles drive permission checks across all modules.
    """

    class Role(models.TextChoices):
        ADMIN = "Admin", "Admin"
        FARM_MANAGER = "Farm_Manager", "Farm Manager"
        VET = "Vet", "Vet"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.FARM_MANAGER,
    )

    class Meta:
        db_table = "users"
        verbose_name = "Farm User"
        verbose_name_plural = "Farm Users"

    def __str__(self):
        return f"{self.username} ({self.role})"

    # ── Role helpers ──────────────────────────────────────────────────────────

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_farm_manager(self):
        return self.role == self.Role.FARM_MANAGER

    @property
    def is_vet(self):
        return self.role == self.Role.VET
