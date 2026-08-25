"""
Milk Tracker serializers.

MilkLogSerializer   — full CRUD serializer with validation rules:
                        • morning_litres >= 0
                        • evening_litres >= 0
                        • total cannot exceed 60 litres (anomaly guard)
                        • date cannot be in the future
                        • (cattle, date) uniqueness enforced on create/update

MilkStatsSerializer — read-only serializer for aggregated summary responses
                      (daily-summary, trend, top-producers endpoints).
"""
from datetime import date as _date
from decimal import Decimal

from rest_framework import serializers

from apps.cattle.models import Cattle
from .models import MilkLog

# Hard cap per-cattle per-day to guard against data-entry errors
MAX_DAILY_LITRES = Decimal("60.00")


class MilkLogSerializer(serializers.ModelSerializer):
    """
    Full MilkLog serializer.

    Read fields
    -----------
    cattle_tag  : str   — tag_number of the related Cattle (display-only)
    total_litres: Decimal — auto-computed by the model; included in responses

    Write fields
    ------------
    cattle_id   : int   — FK write path (accepts the Cattle PK on POST/PUT)

    Validation
    ----------
    1. morning_litres must be >= 0
    2. evening_litres must be >= 0
    3. morning_litres + evening_litres must not exceed MAX_DAILY_LITRES (60 L)
    4. date must not be in the future
    5. (cattle, date) must be unique — checked against DB, skipping self on update
    """

    # Read: expose the tag_number string so the frontend can display it without
    # a separate Cattle lookup.
    cattle_tag = serializers.CharField(
        source="cattle.tag_number",
        read_only=True,
        help_text="Tag number of the cattle (read-only).",
    )

    cattle_name = serializers.CharField(
        source="cattle.name",
        read_only=True,
        help_text="Name of the cattle (read-only).",
    )

    # Write: accept cattle PK; PrimaryKeyRelatedField handles FK validation.
    cattle_id = serializers.PrimaryKeyRelatedField(
        queryset=Cattle.objects.filter(is_active=True),
        source="cattle",
        write_only=True,
        help_text="PK of the Cattle record to associate this log with.",
    )

    class Meta:
        model = MilkLog
        fields = [
            "id",
            "cattle_id",       # write
            "cattle_tag",      # read
            "cattle_name",     # read
            "date",
            "morning_litres",
            "evening_litres",
            "total_litres",    # read-only, computed by model.save()
            "recorded_by",
            "created_at",
        ]
        read_only_fields = ["id", "total_litres", "created_at"]
        extra_kwargs = {
            "recorded_by": {"read_only": True},  # set in perform_create
        }

    # ── Field-level validation ────────────────────────────────────────────────

    def validate_date(self, value: _date) -> _date:
        """Reject dates in the future."""
        if value > _date.today():
            raise serializers.ValidationError(
                "Log date cannot be in the future."
            )
        return value

    def validate_morning_litres(self, value: Decimal) -> Decimal:
        """Morning yield must be non-negative."""
        if value < Decimal("0"):
            raise serializers.ValidationError(
                "morning_litres must be greater than or equal to 0."
            )
        return value

    def validate_evening_litres(self, value: Decimal) -> Decimal:
        """Evening yield must be non-negative."""
        if value < Decimal("0"):
            raise serializers.ValidationError(
                "evening_litres must be greater than or equal to 0."
            )
        return value

    # ── Object-level validation ───────────────────────────────────────────────

    def validate(self, attrs: dict) -> dict:
        """
        Cross-field validation:

        1. Total litres cap — guards against obvious data-entry errors.
           A single cattle producing more than 60 L/day is biologically
           implausible for any common dairy breed.

        2. Unique-together (cattle, date) — DRF does not enforce
           unique_together automatically when a ``source`` alias is used,
           so we check it explicitly here, skipping the current instance on
           updates so a no-op PATCH doesn't raise a false conflict.
        """
        morning = attrs.get("morning_litres", Decimal("0"))
        evening = attrs.get("evening_litres", Decimal("0"))
        total = morning + evening

        # 1. Cap guard
        if total > MAX_DAILY_LITRES:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        f"Total daily yield ({total} L) exceeds the maximum "
                        f"allowed value of {MAX_DAILY_LITRES} L. "
                        "Please verify the entered values."
                    )
                }
            )

        # 2. Unique-together check
        cattle = attrs.get("cattle")
        log_date = attrs.get("date")

        if cattle and log_date:
            qs = MilkLog.objects.filter(cattle=cattle, date=log_date)
            if self.instance is not None:          # update — exclude self
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": (
                            f"A milk log for cattle '{cattle.tag_number}' "
                            f"on {log_date} already exists."
                        )
                    }
                )

        return attrs


# ── Stats / aggregated serializers ────────────────────────────────────────────

class MilkStatsSerializer(serializers.Serializer):
    """
    Read-only serializer for aggregated milk production data.

    Used by the daily-summary, cattle trend, and top-producers endpoints.
    The exact set of fields present depends on the calling view — all fields
    are declared here for documentation purposes; none are required.

    daily-summary fields
    --------------------
    date             : date
    total_litres     : float  — herd total for the day
    cattle_count     : int    — number of cattle with logs that day
    avg_per_cattle   : float

    trend (per-cattle daily totals) fields
    --------------------------------------
    date             : date
    total_litres     : float

    top-producers fields
    --------------------
    cattle_id        : int
    tag_number       : str
    name             : str
    total_litres     : float  — sum over the requested month
    avg_daily_litres : float
    log_count        : int    — number of days logged that month
    rank             : int
    """

    date = serializers.DateField(required=False)
    total_litres = serializers.FloatField(required=False)
    cattle_count = serializers.IntegerField(required=False)
    avg_per_cattle = serializers.FloatField(required=False)
    cattle_id = serializers.IntegerField(required=False)
    tag_number = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    avg_daily_litres = serializers.FloatField(required=False)
    log_count = serializers.IntegerField(required=False)
    rank = serializers.IntegerField(required=False)
