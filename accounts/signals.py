from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import MyUser, Role
from .referrals import generate_referral_code


@receiver(post_save, sender=MyUser)
def assign_referral_code_to_agent(sender, instance, **kwargs):
    if instance.role != Role.REFERRAL or instance.referral_code:
        return
    MyUser.objects.filter(pk=instance.pk).update(referral_code=generate_referral_code())
