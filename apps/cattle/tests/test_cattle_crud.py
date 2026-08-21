import pytest
from django.urls import reverse
from apps.cattle.models import Cattle

@pytest.mark.django_db
def test_create_cattle(owner_client):
    url = reverse('cattle-list')
    data = {
        "tag_number": "T-100",
        "name": "Bessie",
        "breed": "Holstein",
        "gender": "Female",
        "date_of_birth": "2020-01-01",
        "purchase_date": "2021-01-01"
    }
    response = owner_client.post(url, data)
    assert response.status_code == 201
    assert Cattle.objects.count() == 1
    assert Cattle.objects.first().name == "Bessie"

@pytest.mark.django_db
def test_read_cattle(owner_client, cattle):
    url = reverse('cattle-detail', args=[cattle.pk])
    response = owner_client.get(url)
    assert response.status_code == 200
    assert response.data['tag_number'] == cattle.tag_number

@pytest.mark.django_db
def test_update_cattle(owner_client, cattle):
    url = reverse('cattle-detail', args=[cattle.pk])
    data = {"name": "Updated Name"}
    response = owner_client.patch(url, data)
    assert response.status_code == 200
    cattle.refresh_from_db()
    assert cattle.name == "Updated Name"

@pytest.mark.django_db
def test_soft_delete_deactivate(owner_client, cattle):
    url = reverse('cattle-deactivate', args=[cattle.pk])
    response = owner_client.post(url)
    assert response.status_code == 200
    cattle.refresh_from_db()
    assert cattle.is_active is False

@pytest.mark.django_db
def test_hard_delete_cattle_owner(owner_client, cattle):
    url = reverse('cattle-detail', args=[cattle.pk])
    response = owner_client.delete(url)
    assert response.status_code == 204
    assert Cattle.objects.count() == 0

@pytest.mark.django_db
def test_hard_delete_cattle_worker(worker_client, cattle):
    url = reverse('cattle-detail', args=[cattle.pk])
    response = worker_client.delete(url)
    assert response.status_code == 403
    assert Cattle.objects.count() == 1
