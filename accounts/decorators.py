from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """
    Allow a view only for logged-in users whose role is in `roles`.

    - Not logged in      -> redirected to the login page (via @login_required)
    - Logged in, wrong role -> 403 Forbidden

    Because this runs on the server, typing another role's URL by hand
    does not work, even if the link is hidden in the navigation.

    Usage:
        @role_required(User.Role.ADMIN)
        def admin_dashboard(request): ...
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied("You do not have permission to view this page.")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
