from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import SpeedReading, Trip


class StartTripForm(forms.ModelForm):
    """Shown before a ride. The speed limit is copied from the rider's profile, not typed here."""

    class Meta:
        model = Trip
        fields = ["title", "source"]
        labels = {"title": "Trip name", "source": "Location source"}
        widgets = {"source": forms.RadioSelect}

    def __init__(self, *args, rider, **kwargs):
        self.rider = rider
        super().__init__(*args, **kwargs)
        self.fields["title"].initial = f"Ride on {timezone.localtime():%b %d, %Y}"

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 3:
            raise forms.ValidationError("Trip name must be at least 3 characters.")
        return title

    def clean(self):
        cleaned = super().clean()
        # Business rule: only one trip in progress per rider (also enforced by a DB constraint).
        if Trip.objects.filter(rider=self.rider, status=Trip.Status.ACTIVE).exists():
            raise forms.ValidationError("You already have a trip in progress. End it before starting a new one.")
        return cleaned

    def save(self, commit=True):
        trip = super().save(commit=False)
        trip.rider = self.rider
        trip.speed_limit = self.rider.speed_limit
        if commit:
            trip.save()
        return trip


class ReadingForm(forms.ModelForm):
    """
    Validates ONE GPS reading sent by the browser as JSON.
    Using a Django form means the same server-side validation rules apply
    as for normal HTML forms (ranges come from the model validators).
    """

    class Meta:
        model = SpeedReading
        fields = ["recorded_at", "latitude", "longitude", "speed_kmh", "accuracy_m"]

    def __init__(self, *args, trip, **kwargs):
        self.trip = trip
        super().__init__(*args, **kwargs)

    def clean_recorded_at(self):
        recorded_at = self.cleaned_data["recorded_at"]
        if recorded_at < self.trip.started_at - timedelta(seconds=5):
            raise forms.ValidationError("Reading is from before the trip started.")
        if recorded_at > timezone.now() + timedelta(minutes=1):
            raise forms.ValidationError("Reading time is in the future.")
        return recorded_at

    def clean_accuracy_m(self):
        accuracy = self.cleaned_data.get("accuracy_m")
        if accuracy is not None and accuracy < 0:
            raise forms.ValidationError("Accuracy cannot be negative.")
        return accuracy
