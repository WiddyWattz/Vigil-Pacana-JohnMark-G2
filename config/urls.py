from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("django-admin/", admin.site.urls),  # Django's built-in admin site
]
