from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import LoginActivity


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    """Django sends `user_logged_in` after every successful login; we store it for the dashboards."""
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""
    LoginActivity.objects.create(user=user, user_agent=user_agent)
