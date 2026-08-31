"""Django admin registration for the ride models."""
from django.contrib import admin

from .models import Ride, RideEvent, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id_user", "email", "role", "first_name", "last_name")
    list_filter = ("role",)
    search_fields = ("email", "first_name", "last_name")


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = ("id_ride", "status", "id_rider", "id_driver", "pickup_time")
    list_filter = ("status",)


@admin.register(RideEvent)
class RideEventAdmin(admin.ModelAdmin):
    list_display = ("id_ride_event", "id_ride", "description", "created_at")
    list_filter = ("description",)
