import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import SpeedAlert, Trip, haversine_km


def reading(seconds, speed, lat=10.3300, lon=123.9050, start=None):
    t = (start or timezone.now()) + timedelta(seconds=seconds)
    return {"recorded_at": t.isoformat(), "latitude": lat, "longitude": lon, "speed_kmh": speed, "accuracy_m": 5}


class TripTestCase(TestCase):
    def setUp(self):
        self.rider = User.objects.create_user("rider", "rider@example.com", "Rider-Pass-123", speed_limit=60)
        self.other = User.objects.create_user("other", "other@example.com", "Other-Pass-123")
        self.admin = User.objects.create_user("boss", "boss@example.com", "Admin-Pass-123", role=User.Role.ADMIN)
        self.client.force_login(self.rider)

    def make_trip(self, rider=None, **kw):
        rider = rider or self.rider
        return Trip.objects.create(rider=rider, title="Test ride", speed_limit=rider.speed_limit,
                                   started_at=timezone.now() - timedelta(minutes=5), **kw)

    def post_readings(self, trip, readings):
        return self.client.post(reverse("trips:readings", args=[trip.pk]),
                                data=json.dumps({"readings": readings}), content_type="application/json")


class StartTripTests(TripTestCase):
    def test_start_trip_copies_speed_limit_and_redirects_to_tracking(self):
        resp = self.client.post(reverse("trips:start"), {"title": "Morning ride", "source": "GPS"})
        trip = Trip.objects.get()
        self.assertRedirects(resp, reverse("trips:track", args=[trip.pk]))
        self.assertEqual((trip.rider, trip.speed_limit, trip.status), (self.rider, 60, Trip.Status.ACTIVE))

    def test_title_validation(self):
        resp = self.client.post(reverse("trips:start"), {"title": "ab", "source": "GPS"})
        self.assertContains(resp, "at least 3 characters")
        resp = self.client.post(reverse("trips:start"), {"title": "", "source": "BOGUS"})
        self.assertContains(resp, "This field is required.")
        self.assertContains(resp, "Select a valid choice.")
        self.assertFalse(Trip.objects.exists())

    def test_only_one_active_trip(self):
        active = self.make_trip()
        resp = self.client.post(reverse("trips:start"), {"title": "Second ride", "source": "GPS"})
        self.assertContains(resp, "already have a trip in progress")
        self.assertEqual(Trip.objects.count(), 1)
        # Opening the start page while a trip is active goes back to that trip
        self.assertRedirects(self.client.get(reverse("trips:start")), reverse("trips:track", args=[active.pk]))

    def test_guests_and_admins_cannot_start_trips(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("trips:start")), f"{reverse('accounts:login')}?next={reverse('trips:start')}")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("trips:start")).status_code, 403)


class RecordReadingsTests(TripTestCase):
    def test_readings_saved_and_alert_created_over_limit(self):
        trip = self.make_trip()
        start = timezone.now() - timedelta(seconds=30)
        resp = self.post_readings(trip, [reading(0, 40, start=start), reading(1, 65, lat=10.3302, start=start)])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["saved"], 2)
        self.assertEqual(len(data["new_alerts"]), 1)
        self.assertEqual(trip.readings.count(), 2)
        alert = SpeedAlert.objects.get()
        self.assertEqual((alert.speed_kmh, alert.speed_limit), (65, 60))
        self.assertEqual(data["stats"]["max_speed_kmh"], 65)

    def test_alert_cooldown(self):
        trip = self.make_trip()
        start = timezone.now() - timedelta(seconds=60)
        # Over the limit at 0s, 5s (within 10s cooldown) and 12s -> 2 alerts
        self.post_readings(trip, [reading(0, 70, start=start), reading(5, 72, start=start), reading(12, 75, start=start)])
        self.assertEqual(trip.alerts.count(), 2)

    def test_invalid_readings_rejected(self):
        trip = self.make_trip()
        bad = [
            reading(0, 400),                                   # speed out of range
            {**reading(0, 30), "latitude": 95},                # latitude out of range
            reading(-3600, 30, start=trip.started_at),         # before trip started
            reading(600, 30),                                  # in the future
            {"latitude": 10},                                  # missing fields
        ]
        for item in bad:
            resp = self.post_readings(trip, [item])
            self.assertEqual(resp.status_code, 400, item)
        self.assertEqual(self.client.post(reverse("trips:readings", args=[trip.pk]), "not json", content_type="application/json").status_code, 400)
        self.assertEqual(trip.readings.count(), 0)

    def test_cannot_post_to_someone_elses_or_ended_trip(self):
        other_trip = self.make_trip(rider=self.other)
        self.assertEqual(self.post_readings(other_trip, [reading(0, 30)]).status_code, 404)
        done = self.make_trip(status=Trip.Status.COMPLETED)
        self.assertEqual(self.post_readings(done, [reading(0, 30)]).status_code, 409)

    def test_csrf_is_enforced(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.rider)
        trip = self.make_trip()
        resp = client.post(reverse("trips:readings", args=[trip.pk]), json.dumps({"readings": [reading(0, 30)]}),
                           content_type="application/json")
        self.assertEqual(resp.status_code, 403)


class EndTripTests(TripTestCase):
    def test_end_trip_calculates_summary(self):
        trip = self.make_trip()
        start = timezone.now() - timedelta(minutes=2)
        # Two points ~1.11 km apart, 60 s apart -> ~66.7 km/h average
        self.post_readings(trip, [reading(0, 50, 10.3300, 123.9050, start), reading(60, 70, 10.3400, 123.9050, start)])
        resp = self.client.post(reverse("trips:end", args=[trip.pk]))
        self.assertEqual(resp.status_code, 302)
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.Status.COMPLETED)
        self.assertAlmostEqual(float(trip.distance_km), haversine_km(10.33, 123.905, 10.34, 123.905), places=2)
        self.assertAlmostEqual(float(trip.avg_speed_kmh), 66.7, delta=0.2)
        self.assertEqual(float(trip.max_speed_kmh), 70.0)
        self.assertIsNotNone(trip.ended_at)

    def test_cannot_end_trip_without_readings(self):
        trip = self.make_trip()
        resp = self.client.post(reverse("trips:end", args=[trip.pk]), follow=True)
        self.assertContains(resp, "No GPS readings were recorded yet")
        trip.refresh_from_db()
        self.assertTrue(trip.is_active)

    def test_end_requires_post_and_ownership(self):
        trip = self.make_trip(rider=self.other)
        self.assertEqual(self.client.post(reverse("trips:end", args=[trip.pk])).status_code, 404)
        own = self.make_trip()
        self.assertEqual(self.client.get(reverse("trips:end", args=[own.pk])).status_code, 405)

    def test_haversine(self):
        # 1 degree of latitude is ~111.19 km
        self.assertAlmostEqual(haversine_km(0, 0, 1, 0), 111.19, places=1)
