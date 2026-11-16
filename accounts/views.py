from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, ProfileForm, RegistrationForm, StyledPasswordChangeForm


@require_http_methods(["GET", "POST"])
def register(request):
    """Create a new Rider account, then send the user to the login page."""
    if request.user.is_authenticated:
        return redirect("dashboards:home")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Account created for {user.username}. You can now log in.")
            return redirect("accounts:login")
        messages.error(request, "Please correct the errors below.")
    return render(request, "accounts/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    """
    Uses Django's built-in LoginView (authenticate + login + session).
    After login, LOGIN_REDIRECT_URL sends the user to dashboards:home,
    which picks the dashboard for their role.
    """

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, f"Welcome back, {form.get_user().display_name}!")
        return super().form_valid(form)


class LogoutView(auth_views.LogoutView):
    """Built-in LogoutView: only accepts POST and flushes the whole session."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You have been logged out.")
        return response


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    """
    View and edit the logged-in user's own profile.

    There is no user id in the URL: the form is always bound to
    request.user, so a user can never open or edit someone else's profile.
    """
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile")
        messages.error(request, "Please correct the errors below.")
        request.user.refresh_from_db()  # don't show half-applied invalid values in the sidebar/header
    else:
        form = ProfileForm(instance=request.user)

    percent, checklist = request.user.profile_completion()
    return render(request, "accounts/profile.html", {
        "form": form,
        "completion": percent,
        "checklist": checklist,
        "active": "profile",
    })


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keep the user logged in after the change
            messages.success(request, "Your password has been changed.")
            return redirect("accounts:profile")
        messages.error(request, "Please correct the errors below.")
    return render(request, "accounts/change_password.html", {"form": form, "active": "password"})
