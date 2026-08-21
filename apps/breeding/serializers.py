"""
Breeding Manager serializers.

HeatCycleLogSerializer
    Full CRUD. Read: cattle_tag. Write: cattle_id.

ArtificialInseminationSerializer
    Full CRUD. Read: cattle_tag, days_since_ai (computed).
    Write: cattle_id.

PregnancyRecordSerializer
    Full CRUD. Read: cattle_tag, days_until_calving (computed),
    gestation_progress_percent (computed).
    Write: cattle_id, ai_event (nullable OneToOne FK).

BreedingAlertSerializer
    Full fields — used by the BreedingAlertViewSet (read + mark-sent).
"""
from datetime import date
from rest_framework import serializers
from apps.cattle.models import Cattle
from .models import (
    ArtificialInsemination,
    BreedingAlert,
    HeatCycleLog,
    PregnancyRecord,
)

# Total bovine gestation length used for progress calculation
GESTATION_DAYS = 280


# ── HeatCycleLog ─────────────────────────────────────────────────────────────

class HeatCycleLogSerializer(serializers.ModelSerializer):
    """
    Serializer for HeatCycleLog records.

    Read fields
    -----------
    cattle_tag : str — tag_number of the related Cattle

    Write fields
    ------------
    cattle_id  : int — FK write path (accepts Cattle PK)
    """

    cattle_tag = serializers.CharField(
        source="cattle.tag_number",
        read_only=True,
        help_text="Tag number of the cattle (read-only).",
    )
    cattle_id = serializers.PrimaryKeyRelatedField(
        queryset=Cattle.objects.filter(is_active=True),
        source="cattle",
        write_only=True,
        help_text="PK of the active Cattle to associate this heat log with.",
    )

    class Meta:
        model  = HeatCycleLog
        fields = [
            "id",
            "cattle_id",     # write
            "cattle_tag",    # read
            "observed_date",
            "signs",
            "intensity",
            "recorded_by",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    def validate_observed_date(self, value):
        """Heat log date must not be in the future."""
        if value > date.today():
            raise serializers.ValidationError("observed_date cannot be in the future.")
        return value


# ── ArtificialInsemination ────────────────────────────────────────────────────

class ArtificialInseminationSerializer(serializers.ModelSerializer):
    """
    Serializer for ArtificialInsemination records.

    Read fields
    -----------
    cattle_tag    : str — tag_number of the related Cattle
    days_since_ai : int — calendar days elapsed since ai_date (None if future)

    Write fields
    ------------
    cattle_id     : int — FK write path
    """

    cattle_tag = serializers.CharField(
        source="cattle.tag_number",
        read_only=True,
    )
    cattle_id = serializers.PrimaryKeyRelatedField(
        queryset=Cattle.objects.filter(is_active=True),
        source="cattle",
        write_only=True,
    )
    days_since_ai = serializers.SerializerMethodField(
        help_text="Calendar days elapsed since the AI date.",
    )

    class Meta:
        model  = ArtificialInsemination
        fields = [
            "id",
            "cattle_id",        # write
            "cattle_tag",       # read
            "ai_date",
            "semen_bull_name",
            "semen_batch_id",
            "technician_name",
            "notes",
            "outcome",
            "days_since_ai",    # computed read
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "days_since_ai", "created_at", "updated_at"]

    def get_days_since_ai(self, obj: ArtificialInsemination) -> int | None:
        """Return elapsed days since ai_date, or None if the date is in the future."""
        delta = (date.today() - obj.ai_date).days
        return delta if delta >= 0 else None

    def validate_ai_date(self, value):
        """AI date must not be in the future."""
        if value > date.today():
            raise serializers.ValidationError("ai_date cannot be in the future.")
        return value


# ── PregnancyRecord ───────────────────────────────────────────────────────────

class PregnancyRecordSerializer(serializers.ModelSerializer):
    """
    Serializer for PregnancyRecord.

    Read fields
    -----------
    cattle_tag                 : str
    days_until_calving         : int  — days remaining to expected_calving_date;
                                        negative means overdue; None after calving
    gestation_progress_percent : float — 0–100 % of 280-day gestation completed;
                                          100 once calved or overdue

    Write fields
    ------------
    cattle_id  : int
    ai_event   : int (nullable) — PK of the linked ArtificialInsemination
    """

    cattle_tag = serializers.CharField(
        source="cattle.tag_number",
        read_only=True,
    )
    cattle_id = serializers.PrimaryKeyRelatedField(
        queryset=Cattle.objects.filter(is_active=True),
        source="cattle",
        write_only=True,
    )
    days_until_calving = serializers.SerializerMethodField()
    gestation_progress_percent = serializers.SerializerMethodField()

    class Meta:
        model  = PregnancyRecord
        fields = [
            "id",
            "cattle_id",                    # write
            "cattle_tag",                   # read
            "ai_event",
            "confirmed_date",
            "expected_calving_date",
            "actual_calving_date",
            "calf_gender",
            "is_active",
            "days_until_calving",           # computed read
            "gestation_progress_percent",   # computed read
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "days_until_calving",
            "gestation_progress_percent",
            "created_at",
            "updated_at",
        ]

    def get_days_until_calving(self, obj: PregnancyRecord) -> int | None:
        """
        Days remaining until expected_calving_date.

        Returns None once the actual calving date is recorded (pregnancy over).
        Negative value means the animal is overdue.
        """
        if obj.actual_calving_date:
            return None
        return (obj.expected_calving_date - date.today()).days

    def get_gestation_progress_percent(self, obj: PregnancyRecord) -> float:
        """
        Percentage of the 280-day gestation period completed.

        Clamped to [0, 100]. Returns 100 once calved or overdue.
        """
        end = obj.actual_calving_date or date.today()
        elapsed = (end - obj.confirmed_date).days
        pct = (elapsed / GESTATION_DAYS) * 100
        return round(min(max(pct, 0.0), 100.0), 1)

    def validate(self, attrs):
        """expected_calving_date must be after confirmed_date (when provided)."""
        confirmed = attrs.get("confirmed_date")
        expected  = attrs.get("expected_calving_date")
        if confirmed and expected and expected <= confirmed:
            raise serializers.ValidationError(
                {"expected_calving_date": "expected_calving_date must be after confirmed_date."}
            )
        return attrs


# ── BreedingAlert ─────────────────────────────────────────────────────────────

class BreedingAlertSerializer(serializers.ModelSerializer):
    """
    Serializer for BreedingAlert.

    cattle_tag is exposed as a read-only convenience field.
    cattle_id is the write path.
    """

    cattle_tag = serializers.CharField(
        source="cattle.tag_number",
        read_only=True,
    )
    cattle_id = serializers.PrimaryKeyRelatedField(
        queryset=Cattle.objects.all(),
        source="cattle",
        write_only=True,
    )

    class Meta:
        model  = BreedingAlert
        fields = [
            "id",
            "cattle_id",      # write
            "cattle_tag",     # read
            "alert_type",
            "scheduled_date",
            "message",
            "is_sent",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
