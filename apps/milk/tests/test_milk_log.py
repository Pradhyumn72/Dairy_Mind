import pytest
from django.urls import reverse
from apps.milk.models import MilkLog
from datetime import date, timedelta

@pytest.mark.django_db
def test_create_milk_log(worker_client, cattle):
    url = reverse('milk-log-list')
    data = {
        "cattle_id": cattle.pk,
        "date": date.today().isoformat(),
        "morning_litres": 15.0,
        "evening_litres": 0.0
    }
    response = worker_client.post(url, data)
    assert response.status_code == 201
    assert MilkLog.objects.count() == 1

@pytest.mark.django_db
def test_future_date_validation(worker_client, cattle):
    url = reverse('milk-log-list')
    data = {
        "cattle_id": cattle.pk,
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "morning_litres": 10.0,
        "evening_litres": 0.0
    }
    response = worker_client.post(url, data)
    assert response.status_code == 400
    assert "future" in str(response.data).lower()
