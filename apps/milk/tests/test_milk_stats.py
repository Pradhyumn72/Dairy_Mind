import pytest
from django.urls import reverse
from apps.milk.models import MilkLog
from datetime import date

@pytest.mark.django_db
def test_daily_summary(owner_client, cattle):
    MilkLog.objects.create(cattle=cattle, date=date.today(), morning_litres=10.0, evening_litres=0.0)
    MilkLog.objects.create(cattle=cattle, date=date.today(), morning_litres=0.0, evening_litres=12.0)
    
    url = reverse('milk-daily-summary')
    response = owner_client.get(url, {'date': date.today().isoformat()})
    assert response.status_code == 200
    assert response.data['total_liters'] == 22.0

@pytest.mark.django_db
def test_farm_trend(owner_client, cattle):
    MilkLog.objects.create(cattle=cattle, date=date.today(), morning_litres=15.0, evening_litres=0.0)
    url = reverse('milk-farm-trend')
    response = owner_client.get(url, {'days': 7})
    assert response.status_code == 200
    assert 'trend' in response.data
    assert len(response.data['trend']) >= 1
