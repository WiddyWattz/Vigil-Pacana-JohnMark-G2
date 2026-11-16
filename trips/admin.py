from django.contrib import admin

from .models import SpeedAlert, SpeedReading, Trip


class SpeedAlertInline(admin.TabularInline):
    model = SpeedAlert
    extra = 0
    readonly_fields = ("triggered_at", "speed_kmh", "speed_limit", "reading")


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("title", "rider", "status", "source", "started_at", "distance_km", "max_speed_kmh")
    list_filter = ("status", "source")
    search_fields = ("title", "rider__username")
    inlines = [SpeedAlertInline]


@admin.register(SpeedReading)
class SpeedReadingAdmin(admin.ModelAdmin):
    list_display = ("trip", "recorded_at", "speed_kmh", "latitude", "longitude")
    list_filter = ("trip__rider",)
