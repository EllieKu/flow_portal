import uuid

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import AsyncClient, Client, RequestFactory, TestCase
from django.urls import reverse

User = get_user_model()


class UserIdentityTests(TestCase):
    def test_database_rejects_duplicate_dify_identity(self):
        first = User.objects.create_user(username="first")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="second", dify_user_id=first.dify_user_id)

    def test_identity_is_unique_and_survives_account_changes(self):
        first = User.objects.create_user(username="first", password="A-valid-password-123")
        second = User.objects.create_user(username="second")
        identity = first.dify_user_id
        self.assertIsInstance(identity, uuid.UUID)
        self.assertNotEqual(identity, second.dify_user_id)

        first.username = "renamed"
        first.email = "renamed@example.com"
        first.set_password("Another-valid-password-456")
        first.save()
        first.refresh_from_db()
        self.assertEqual(first.dify_user_id, identity)


class AuthenticationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="member", password="A-valid-password-123"
        )

    def test_anonymous_user_cannot_access_portal(self):
        response = self.client.get(reverse("accounts:home"))
        self.assertRedirects(response, "/login/?next=/")

    def test_login_logout_and_post_logout_access(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "member", "password": "A-valid-password-123"},
        )
        self.assertRedirects(response, reverse("accounts:home"))
        self.assertContains(self.client.get(reverse("accounts:home")), "member")
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertRedirects(self.client.get("/"), "/login/?next=/")

    def test_invalid_password_does_not_authenticate(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "member", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_disabled_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertFalse(self.client.login(username="member", password="A-valid-password-123"))

    def test_disabling_user_invalidates_existing_access(self):
        self.client.force_login(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertRedirects(self.client.get("/"), "/login/?next=/")

    def test_login_does_not_redirect_to_external_site(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "member",
                "password": "A-valid-password-123",
                "next": "https://example.com/",
            },
        )
        self.assertRedirects(response, reverse("accounts:home"))

    def test_logout_requires_post_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.get(reverse("accounts:logout")).status_code, 405)
        self.assertEqual(client.post(reverse("accounts:logout")).status_code, 403)
        client.get(reverse("accounts:home"))
        response = client.post(
            reverse("accounts:logout"),
            {"csrfmiddlewaretoken": client.cookies["csrftoken"].value},
        )
        self.assertRedirects(response, reverse("accounts:login"))

    def test_login_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            client.post(
                reverse("accounts:login"),
                {"username": "member", "password": "A-valid-password-123"},
            ).status_code,
            403,
        )
        client.get(reverse("accounts:login"))
        response = client.post(
            reverse("accounts:login"),
            {
                "username": "member",
                "password": "A-valid-password-123",
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )
        self.assertRedirects(response, reverse("accounts:home"))

    def test_regular_user_cannot_access_admin(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:index"))
        self.assertRedirects(response, "/admin/login/?next=/admin/")
        self.assertNotContains(self.client.get("/"), 'href="/admin/"')

    async def test_portal_authentication_through_async_client(self):
        client = AsyncClient()
        response = await client.get("/")
        self.assertEqual(response.status_code, 302)
        await client.aforce_login(self.user)
        response = await client.get("/")
        self.assertEqual(response.status_code, 200)


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="administrator",
            email="admin@example.com",
            password="A-valid-admin-password-123",
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_admin_can_create_user_with_usable_password(self):
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "newmember",
                "usable_password": "true",
                "password1": "New-member-password-4862",
                "password2": "New-member-password-4862",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newmember")
        self.assertTrue(user.check_password("New-member-password-4862"))
        self.assertIsInstance(user.dify_user_id, uuid.UUID)

    def test_admin_can_create_group(self):
        response = self.client.post(
            reverse("admin:auth_group_add"), {"name": "Support", "_save": "Save"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Group.objects.filter(name="Support").exists())

    def test_identity_is_readonly_and_groups_are_manageable(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        user_admin = admin.site._registry[User]
        form = user_admin.get_form(request, obj=self.admin_user)
        self.assertNotIn("dify_user_id", form.base_fields)
        self.assertIn("groups", form.base_fields)
        response = self.client.get(
            reverse("admin:accounts_user_change", args=[self.admin_user.pk])
        )
        self.assertContains(response, str(self.admin_user.dify_user_id))

