import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import role_required
from accounts.models import User

from .forms import ReadingForm, StartTripForm, TripEditForm
from .models import SpeedAlert, SpeedReading, Trip, haversine_km

MAX_READINGS_PER_REQUEST = 60


def _own_trip(request, pk, **filters):
    """
    Fetch a trip that belongs to the logged-in rider.
    Someone else's trip gives 404, so riders can't even tell it exists.
    """
    return get_object_or_404(Trip, pk=pk, rider=request.user, **filters)


def _viewable_trip(request, pk):
    """Administrators may open any trip; riders only their own (others give 404)."""
    if request.user.is_admin_role:
        return get_object_or_404(Trip.objects.select_related("rider"), pk=pk)
    return _own_trip(request, pk)


@role_required(User.Role.RIDER)
@require_http_methods(["GET", "POST"])
def start_trip(request):
    active = Trip.objects.filter(rider=request.user, status=Trip.Status.ACTIVE).first()
    if active and request.method == "GET":
        messages.info(request, "You already have a trip in progress.")
        return redirect("trips:track", pk=active.pk)

    form = StartTripForm(request.POST or None, rider=request.user)
    if request.method == "POST":
        if form.is_valid():
            try:
                trip = form.save()
            except IntegrityError:  # two "start" clicks at the same moment
                messages.error(request, "You already have a trip in progress.")
                return redirect("trips:start")
            messages.success(request, f"Trip started. Alerts will sound above {trip.speed_limit} km/h.")
            return redirect("trips:track", pk=trip.pk)
        messages.error(request, "Please correct the errors below.")
    return render(request, "trips/start_trip.html", {"form": form, "active": "start_trip"})


@role_required(User.Role.RIDER)
def track_trip(request, pk):
    trip = _own_trip(request, pk)
    if not trip.is_active:
        messages.info(request, "That trip has already ended.")
        return redirect("trips:detail", pk=trip.pk)
    stats = _live_stats(trip)
    return render(request, "trips/track_trip.html", {"trip": trip, "stats": stats, "active": "start_trip"})


@role_required(User.Role.RIDER)
@require_POST
def record_readings(request, pk):
    """
    JSON endpoint the tracking page calls every few seconds:
        POST {"readings": [{"recorded_at", "latitude", "longitude", "speed_kmh", "accuracy_m"}, ...]}
    Every reading is validated with ReadingForm. Speed alerts are decided
    HERE, on the server, by comparing each speed with the trip's limit.
    """
    trip = _own_trip(request, pk)
    if not trip.is_active:
        return JsonResponse({"error": "This trip has already ended."}, status=409)

    try:
        payload = json.loads(request.body)
        items = payload["readings"]
        assert isinstance(items, list)
    except (ValueError, KeyError, AssertionError):
        return JsonResponse({"error": "Expected JSON: {\"readings\": [...]}"}, status=400)
    if not 1 <= len(items) <= MAX_READINGS_PER_REQUEST:
        return JsonResponse({"error": f"Send between 1 and {MAX_READINGS_PER_REQUEST} readings."}, status=400)

    forms = [ReadingForm(item if isinstance(item, dict) else {}, trip=trip) for item in items]
    errors = {i: f.errors.get_json_data() for i, f in enumerate(forms) if not f.is_valid()}
    if errors:
        return JsonResponse({"error": "Invalid reading data.", "details": errors}, status=400)

    new_alerts = []
    with transaction.atomic():
        last_alert_at = trip.alerts.aggregate(t=Max("triggered_at"))["t"]
        for form in sorted(forms, key=lambda f: f.cleaned_data["recorded_at"]):
            reading = form.save(commit=False)
            reading.trip = trip
            reading.save()
            over_limit = reading.speed_kmh > trip.speed_limit
            cooled_down = last_alert_at is None or (
                (reading.recorded_at - last_alert_at).total_seconds() >= SpeedAlert.COOLDOWN_SECONDS
            )
            if over_limit and cooled_down:
                alert = SpeedAlert.objects.create(
                    trip=trip, reading=reading, triggered_at=reading.recorded_at,
                    speed_kmh=reading.speed_kmh, speed_limit=trip.speed_limit,
                )
                last_alert_at = alert.triggered_at
                new_alerts.append({"speed_kmh": round(alert.speed_kmh), "at": alert.triggered_at.isoformat()})

    return JsonResponse({"saved": len(forms), "new_alerts": new_alerts, "stats": _live_stats(trip)})


@role_required(User.Role.RIDER)
@require_POST
def end_trip(request, pk):
    trip = _own_trip(request, pk, status=Trip.Status.ACTIVE)
    if not trip.readings.exists():
        messages.error(request, "No GPS readings were recorded yet. Ride for a moment, or delete this trip.")
        return redirect("trips:track", pk=trip.pk)
    trip.finish()
    messages.success(request, f"Trip saved: {trip.distance_km} km, top speed {trip.max_speed_kmh} km/h.")
    return redirect("trips:detail", pk=trip.pk)


