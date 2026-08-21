import pytest
from datetime import date, timedelta
from apps.milk.models import MilkLog
from apps.health.tasks import check_anomalies
from apps.health.models import HealthAlert

@pytest.mark.django_db
def test_anomaly_detector_no_drop(cattle):
    # Create 14 days of normal milk logs
    today = date.today()
    for i in range(14):
        log_date = today - timedelta(days=14-i)
        MilkLog.objects.create(cattle=cattle, date=log_date, morning_litres=15.0, evening_litres=0.0)
    
    # Run detector
    check_anomalies()
    
    # Should not create alert
    assert HealthAlert.objects.filter(cattle=cattle).count() == 0

@pytest.mark.django_db
def test_anomaly_detector_sudden_drop(cattle):
    # Create 13 days of normal milk logs
    today = date.today()
    for i in range(13):
        log_date = today - timedelta(days=14-i)
        MilkLog.objects.create(cattle=cattle, date=log_date, morning_litres=15.0, evening_litres=0.0)
    
    # Today: sudden drop
    MilkLog.objects.create(cattle=cattle, log_date=today, morning_litres=5.0, evening_litres=0.0)
    
    # Run detector
    check_anomalies()
    
    # Should create alert
    assert HealthAlert.objects.filter(cattle=cattle).count() == 1
    alert = HealthAlert.objects.filter(cattle=cattle).first()
    assert alert.severity in [HealthAlert.Severity.HIGH, HealthAlert.Severity.MEDIUM]
