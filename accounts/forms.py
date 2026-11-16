"""
Forms for the account feature.

All validation here runs on the server, so it still applies even if
someone bypasses the HTML `required` attributes in the browser.
"""

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import User

MAX_PHOTO_BYTES = 2 * 1024 * 1024  # 2 MB


def _clean_unique(form, field, message):
    """Case-insensitive uniqueness check that ignores the user being edited."""
    value = form.cleaned_data.get(field, "").strip()
    qs = User.objects.filter(**{f"{field}__iexact": value})
    if form.instance.pk:
        qs = qs.exclude(pk=form.instance.pk)
    if qs.exists():
        raise forms.ValidationError(message)
    return value


class RegistrationForm(forms.ModelForm):
    """Sign-up form. New accounts always get the Rider role (set in the model default)."""

    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", strip=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "contact_number"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make the name and email fields required (they are optional on AbstractUser).
        for name in ("first_name", "last_name", "email"):
            self.fields[name].required = True

    def clean_username(self):
        return _clean_unique(self, "username", "This username is already taken.")

    def clean_email(self):
        return _clean_unique(self, "email", "An account with this email already exists.").lower()

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        elif p1:
            # Run Django's password validators (length, common passwords, ...).
            try:
                password_validation.validate_password(p1, self.instance)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        # set_password() hashes the password; the plain text is never stored.
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Django's built-in login form with a clearer error message."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Invalid username or password. Please try again.",
    }


class ProfileForm(forms.ModelForm):
    """Lets a user edit their own profile. Role is deliberately NOT editable here."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "contact_number", "speed_limit", "profile_photo"]
        labels = {"speed_limit": "Speed limit (km/h)"}
        widgets = {"profile_photo": forms.FileInput(attrs={"accept": "image/*"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("first_name", "last_name", "email"):
            self.fields[name].required = True

    def clean_username(self):
        return _clean_unique(self, "username", "This username is already taken.")

    def clean_email(self):
        return _clean_unique(self, "email", "An account with this email already exists.").lower()

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if photo and hasattr(photo, "size") and photo.size > MAX_PHOTO_BYTES:
            raise forms.ValidationError("Profile photo must be 2 MB or smaller.")
        return photo


class StyledPasswordChangeForm(PasswordChangeForm):
    """Django's password change form (checks the old password, validates and hashes the new one)."""