def _live_stats(trip):
    """Running totals shown on the tracking page while the trip is in progress."""
    points = list(trip.readings.order_by("recorded_at").values_list("latitude", "longitude", "speed_kmh"))
    distance = sum(haversine_km(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))
    return {
        "readings": len(points),
        "distance_km": round(distance, 2),
        "max_speed_kmh": round(max((p[2] for p in points), default=0)),
        "current_speed_kmh": round(points[-1][2]) if points else 0,
        "alerts": trip.alerts.count(),
    }


# ---------------------------------------------------------------------------
# Trip history: list (Read), detail (Read), edit (Update), delete (Delete)
# ---------------------------------------------------------------------------

@login_required
def trip_list(request):
    """
    Riders see only their own trips. Administrators see every rider's trips
    and can filter by rider. Both can search by name and filter by status.
    """
    is_admin = request.user.is_admin_role
    trips = Trip.objects.select_related("rider")
    if not is_admin:
        trips = trips.filter(rider=request.user)

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    rider_id = request.GET.get("rider", "")
    if q:
        trips = trips.filter(Q(title__icontains=q) | Q(notes__icontains=q))
    if status in Trip.Status.values:
        trips = trips.filter(status=status)
    if is_admin and rider_id.isdigit():
        trips = trips.filter(rider_id=int(rider_id))

    # Totals are calculated separately from the alert count: joining alerts
    # here would repeat each trip once per alert and inflate the distance sum.
    completed = trips.filter(status=Trip.Status.COMPLETED)
    totals = completed.aggregate(count=Count("id"), distance=Sum("distance_km"), top=Max("max_speed_kmh"))
    totals["alerts"] = SpeedAlert.objects.filter(trip__in=completed).count()
    trips = trips.annotate(alert_count=Count("alerts"))
    return render(request, "trips/trip_list.html", {
        "active": "trips",
        "page": Paginator(trips, 10).get_page(request.GET.get("page")),
        "totals": totals,
        "q": q, "status": status, "rider_id": rider_id,
        "statuses": Trip.Status.choices,
        "riders": User.objects.filter(role=User.Role.RIDER).order_by("username") if is_admin else None,
    })


@login_required
def trip_detail(request, pk):
    trip = _viewable_trip(request, pk)
    readings = list(trip.readings.values_list("latitude", "longitude", "speed_kmh"))
    return render(request, "trips/trip_detail.html", {
        "active": "trips",
        "trip": trip,
        "alerts": trip.alerts.all(),
        "reading_count": len(readings),
        "speed_chart": _speed_chart(readings, trip.speed_limit),
        "route": _route_shape(readings),
        "can_edit": trip.rider_id == request.user.id,
    })


@login_required
@require_http_methods(["GET", "POST"])
def trip_edit(request, pk):
    """Only the rider who recorded the trip may rename it or edit its notes."""
    trip = _own_trip(request, pk)
    form = TripEditForm(request.POST or None, instance=trip)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Trip details updated.")
            return redirect("trips:detail", pk=trip.pk)
        messages.error(request, "Please correct the errors below.")
    return render(request, "trips/trip_edit.html", {"form": form, "trip": trip, "active": "trips"})


@login_required
@require_http_methods(["GET", "POST"])
def trip_delete(request, pk):
    """
    The owner can delete (or discard an in-progress) trip; an Administrator
    can delete any trip. Readings and alerts are removed with it (CASCADE).
    """
    trip = _viewable_trip(request, pk)
    if request.method == "POST":
        title, owner = trip.title, trip.rider
        trip.delete()
        who = "" if owner == request.user else f" (recorded by {owner.username})"
        messages.success(request, f'Trip "{title}"{who} was deleted.')
        return redirect("trips:list")
    return render(request, "trips/trip_confirm_delete.html", {
        "trip": trip, "active": "trips",
        "reading_count": trip.readings.count(), "alert_count": trip.alerts.count(),
    })


CHART_W, CHART_H, MAX_POINTS = 600, 160, 150


def _downsample(points):
    step = max(1, len(points) // MAX_POINTS)
    return points[::step] + ([points[-1]] if len(points) % step else [])


def _speed_chart(readings, limit):
    """SVG polyline points for the speed-over-time chart, plus the y position of the limit line."""
    if len(readings) < 2:
        return None
    speeds = [r[2] for r in _downsample(readings)]
    top = max(max(speeds), limit) * 1.15
    step = CHART_W / (len(speeds) - 1)
    y = lambda v: round(CHART_H - v / top * CHART_H, 1)
    pts = " ".join(f"{round(i * step, 1)},{y(v)}" for i, v in enumerate(speeds))
    return {"points": pts, "area": f"0,{CHART_H} {pts} {CHART_W},{CHART_H}", "limit_y": y(limit),
            "top": round(top), "w": CHART_W, "h": CHART_H}


def _route_shape(readings):
    """Scale the GPS points into a 300x200 box to draw the route outline (no map service needed)."""
    if len(readings) < 2:
        return None
    pts = _downsample(readings)
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(lats) - min(lats), max(lons) - min(lons)) or 1e-6
    scale = 180 / span
    coords = [(round(10 + (lon - min(lons)) * scale, 1), round(190 - (lat - min(lats)) * scale, 1)) for lat, lon, _ in pts]
    return {"points": " ".join(f"{x},{y}" for x, y in coords), "start": coords[0], "end": coords[-1]}
