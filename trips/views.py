import json

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import role_required
from accounts.models import User

from .forms import ReadingForm, StartTripForm
from .models import SpeedAlert, SpeedReading, Trip, haversine_km

MAX_READINGS_PER_REQUEST = 60


def _own_trip(request, pk, **filters):
    """
    Fetch a trip that belongs to the logged-in rider.
    Someone else's trip gives 404, so riders can't even tell it exists.
    """
    return get_object_or_404(Trip, pk=pk, rider=request.user, **filters)


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
        return redirect("dashboards:home")
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
    return redirect("dashboards:home")


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
