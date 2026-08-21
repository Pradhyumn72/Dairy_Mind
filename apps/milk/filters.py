"""
Django-filter FilterSet for the MilkLog model.

Provides exact and range filters used by MilkLogViewSet.
"""
import django_filters
from .models import MilkLog


class MilkLogFilter(django_filters.FilterSet):
    """
    FilterSet for MilkLogViewSet.

    Supported query params
    ----------------------
    cattle      : int exact     (?cattle=3)
    date        : date exact    (?date=2024-06-15)
    date_from   : date >=       (?date_from=2024-06-01)
    date_to     : date <=       (?date_to=2024-06-30)
    """

    cattle = django_filters.NumberFilter(field_name="cattle__id")
    date = django_filters.DateFilter(field_name="date")
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = MilkLog
        fields = ["cattle", "date", "date_from", "date_to"]
