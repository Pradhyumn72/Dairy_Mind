"""
Costs app serializers.

FeedLogSerializer    — CRUD serializer for FeedLog with auto-computed total_cost.
CostSummarySerializer — read-only output serializer for CostSummary model rows.
"""
from datetime import date as _date
from decimal import Decimal

from rest_framework import serializers

from apps.cattle.models import Cattle
from .models import CostSummary, FeedLog


class FeedLogSerializer(serializers.ModelSerializer):
    """
    Serializer for FeedLog.

    Read fields
    -----------
    cattle_tag  : str   — tag_number of the related Cattle
    total_cost  : Decimal — auto-computed by model.save()

    Write fields
    ------------
    cattle_id   : int   — FK write path

    Validation
    ----------
    * quantity_kg > 0
    * cost_per_kg > 0
    * date cannot be in the future
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
        help_text="PK of the active Cattle this feed log belongs to.",
    )

    class Meta:
        model  = FeedLog
        fields = [
            "id",
            "cattle_id",    # write
            "cattle_tag",   # read
            "date",
            "feed_type",
            "quantity_kg",
            "cost_per_kg",
            "total_cost",   # read-only, computed by model.save()
            "created_at",
        ]
        read_only_fields = ["id", "total_cost", "created_at"]

    def validate_date(self, value):
        if value > _date.today():
            raise serializers.ValidationError("Feed log date cannot be in the future.")
        return value

    def validate_quantity_kg(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("quantity_kg must be greater than zero.")
        return value

    def validate_cost_per_kg(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("cost_per_kg must be greater than zero.")
        return value


class CostSummarySerializer(serializers.ModelSerializer):
    """
    Read-only serializer for CostSummary model rows.
    Used by the monthly summary endpoint to return stored roll-up data.
    """

    cattle_tag  = serializers.CharField(source="cattle.tag_number", read_only=True)
    cattle_name = serializers.CharField(source="cattle.name", read_only=True)

    class Meta:
        model  = CostSummary
        fields = [
            "id",
            "cattle_id",
            "cattle_tag",
            "cattle_name",
            "month",
            "year",
            "total_feed_cost",
            "total_milk_litres",
            "cost_per_litre",
            "profit_margin",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
