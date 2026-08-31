"""Filter definitions for the Ride List API."""
import django_filters

from .models import Ride


class RideFilter(django_filters.FilterSet):
    """Filter rides by status and by the rider's email.

    ``rider_email`` uses an exact (case-insensitive) match. It joins through
    the related rider without pulling the user rows into Python.
    """

    status = django_filters.CharFilter(field_name="status", lookup_expr="iexact")
    rider_email = django_filters.CharFilter(
        field_name="id_rider__email", lookup_expr="iexact"
    )

    class Meta:
        model = Ride
        fields = ["status", "rider_email"]
