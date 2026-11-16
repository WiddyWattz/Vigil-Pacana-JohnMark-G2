from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.home, name="home"),
    path("rider/", views.rider_dashboard, name="rider_dashboard"),
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("admin/users/", views.manage_users, name="manage_users"),
    path("admin/users/<int:pk>/update/", views.update_user, name="update_user"),
]
