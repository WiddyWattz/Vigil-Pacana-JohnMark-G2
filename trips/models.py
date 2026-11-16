"""
Trip tracking models (Vigil's core feature).

    User 1 ──< Trip 1 ──< SpeedReading     (one GPS sample: position + speed)
                    1 ──< SpeedAlert       (rider went over their speed limit)

A Trip belongs to the rider who recorded it. Its summary numbers
(distance, duration, average/max speed) are calculated on the server from
the saved SpeedReadings when the trip ends, so they can't be faked by the browser.
"""

import math

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance in km between two GPS points (great-circle formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class Trip(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "In progress"
        COMPLETED = "COMPLETED", "Completed"

    class Source(models.TextChoices):
        GPS = "GPS", "Device GPS"
        SIMULATED = "SIMULATED", "Demo (simulated GPS)"

    rider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trips")
    title = models.CharField(max_length=80)
    notes = models.TextField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.GPS)

    # Copied from the rider's profile when the trip starts, so later profile
    # changes don't rewrite the history of old trips.
    speed_limit = models.PositiveSmallIntegerField(validators=[MinValueValidator(10), MaxValueValidator(200)])

    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Summary, filled in by finish()
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    avg_speed_kmh = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    max_speed_kmh = models.DecimalField(max_digits=5, decimal_places=1, default=0)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            # Business rule: a rider can only have ONE trip in progress at a time.
            models.UniqueConstraint(fields=["rider"], condition=Q(status="ACTIVE"), name="one_active_trip_per_rider"),
        ]

    def __str__(self):
        return f"{self.title} ({self.rider})"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def duration_display(self):
        seconds = self.duration_seconds if not self.is_active else int((timezone.now() - self.started_at).total_seconds())
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"

    def finish(self):
        """End the trip and calculate its summary from the saved readings."""
        readings = list(self.readings.order_by("recorded_at").values_list("latitude", "longitude", "speed_kmh", "recorded_at"))
        distance = sum(
            haversine_km(a[0], a[1], b[0], b[1]) for a, b in zip(readings, readings[1:])
        )
        self.ended_at = timezone.now()
        self.duration_seconds = int((self.ended_at - self.started_at).total_seconds())
        self.distance_km = round(distance, 2)
        speeds = [r[2] for r in readings]
        self.max_speed_kmh = round(max(speeds), 1) if speeds else 0
        # Average moving speed = distance / time between first and last reading
        moving_hours = (readings[-1][3] - readings[0][3]).total_seconds() / 3600 if len(readings) > 1 else 0
        self.avg_speed_kmh = round(distance / moving_hours, 1) if moving_hours > 0 else 0
        self.status = self.Status.COMPLETED
        self.save()


class SpeedReading(models.Model):
    """One GPS sample sent by the rider's browser while a trip is active."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="readings")
    recorded_at = models.DateTimeField()
    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    speed_kmh = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(300)])
    accuracy_m = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["recorded_at"]

    def __str__(self):
        return f"{self.speed_kmh:.0f} km/h @ {self.recorded_at:%H:%M:%S}"


class SpeedAlert(models.Model):
    """Saved every time the rider goes over their speed limit (at most one per cooldown period)."""

    COOLDOWN_SECONDS = 10

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="alerts")
    reading = models.OneToOneField(SpeedReading, on_delete=models.CASCADE, related_name="alert")
    triggered_at = models.DateTimeField()
    speed_kmh = models.FloatField()
    speed_limit = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["triggered_at"]

    @property
    def over_by(self):
        return round(self.speed_kmh - self.speed_limit, 1)

    def __str__(self):
        return f"{self.speed_kmh:.0f} km/h (limit {self.speed_limit})"
