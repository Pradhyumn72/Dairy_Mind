import pytest
from datetime import date, timedelta
from apps.milk.models import MilkLog
from apps.forecast.ml.production_forecaster import MilkProductionForecaster

@pytest.mark.django_db
def test_forecaster_output_shape(cattle):
    today = date.today()
    # Create 60 days of milk logs
    for i in range(60):
        log_date = today - timedelta(days=60-i)
        MilkLog.objects.create(cattle=cattle, date=log_date, morning_litres=10.0 + (i * 0.1), evening_litres=0.0)
    
    forecaster = MilkProductionForecaster()
    # Mock model fitting for test
    df = forecaster.fit_and_forecast(cattle_id=cattle.pk, days_history=60, forecast_days=7)
    
    assert len(df) == 7
    assert 'ds' in df.columns
    assert 'yhat' in df.columns
    assert 'yhat_lower' in df.columns
    assert 'yhat_upper' in df.columns
