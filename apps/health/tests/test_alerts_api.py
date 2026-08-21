import pytest
from django.urls import reverse
from apps.health.models import HealthAlert
from datetime import date

@pytest.mark.django_db
def test_alert_list(owner_client, cattle):
    HealthAlert.objects.create(cattle=cattle, alert_date=date.today(), severity=HealthAlert.Severity.HIGH, message="Test Alert")
    url = reverse('alert-list')
    response = owner_client.get(url)
    assert response.status_code == 200
    assert len(response.data['results']) == 1

@pytest.mark.django_db
def test_resolve_alert(owner_client, cattle):
    alert = HealthAlert.objects.create(cattle=cattle, alert_date=date.today(), severity=HealthAlert.Severity.HIGH, message="Test Alert")
    url = reverse('alert-acknowledge', args=[alert.pk])
    response = owner_client.post(url)
    assert response.status_code == 200
    alert.refresh_from_db()
    assert alert.is_resolved is True
