"""
Django-filter FilterSet for the Cattle model.

Provides exact and case-insensitive partial match filters for list views.
"""
import django_filters
from .models import Cattle


class CattleFilter(django_filters.FilterSet):
    """
    FilterSet for CattleViewSet.

    Supported query params
    ----------------------
    breed      : case-insensitive partial match  (?breed=holstein)
    gender     : exact match                     (?gender=Female)
    is_active  : boolean exact match             (?is_active=true)
    name       : case-insensitive partial match  (?name=daisy)
    tag_number : case-insensitive partial match  (?tag_number=TG)
    """

    breed = django_filters.CharFilter(
        field_name="breed", lookup_expr="icontains"
    )
    gender = django_filters.ChoiceFilter(
        field_name="gender", choices=Cattle.Gender.choices
    )
    is_active = django_filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = Cattle
        fields = ["breed", "gender", "is_active"]
