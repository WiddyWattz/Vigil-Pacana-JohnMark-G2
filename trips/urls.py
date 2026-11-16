from django.urls import path

from . import views

app_name = "trips"

urlpatterns = [
    # Trip history (list / detail / edit / delete)
    path("", views.trip_list, name="list"),
    path("<int:pk>/", views.trip_detail, name="detail"),
    path("<int:pk>/edit/", views.trip_edit, name="edit"),
    path("<int:pk>/delete/", views.trip_delete, name="delete"),
    # Live tracking
    path("start/", views.start_trip, name="start"),
    path("<int:pk>/track/", views.track_trip, name="track"),
    path("<int:pk>/readings/", views.record_readings, name="readings"),
    path("<int:pk>/end/", views.end_trip, name="end"),
]
