from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboards:home", permanent=False)),
    path("accounts/", include("accounts.urls")),
    path("dashboard/", include("dashboards.urls")),
    path("trips/", include("trips.urls")),
    path("django-admin/", admin.site.urls),  # Django's built-in admin site
]

# Serve uploaded profile photos during development.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
