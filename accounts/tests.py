from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import LoginActivity

User = get_user_model()

VALID = {
    "first_name": "Juan", "last_name": "Dela Cruz", "username": "juan", "email": "juan@example.com",
    "contact_number": "09171234567", "password1": "Sup3r-Secret!", "password2": "Sup3r-Secret!",
}


class RegistrationTests(TestCase):
    url = reverse("accounts:register")

    def test_register_creates_rider_with_hashed_password(self):
        resp = self.client.post(self.url, VALID)
        self.assertRedirects(resp, reverse("accounts:login"))
        user = User.objects.get(username="juan")
        self.assertEqual(user.role, User.Role.RIDER)
        self.assertNotEqual(user.password, VALID["password1"])  # never stored as plain text
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(user.check_password(VALID["password1"]))

    def test_password_mismatch(self):
        resp = self.client.post(self.url, {**VALID, "password2": "different-Pass1"})
        self.assertContains(resp, "Passwords do not match.")
        self.assertFalse(User.objects.exists())

    def test_duplicate_username_and_email_case_insensitive(self):
        User.objects.create_user("juan", "juan@example.com", "x-Pass-1234")
        resp = self.client.post(self.url, {**VALID, "username": "JUAN", "email": "Juan@Example.com"})
        self.assertContains(resp, "This username is already taken.")
        self.assertContains(resp, "An account with this email already exists.")
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_email_and_required_fields(self):
        resp = self.client.post(self.url, {**VALID, "email": "not-an-email", "first_name": ""})
        self.assertContains(resp, "Enter a valid email address.")
        self.assertContains(resp, "This field is required.")
        self.assertFalse(User.objects.exists())

    def test_weak_password_rejected(self):
        resp = self.client.post(self.url, {**VALID, "password1": "12345678", "password2": "12345678"})
        self.assertContains(resp, "too common")
        self.assertFalse(User.objects.exists())

    def test_invalid_contact_number(self):
        resp = self.client.post(self.url, {**VALID, "contact_number": "12345"})
        self.assertContains(resp, "Enter a valid mobile number")

    def test_role_cannot_be_chosen_at_registration(self):
        self.client.post(self.url, {**VALID, "role": "ADMIN"})
        self.assertEqual(User.objects.get(username="juan").role, User.Role.RIDER)


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("rider", "rider@example.com", "Rider-Pass-123")

    def test_login_success_redirects_to_role_dashboard_and_logs_activity(self):
        resp = self.client.post(reverse("accounts:login"), {"username": "rider", "password": "Rider-Pass-123"}, follow=True)
        self.assertRedirects(resp, reverse("dashboards:rider_dashboard"))
        self.assertEqual(LoginActivity.objects.filter(user=self.user).count(), 1)

    def test_login_invalid_credentials(self):
        resp = self.client.post(reverse("accounts:login"), {"username": "rider", "password": "wrong"})
        self.assertContains(resp, "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        resp = self.client.post(reverse("accounts:login"), {"username": "rider", "password": "Rider-Pass-123"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(resp.status_code, 200)

    def test_logout_ends_session(self):
        self.client.login(username="rider", password="Rider-Pass-123")
        resp = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(resp, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        # Protected pages are no longer reachable
        resp = self.client.get(reverse("dashboards:rider_dashboard"))
        self.assertRedirects(resp, reverse("accounts:login") + "?next=" + reverse("dashboards:rider_dashboard"))

    def test_logout_requires_post(self):
        self.client.login(username="rider", password="Rider-Pass-123")
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)

    def test_logged_in_user_skips_login_and_register(self):
        self.client.login(username="rider", password="Rider-Pass-123")
        self.assertRedirects(self.client.get(reverse("accounts:register")), reverse("dashboards:home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 302)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("rider", "rider@example.com", "Rider-Pass-123", first_name="R", last_name="One")
        self.other = User.objects.create_user("other", "other@example.com", "Other-Pass-123")
        self.client.login(username="rider", password="Rider-Pass-123")

    def data(self, **extra):
        return {"first_name": "Rider", "last_name": "One", "username": "rider", "email": "rider@example.com",
                "contact_number": "09171234567", "speed_limit": 70, **extra}

    def test_profile_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)

    def test_view_and_update_own_profile(self):
        self.assertContains(self.client.get(reverse("accounts:profile")), "rider@example.com")
        resp = self.client.post(reverse("accounts:profile"), self.data(), follow=True)
        self.assertContains(resp, "Your profile has been updated.")
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.contact_number, self.user.speed_limit), ("Rider", "09171234567", 70))

    def test_cannot_take_another_users_email_or_username(self):
        resp = self.client.post(reverse("accounts:profile"), self.data(username="other", email="OTHER@example.com"))
        self.assertContains(resp, "This username is already taken.")
        self.assertContains(resp, "An account with this email already exists.")

    def test_cannot_escalate_role_via_profile(self):
        self.client.post(reverse("accounts:profile"), self.data(role="ADMIN"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.RIDER)

    def test_speed_limit_range_validated(self):
        resp = self.client.post(reverse("accounts:profile"), self.data(speed_limit=500))
        self.assertContains(resp, "less than or equal to 200")

    def test_change_password(self):
        resp = self.client.post(reverse("accounts:change_password"), {
            "old_password": "Rider-Pass-123", "new_password1": "Brand-New-Pass-9", "new_password2": "Brand-New-Pass-9"})
        self.assertRedirects(resp, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-New-Pass-9"))
