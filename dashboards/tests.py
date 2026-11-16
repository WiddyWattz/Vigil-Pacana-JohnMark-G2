from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class RoleAccessTests(TestCase):
    def setUp(self):
        self.rider = User.objects.create_user("rider", "rider@example.com", "Rider-Pass-123")
        self.admin = User.objects.create_user("boss", "boss@example.com", "Admin-Pass-123", role=User.Role.ADMIN)

    def login(self, user):
        self.client.force_login(user)

    def test_anonymous_redirected_to_login(self):
        for name in ("dashboards:home", "dashboards:rider_dashboard", "dashboards:admin_dashboard", "dashboards:manage_users"):
            resp = self.client.get(reverse(name))
            self.assertRedirects(resp, f"{reverse('accounts:login')}?next={reverse(name)}", msg_prefix=name)

    def test_home_redirects_by_role(self):
        self.login(self.rider)
        self.assertRedirects(self.client.get(reverse("dashboards:home")), reverse("dashboards:rider_dashboard"))
        self.login(self.admin)
        self.assertRedirects(self.client.get(reverse("dashboards:home")), reverse("dashboards:admin_dashboard"))

    def test_rider_cannot_open_admin_pages(self):
        self.login(self.rider)
        self.assertEqual(self.client.get(reverse("dashboards:rider_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboards:admin_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboards:manage_users")).status_code, 403)
        resp = self.client.post(reverse("dashboards:update_user", args=[self.admin.pk]), {"action": "toggle_active"})
        self.assertEqual(resp.status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_cannot_open_rider_dashboard(self):
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("dashboards:admin_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboards:rider_dashboard")).status_code, 403)

    def test_dashboards_show_role_specific_content(self):
        self.login(self.rider)
        resp = self.client.get(reverse("dashboards:rider_dashboard"))
        self.assertContains(resp, "Speed Alert")
        self.assertNotContains(resp, "Manage Users")
        self.login(self.admin)
        resp = self.client.get(reverse("dashboards:admin_dashboard"))
        self.assertContains(resp, "Manage Users")
        self.assertContains(resp, "Role breakdown")

    def test_superuser_is_always_admin(self):
        su = User.objects.create_superuser("root", "root@example.com", "Root-Pass-123")
        self.assertEqual(su.role, User.Role.ADMIN)


class ManageUsersTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", "boss@example.com", "Admin-Pass-123", role=User.Role.ADMIN)
        self.rider = User.objects.create_user("rider", "rider@example.com", "Rider-Pass-123", first_name="Pedro")
        self.client.force_login(self.admin)
        self.url = reverse("dashboards:update_user", args=[self.rider.pk])

    def test_search_and_filter(self):
        resp = self.client.get(reverse("dashboards:manage_users"), {"q": "pedro"})
        self.assertContains(resp, "@rider")
        self.assertNotContains(resp, "@boss ")
        resp = self.client.get(reverse("dashboards:manage_users"), {"role": "ADMIN"})
        self.assertNotContains(resp, "@rider")

    def test_change_role_and_toggle_active(self):
        self.client.post(self.url, {"action": "set_role", "role": "ADMIN"})
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.role, User.Role.ADMIN)
        self.client.post(self.url, {"action": "toggle_active"})
        self.rider.refresh_from_db()
        self.assertFalse(self.rider.is_active)

    def test_admin_cannot_change_self(self):
        self.client.post(reverse("dashboards:update_user", args=[self.admin.pk]), {"action": "set_role", "role": "RIDER"})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)

    def test_update_requires_post_and_valid_role(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.post(self.url, {"action": "set_role", "role": "SUPERHERO"})
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.role, User.Role.RIDER)

    def test_no_open_redirect(self):
        resp = self.client.post(self.url, {"action": "toggle_active", "next": "https://evil.example.com/"})
        self.assertRedirects(resp, reverse("dashboards:manage_users"))
