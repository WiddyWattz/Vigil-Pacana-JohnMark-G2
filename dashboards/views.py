from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import LoginActivity, User

CHART_W, CHART_H = 300, 120  # size of the SVG drawing area in the "Weekly activity" card


def _last_7_days():
    today = timezone.localdate()
    return [today - timedelta(days=i) for i in range(6, -1, -1)]


def _daily_counts(queryset, date_field):
    """Count rows per day for the last 7 days -> list of 7 integers (oldest first)."""
    days = _last_7_days()
    rows = (
        queryset.filter(**{f"{date_field}__date__gte": days[0]})
        .annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(n=Count("id"))
    )
    by_day = {r["day"]: r["n"] for r in rows}
    return [by_day.get(d, 0) for d in days]


def _chart(series_list):
    """
    Turn lists of daily counts into SVG polyline points so the template can
    draw the weekly line chart without any JavaScript chart library.
    """
    peak = max([max(s) for s in series_list] + [1])
    step = CHART_W / 6
    lines = []
    for series in series_list:
        pts = [(round(i * step, 1), round(CHART_H - (v / peak) * (CHART_H - 10), 1)) for i, v in enumerate(series)]
        lines.append({
            "points": " ".join(f"{x},{y}" for x, y in pts),
            "area": f"0,{CHART_H} " + " ".join(f"{x},{y}" for x, y in pts) + f" {CHART_W},{CHART_H}",
            "values": series,
            "total": sum(series),
        })
    days = _last_7_days()
    return {
        "lines": lines,
        "labels": [d.strftime("%a")[0] for d in days],
        "today_index": 6,
        "peak": peak,
        "w": CHART_W,
        "h": CHART_H,
    }


def _pct(part, whole):
    return round(part * 100 / whole) if whole else 0


def _ring(percent):
    """Values for an SVG progress ring (circle radius 40)."""
    circumference = 251.33  # 2 * pi * 40
    return {"percent": percent, "dash": round(circumference * percent / 100, 2), "circ": circumference}


@login_required
def home(request):
    """Send each user to the dashboard for their role (used right after login)."""
    if request.user.role == User.Role.ADMIN:
        return redirect("dashboards:admin_dashboard")
    return redirect("dashboards:rider_dashboard")


@role_required(User.Role.RIDER)
def rider_dashboard(request):
    user = request.user
    percent, checklist = user.profile_completion()
    logins = user.login_activity.all()
    return render(request, "dashboards/user_dashboard.html", {
        "active": "dashboard",
        "total_logins": logins.count(),
        "days_member": (timezone.localdate() - timezone.localdate(user.date_joined)).days,
        "logins_this_week": sum(_daily_counts(logins, "timestamp")),
        "chart": _chart([_daily_counts(logins, "timestamp")]),
        "legend": ["Sign-ins"],
        "ring": _ring(percent),
        "checklist": checklist,
        "checklist_done": sum(1 for _, ok in checklist if ok),
        "recent_logins": logins[:2],
    })


@role_required(User.Role.ADMIN)
def admin_dashboard(request):
    users = User.objects.all()
    total = users.count()
    admin_count = users.filter(role=User.Role.ADMIN).count()
    rider_count = total - admin_count
    active_count = users.filter(is_active=True).count()
    active_riders = users.filter(role=User.Role.RIDER, is_active=True).count()
    week_ago = timezone.now() - timedelta(days=7)

    return render(request, "dashboards/admin_dashboard.html", {
        "active": "dashboard",
        "total_users": total,
        "admin_count": admin_count,
        "rider_count": rider_count,
        "active_count": active_count,
        "new_this_week": users.filter(date_joined__gte=week_ago).count(),
        "chart": _chart([_daily_counts(LoginActivity.objects.all(), "timestamp"), _daily_counts(users, "date_joined")]),
        "legend": ["Sign-ins", "New sign-ups"],
        "ring": _ring(_pct(active_riders, rider_count)),
        "active_ring": _ring(_pct(active_count, total)),
        "active_riders": active_riders,
        "inactive_riders": rider_count - active_riders,
        "breakdown": [
            {"title": "Riders", "count": rider_count, "ring": _ring(_pct(rider_count, total)),
             "filter": "?role=RIDER", "note": "Accounts created through registration"},
            {"title": "Administrators", "count": admin_count, "ring": _ring(_pct(admin_count, total)),
             "filter": "?role=ADMIN", "note": "Can manage users and roles"},
            {"title": "Inactive", "count": total - active_count, "ring": _ring(_pct(total - active_count, total)),
             "filter": "", "note": "Deactivated accounts cannot log in"},
        ],
        "recent_users": users.order_by("-date_joined")[:4],
        "recent_logins": LoginActivity.objects.select_related("user")[:2],
    })


@role_required(User.Role.ADMIN)
def manage_users(request):
    """Administrator-only list of all accounts with search and role filter."""
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    users = User.objects.order_by("-date_joined")
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    if role in User.Role.values:
        users = users.filter(role=role)
    page = Paginator(users, 10).get_page(request.GET.get("page"))
    return render(request, "dashboards/manage_users.html", {
        "active": "users",
        "page": page,
        "q": q,
        "role": role,
        "roles": User.Role.choices,
    })


@require_POST
@role_required(User.Role.ADMIN)
def update_user(request, pk):
    """Change another user's role or active status (POST only, CSRF-protected)."""
    target = get_object_or_404(User, pk=pk)
    back = request.POST.get("next", "")
    # Only redirect back to a page on this site (prevents open redirects).
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = "dashboards:manage_users"

    if target == request.user:
        messages.error(request, "You cannot change your own role or status.")
        return redirect(back)

    action = request.POST.get("action")
    if action == "set_role" and request.POST.get("role") in User.Role.values:
        if target.is_superuser:
            messages.error(request, "Superuser accounts are always Administrators.")
            return redirect(back)
        target.role = request.POST["role"]
        target.save(update_fields=["role"])
        messages.success(request, f"{target.username} is now a {target.get_role_display()}.")
    elif action == "toggle_active":
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        messages.success(request, f"{target.username} has been {'activated' if target.is_active else 'deactivated'}.")
    else:
        messages.error(request, "Invalid action.")
    return redirect(back)
