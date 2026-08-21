"""
Django-filter FilterSets for the Breeding Manager app.
"""
import django_filters
from .models import ArtificialInsemination, BreedingAlert, HeatCycleLog, PregnancyRecord


class HeatCycleLogFilter(django_filters.FilterSet):
    """
    Supported query params
    ----------------------
    cattle          int exact      (?cattle=3)
    date_from       date >=        (?date_from=2024-01-01)
    date_to         date <=        (?date_to=2024-06-30)
    intensity       str exact      (?intensity=STRONG)
    """
    cattle    = django_filters.NumberFilter(field_name="cattle__id")
    date_from = django_filters.DateFilter(field_name="observed_date", lookup_expr="gte")
    date_to   = django_filters.DateFilter(field_name="observed_date", lookup_expr="lte")
    intensity = django_filters.ChoiceFilter(
        field_name="intensity", choices=HeatCycleLog.Intensity.choices
    )

    class Meta:
        model  = HeatCycleLog
        fields = ["cattle", "date_from", "date_to", "intensity"]


class ArtificialInseminationFilter(django_filters.FilterSet):
    """
    Supported query params
    ----------------------
    cattle      int exact   (?cattle=3)
    date_from   date >=     (?date_from=2024-01-01)
    date_to     date <=     (?date_to=2024-12-31)
    outcome     str exact   (?outcome=CONFIRMED_PREGNANT)
    """
    cattle    = django_filters.NumberFilter(field_name="cattle__id")
    date_from = django_filters.DateFilter(field_name="ai_date", lookup_expr="gte")
    date_to   = django_filters.DateFilter(field_name="ai_date", lookup_expr="lte")
    outcome   = django_filters.ChoiceFilter(
        field_name="outcome", choices=ArtificialInsemination.Outcome.choices
    )

    class Meta:
        model  = ArtificialInsemination
        fields = ["cattle", "date_from", "date_to", "outcome"]


class PregnancyRecordFilter(django_filters.FilterSet):
    """
    Supported query params
    ----------------------
    cattle      int exact   (?cattle=3)
    is_active   bool        (?is_active=true)
    """
    cattle    = django_filters.NumberFilter(field_name="cattle__id")
    is_active = django_filters.BooleanFilter(field_name="is_active")

    class Meta:
        model  = PregnancyRecord
        fields = ["cattle", "is_active"]


class BreedingAlertFilter(django_filters.FilterSet):
    """
    Supported query params
    ----------------------
    cattle      int exact   (?cattle=3)
    is_sent     bool        (?is_sent=false)
    alert_type  str exact   (?alert_type=HEAT_DUE)
    """
    cattle     = django_filters.NumberFilter(field_name="cattle__id")
    is_sent    = django_filters.BooleanFilter(field_name="is_sent")
    alert_type = django_filters.ChoiceFilter(
        field_name="alert_type", choices=BreedingAlert.AlertType.choices
    )

    class Meta:
        model  = BreedingAlert
        fields = ["cattle", "is_sent", "alert_type"]
