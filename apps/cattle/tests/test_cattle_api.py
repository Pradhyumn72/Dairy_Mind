import pytest
from django.urls import reverse
from apps.milk.models import MilkLog
from datetime import date

@pytest.mark.django_db
def test_milk_history(owner_client, cattle):
    MilkLog.objects.create(cattle=cattle, date=date.today(), morning_litres=10.5, evening_litres=0.0)
    url = reverse('cattle-milk-history', args=[cattle.pk])
    response = owner_client.get(url)
    assert response.status_code == 200
    assert 'logs' in response.data
    assert len(response.data['logs']) == 1

@pytest.mark.django_db
def test_dashboard(owner_client, cattle):
    url = reverse('cattle-dashboard', args=[cattle.pk])
    response = owner_client.get(url)
    assert response.status_code == 200
    assert 'tag_number' in response.data
    assert 'avg_milk_last_30_days' in response.data
