from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LoginActivity, User


@admin.register(User)
class VigilUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Vigil", {"fields": ("role", "contact_number", "profile_photo", "speed_limit")}),
    )


@admin.register(LoginActivity)
class LoginActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp", "user_agent")
    list_filter = ("timestamp",)
    search_fields = ("user__username",)
