"""Shared access policy: explicit user OR group grant, with a short-lived cache."""

import logging
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import Bot

logger = logging.getLogger(__name__)
NAMESPACE_KEY = "bots:grant-namespace"


def invalidate_grants():
    """Rotate the namespace rather than enumerate user keys."""
    try:
        cache.set(NAMESPACE_KEY, uuid.uuid4().hex, timeout=None)
    except Exception:
        logger.warning("Unable to invalidate Bot grant cache", exc_info=True)


def available_bots(user):
    if not user.is_authenticated or not user.is_active:
        return Bot.objects.none()

    key = None
    bot_ids = None
    try:
        namespace = cache.get_or_set(NAMESPACE_KEY, uuid.uuid4().hex, timeout=None)
        key = f"bots:grants:{namespace}:{user.pk}"
        bot_ids = cache.get(key)
    except Exception:
        logger.warning("Unable to read Bot grant cache; querying database", exc_info=True)

    if bot_ids is None:
        bot_ids = list(
            Bot.objects.filter(is_active=True)
            .filter(Q(allowed_users=user) | Q(allowed_groups__user=user))
            .values_list("pk", flat=True)
            .distinct()
        )
        if key is not None:
            try:
                cache.set(key, bot_ids, timeout=settings.BOT_GRANT_CACHE_TTL)
            except Exception:
                logger.warning("Unable to write Bot grant cache", exc_info=True)

    # Re-read Bot data; connection settings and active status are never cached here.
    return Bot.objects.filter(pk__in=bot_ids, is_active=True)


def authorized_bot(user, pk):
    # Use the same policy for the list and direct URLs; do not reveal hidden Bots.
    return get_object_or_404(available_bots(user), pk=pk)

