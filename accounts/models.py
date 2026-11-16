from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

# Philippine-style mobile numbers: 09XXXXXXXXX or +639XXXXXXXXX
contact_number_validator = RegexValidator(
    regex=r"^(09\d{9}|\+639\d{9})$",
    message="Enter a valid mobile number, e.g. 09171234567 or +639171234567.",
)


class User(AbstractUser):
    """
    Vigil's user account.

    Extends Django's built-in AbstractUser, so we keep everything Django
    already provides (username, password hashing, first/last name, email,
    is_active, last_login, ...) and add the fields our project needs.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        RIDER = "RIDER", "Rider"

    # Every user has exactly one role. New sign-ups are Riders;
    # only an Administrator can promote someone to Administrator.
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.RIDER)

    # Emails must be unique so two accounts can't share one address.
    email = models.EmailField("email address", unique=True)

    contact_number = models.CharField(max_length=13, blank=True, validators=[contact_number_validator])
    profile_photo = models.ImageField(upload_to="profile_photos/", blank=True)

    # Vigil's rider-defined speed alert threshold (km/h), 60 by default.
    speed_limit = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(10), MaxValueValidator(200)]
    )

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_rider(self):
        return self.role == self.Role.RIDER

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def initials(self):
        parts = [self.first_name[:1], self.last_name[:1]]
        return ("".join(parts) or self.username[:2]).upper()

    def profile_completion(self):
        """Return (percent, checklist) describing how complete the profile is."""
        checklist = [
            ("Full name", bool(self.first_name and self.last_name)),
            ("Email address", bool(self.email)),
            ("Contact number", bool(self.contact_number)),
            ("Profile photo", bool(self.profile_photo)),
        ]
        done = sum(1 for _, ok in checklist if ok)
        return round(done * 100 / len(checklist)), checklist

    def save(self, *args, **kwargs):
        # Superusers created with `createsuperuser` are always Administrators.
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class LoginActivity(models.Model):
    """One row per successful sign-in. Powers the dashboard activity charts."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_activity")
    timestamp = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "login activity"

    def __str__(self):
        return f"{self.user} @ {self.timestamp:%Y-%m-%d %H:%M}"

    @property
    def device(self):
        """A short, human-friendly guess at the browser/OS from the user agent."""
        ua = self.user_agent.lower()
        os_name = next((n for k, n in [("android", "Android"), ("iphone", "iPhone"), ("windows", "Windows"),
                                        ("mac os", "macOS"), ("linux", "Linux")] if k in ua), "Unknown OS")
        browser = next((n for k, n in [("edg", "Edge"), ("opr", "Opera"), ("firefox", "Firefox"),
                                        ("chrome", "Chrome"), ("safari", "Safari")] if k in ua), "Browser")
        return f"{browser} on {os_name}"
