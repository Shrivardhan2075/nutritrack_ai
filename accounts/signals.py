from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=User)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    """Every new User automatically gets a Profile row (1:1)."""
    if created:
        Profile.objects.create(user=instance)
