import pytest
from django.contrib.auth.models import User
from apps.accounts.models import Profile
from apps.cattle.models import Cattle
from rest_framework.test import APIClient
import factory
from django.utils import timezone
from datetime import timedelta

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    
    @factory.post_generation
    def profile(self, create, extracted, **kwargs):
        if not create:
            return
        # Profile is created via signals, so we just update it
        self.profile.role = kwargs.get('role', Profile.Role.OWNER)
        self.profile.save()

class CattleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cattle
    
    tag_number = factory.Sequence(lambda n: f"TAG-{n:04d}")
    name = factory.Faker("first_name")
    breed = "Holstein"
    gender = Cattle.Gender.FEMALE
    date_of_birth = factory.LazyFunction(lambda: timezone.now().date() - timedelta(days=1000))
    is_active = True

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def owner_user():
    return UserFactory(profile__role=Profile.Role.OWNER)

@pytest.fixture
def owner_client(api_client, owner_user):
    api_client.force_authenticate(user=owner_user)
    return api_client

@pytest.fixture
def worker_user():
    return UserFactory(profile__role=Profile.Role.WORKER)

@pytest.fixture
def worker_client(api_client, worker_user):
    api_client.force_authenticate(user=worker_user)
    return api_client

@pytest.fixture
def cattle():
    return CattleFactory()
