from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .access import available_bots
from .models import Bot

User = get_user_model()


class BotAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="member")
        cls.other = User.objects.create_user(username="other")
        cls.group = Group.objects.create(name="Support")
        cls.user.groups.add(cls.group)
        cls.personal = Bot.objects.create(name="Personal", api_key_env="DIFY_PERSONAL_KEY")
        cls.shared = Bot.objects.create(name="Shared", api_key_env="DIFY_SHARED_KEY")
        cls.hidden = Bot.objects.create(name="Hidden", api_key_env="DIFY_HIDDEN_KEY")
        cls.disabled = Bot.objects.create(
            name="Disabled", api_key_env="DIFY_DISABLED_KEY", is_active=False
        )
        cls.personal.allowed_users.add(cls.user)
        cls.shared.allowed_groups.add(cls.group)
        cls.shared.allowed_users.add(cls.user)
        cls.disabled.allowed_users.add(cls.user)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_list_uses_union_without_duplicates_and_hides_disabled(self):
        self.assertEqual(
            list(available_bots(self.user)), [self.personal, self.shared]
        )
        response = self.client.get(reverse("bots:list"))
        self.assertContains(response, "Personal")
        self.assertContains(response, "Shared")
        self.assertNotContains(response, "Hidden")
        self.assertNotContains(response, "Disabled")
        self.assertContains(self.client.get("/"), "我的 Bot")

    def test_direct_access_uses_same_policy(self):
        self.assertEqual(self.client.get(self.personal.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(self.disabled.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get("/bots/999999/chat/").status_code, 404)

    def test_anonymous_cannot_list_or_open_bot(self):
        self.client.logout()
        for url in [reverse("bots:list"), self.personal.get_absolute_url()]:
            response = self.client.get(url)
            self.assertRedirects(response, f"/login/?next={url}")

    def test_admin_does_not_implicitly_have_bot_access(self):
        admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="Admin-password-123"
        )
        self.assertEqual(list(available_bots(admin)), [])
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.personal.get_absolute_url()).status_code, 404)

    def test_different_users_do_not_share_grants(self):
        self.assertEqual(len(list(available_bots(self.user))), 2)
        self.assertEqual(list(available_bots(self.other)), [])
        self.client.force_login(self.other)
        self.assertContains(self.client.get(reverse("bots:list")), "目前沒有可使用的 Bot")

    def test_cache_hit_skips_grant_query(self):
        with self.assertNumQueries(2):
            self.assertEqual(len(list(available_bots(self.user))), 2)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(available_bots(self.user))), 2)

    def test_empty_result_is_cached(self):
        self.assertEqual(list(available_bots(self.other)), [])
        with self.assertNumQueries(0):
            self.assertEqual(list(available_bots(self.other)), [])

    def test_personal_revoke_invalidates_cached_grants(self):
        list(available_bots(self.user))
        with self.captureOnCommitCallbacks(execute=True):
            self.personal.allowed_users.remove(self.user)
        self.assertNotIn(self.personal, available_bots(self.user))
        self.assertEqual(self.client.get(self.personal.get_absolute_url()).status_code, 404)

    def test_group_membership_revoke_and_reverse_add_invalidate(self):
        # This Bot has only a group grant after removing the personal grant.
        with self.captureOnCommitCallbacks(execute=True):
            self.shared.allowed_users.clear()
        self.assertIn(self.shared, available_bots(self.user))
        with self.captureOnCommitCallbacks(execute=True):
            self.user.groups.clear()
        self.assertNotIn(self.shared, available_bots(self.user))
        with self.captureOnCommitCallbacks(execute=True):
            self.group.user_set.add(self.user)
        self.assertIn(self.shared, available_bots(self.user))

    def test_group_grant_revocation_invalidates(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.shared.allowed_users.clear()
        list(available_bots(self.user))
        with self.captureOnCommitCallbacks(execute=True):
            self.shared.allowed_groups.clear()
        self.assertNotIn(self.shared, available_bots(self.user))

    def test_disabled_and_reenabled_bot_updates_access(self):
        list(available_bots(self.user))
        with self.captureOnCommitCallbacks(execute=True):
            self.personal.is_active = False
            self.personal.save()
        self.assertNotIn(self.personal, available_bots(self.user))
        with self.captureOnCommitCallbacks(execute=True):
            self.personal.is_active = True
            self.personal.save()
        self.assertIn(self.personal, available_bots(self.user))

    def test_disabled_user_cannot_access_bot_with_cached_grant(self):
        list(available_bots(self.user))
        self.user.is_active = False
        self.user.save()
        self.assertEqual(list(available_bots(self.user)), [])
        self.assertRedirects(
            self.client.get(self.personal.get_absolute_url()),
            f"/login/?next={self.personal.get_absolute_url()}",
        )

    def test_cache_expiry_reloads_grants(self):
        with self.settings(BOT_GRANT_CACHE_TTL=0):
            list(available_bots(self.user))
            with self.assertNumQueries(2):
                list(available_bots(self.user))

    def test_cache_failure_falls_back_to_database(self):
        with patch("bots.access.cache.get_or_set", side_effect=ConnectionError):
            with self.assertLogs("bots.access", level="WARNING"):
                self.assertEqual(list(available_bots(self.user)), [self.personal, self.shared])

    def test_connection_settings_are_not_rendered(self):
        self.personal.api_base_url = "https://private-dify.example.test/v1"
        self.personal.save()
        for url in [reverse("bots:list"), self.personal.get_absolute_url()]:
            response = self.client.get(url)
            self.assertNotContains(response, "DIFY_PERSONAL_KEY")
            self.assertNotContains(response, "private-dify.example.test")
            self.assertIn("no-store", response.headers["Cache-Control"])


class BotAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="Admin-password-123"
        )
        self.user = User.objects.create_user(username="member")
        self.group = Group.objects.create(name="Support")
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_admin_can_create_bot_with_user_and_group_grants(self):
        response = self.client.post(reverse("admin:bots_bot_add"), {
            "name": "Helpdesk",
            "description": "Support assistant",
            "is_active": "on",
            "api_base_url": "https://api.dify.ai/v1",
            "api_key_env": "DIFY_SUPPORT_API_KEY",
            "allowed_users": [self.user.pk],
            "allowed_groups": [self.group.pk],
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        bot = Bot.objects.get(name="Helpdesk")
        self.assertIn(self.user, bot.allowed_users.all())
        self.assertIn(self.group, bot.allowed_groups.all())

    def test_user_without_admin_permission_cannot_create_bot(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("admin:bots_bot_add"), {"name": "Forbidden"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Bot.objects.exists())

    def test_invalid_connection_configuration_is_rejected(self):
        for changes in [
            {"api_key_env": "app-a-secret-key"},
            {"api_base_url": "ftp://example.com/v1"},
        ]:
            bot = Bot(name="Invalid", api_key_env="DIFY_KEY")
            for field, value in changes.items():
                setattr(bot, field, value)
            with self.assertRaises(ValidationError):
                bot.full_clean()
