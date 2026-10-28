from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .access import invalidate_grants
from .models import Bot

User = get_user_model()


@receiver(post_save, sender=Bot)
@receiver(post_delete, sender=Bot)
@receiver(post_save, sender=User)
@receiver(post_delete, sender=User)
@receiver(post_delete, sender=Group)
def invalidate_after_save(sender, using, **kwargs):
    transaction.on_commit(invalidate_grants, using=using)


@receiver(m2m_changed, sender=Bot.allowed_users.through)
@receiver(m2m_changed, sender=Bot.allowed_groups.through)
@receiver(m2m_changed, sender=User.groups.through)
def invalidate_after_membership_change(sender, action, using, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        transaction.on_commit(invalidate_grants, using=using)

