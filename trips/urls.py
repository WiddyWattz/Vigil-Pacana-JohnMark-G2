from django.urls import path

from . import views

app_name = "trips"

urlpatterns = [
    path("start/", views.start_trip, name="start"),
    path("<int:pk>/track/", views.track_trip, name="track"),
    path("<int:pk>/readings/", views.record_readings, name="readings"),
    path("<int:pk>/end/", views.end_trip, name="end"),
]
