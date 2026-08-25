"""
Cattle Registry serializers.

CattleSerializer     — full representation used for create/retrieve/update.
                       Includes computed ``age_years`` field and write
                       validation (unique tag_number, dob not in future).

CattleListSerializer — lighter projection used for list views, omitting heavy
                       text fields and adding just enough info for table rows.

AnimalHistorySerializer — read-only audit-log entry for the history endpoint.
"""
from datetime import date

from rest_framework import serializers

from .models import Cattle, AnimalHistory


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_age_years(dob: date) -> float:
    """Return fractional years between *dob* and today, rounded to 1 decimal."""
    today = date.today()
    delta_days = (today - dob).days
    return round(delta_days / 365.25, 1)


# ── Full serializer ───────────────────────────────────────────────────────────

class CattleSerializer(serializers.ModelSerializer):
    """
    Full Cattle serializer used for create, retrieve, and update operations.

    Extra computed field
    --------------------
    age_years : float
        Derived from ``date_of_birth``; read-only, not stored in the DB.

    Validation
    ----------
    * ``tag_number`` must be unique (checked against existing records,
      skipping the current instance on updates).
    * ``date_of_birth`` must not be in the future.
    """

    age_years = serializers.SerializerMethodField(
        help_text="Cattle age in fractional years, computed from date_of_birth."
    )

    class Meta:
        model = Cattle
        fields = [
            "id",
            "tag_number",
            "name",
            "breed",
            "date_of_birth",
            "age_years",        # computed
            "gender",
            "weight_kg",
            "avg_daily_milk_litres",
            "purchase_date",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "age_years", "created_at", "updated_at"]

    # ── Computed field ────────────────────────────────────────────────────────

    def get_age_years(self, obj: Cattle) -> float:
        """Compute and return age in fractional years."""
        return _compute_age_years(obj.date_of_birth)

    # ── Field-level validation ────────────────────────────────────────────────

    def validate_date_of_birth(self, value: date) -> date:
        """Reject a date_of_birth set in the future."""
        if value > date.today():
            raise serializers.ValidationError(
                "date_of_birth cannot be in the future."
            )
        return value

    def validate_tag_number(self, value: str) -> str:
        """
        Enforce uniqueness of tag_number.

        On create  : checks the entire table.
        On update  : excludes the current instance from the uniqueness check
                     so a no-op save doesn't raise a false conflict.
        """
        qs = Cattle.objects.filter(tag_number=value)
        # self.instance is set by DRF on PATCH/PUT
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A cattle record with tag_number '{value}' already exists."
            )
        return value


# ── List serializer ───────────────────────────────────────────────────────────

class CattleListSerializer(serializers.ModelSerializer):
    """
    Lightweight Cattle serializer used in list responses.

    Omits ``notes``, ``purchase_date``, and timestamp fields to reduce
    payload size when fetching many records.  Includes ``age_years`` because
    it's useful for table-row display without a detail fetch.
    """

    age_years = serializers.SerializerMethodField()

    class Meta:
        model = Cattle
        fields = [
            "id",
            "tag_number",
            "name",
            "breed",
            "gender",
            "date_of_birth",
            "age_years",
            "weight_kg",
            "avg_daily_milk_litres",
            "is_active",
        ]
        read_only_fields = fields

    def get_age_years(self, obj: Cattle) -> float:
        """Compute and return age in fractional years."""
        return _compute_age_years(obj.date_of_birth)


# ── History serializer ────────────────────────────────────────────────────────

class AnimalHistorySerializer(serializers.ModelSerializer):
    """
    Read-only serializer for AnimalHistory audit log entries.

    ``changed_by_username`` surfaces the actor's username without exposing
    the full user object.
    """

    changed_by_username = serializers.SerializerMethodField()

    class Meta:
        model = AnimalHistory
        fields = [
            "id",
            "action_type",
            "changed_at",
            "changed_by_username",
            "changed_fields",
            "previous_values",
        ]
        read_only_fields = fields

    def get_changed_by_username(self, obj: AnimalHistory) -> str | None:
        """Return the username of the actor, or None if the user was deleted."""
        if obj.changed_by:
            return obj.changed_by.username
        return None
