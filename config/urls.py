"""URL configuration for the ride management API."""
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from rides.views import RideEventViewSet, RideViewSet, UserViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"rides", RideViewSet, basename="ride")
router.register(r"ride-events", RideEventViewSet, basename="rideevent")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    # Login/logout for the browsable API.
    path("api-auth/", include("rest_framework.urls")),
]
