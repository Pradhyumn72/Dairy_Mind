"""
Profile model extending Django's built-in User model with role-based access.
"""
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    """
    Extends Django's User model with additional details.
    """

    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        WORKER = "WORKER", "Worker"
        VET = "VET", "Vet"

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OWNER,
    )
    farm_name = models.CharField(max_length=200, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    
    class Meta:
        db_table = "user_profiles"
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_worker(self):
        return self.role == self.Role.WORKER

    @property
    def is_vet(self):
        return self.role == self.Role.VET


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
