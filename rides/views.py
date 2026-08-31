"""API viewsets for users, rides, and ride events."""
from datetime import timedelta

from django.db.models import F, FloatField, Prefetch, Value
from django.db.models.functions import ACos, Cos, Least, Greatest, Radians, Sin
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from .filters import RideFilter
from .models import Ride, RideEvent, User
from .pagination import RidePagination
from .permissions import IsAdminRole
from .serializers import (
    RideEventSerializer,
    RideListSerializer,
    RideSerializer,
    UserSerializer,
)

# Mean radius of the Earth in kilometres, used for the great-circle distance.
EARTH_RADIUS_KM = 6371.0088


class UserViewSet(viewsets.ModelViewSet):
    """CRUD for users. Admin-role only."""

    queryset = User.objects.all().order_by("id_user")
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]


class RideEventViewSet(viewsets.ModelViewSet):
    """CRUD for ride events. Admin-role only."""

    queryset = RideEvent.objects.all().order_by("-created_at")
    serializer_class = RideEventSerializer
    permission_classes = [IsAdminRole]


class RideViewSet(viewsets.ModelViewSet):
    """CRUD for rides plus the optimized Ride List API.

    The list endpoint supports:

    * pagination (``page`` / ``page_size``)
    * filtering by ``status`` and ``rider_email``
    * sorting by ``pickup_time`` or by distance to a supplied pickup GPS point
    * an extra ``todays_ride_events`` field limited to the last 24 hours

    Query efficiency: the base queryset uses ``select_related`` for rider and
    driver (a single JOINed query) and two ``Prefetch`` operations for events.
    A list page therefore costs 1 query for the rides (+JOINed users), plus
    2 prefetch queries, plus the pagination COUNT query.
    """

    permission_classes = [IsAdminRole]
    pagination_class = RidePagination
    filterset_class = RideFilter

    # Allowed ordering values -> ORM ordering expression.
    ORDERING_MAP = {
        "pickup_time": "pickup_time",
        "-pickup_time": "-pickup_time",
    }

    def get_serializer_class(self):
        if self.action == "list":
            return RideListSerializer
        return RideSerializer

    def get_queryset(self):
        """Build the queryset shared by list and detail reads.

        ``select_related`` pulls rider + driver in the same SELECT. Two
        ``Prefetch`` calls attach all events and the last-24h events without
        ever loading the full event list per-row in Python.
        """
        cutoff = timezone.now() - timedelta(hours=24)

        todays_events_prefetch = Prefetch(
            "events",
            queryset=RideEvent.objects.filter(created_at__gte=cutoff).order_by(
                "-created_at"
            ),
            to_attr="_todays_events",
        )

        return (
            Ride.objects.select_related("id_rider", "id_driver")
            .prefetch_related("events", todays_events_prefetch)
            .order_by("pickup_time")
        )

    def _apply_ordering(self, queryset):
        """Apply pickup_time or distance ordering based on query params.

        Distance sorting is done entirely in SQL using the haversine formula
        expressed via ORM functions, so ORDER BY + LIMIT/OFFSET run in the
        database and pagination keeps working on very large tables.
        """
        ordering = self.request.query_params.get("ordering")

        if ordering in ("distance", "-distance"):
            lat = self.request.query_params.get("pickup_lat")
            lng = self.request.query_params.get("pickup_lng")
            if lat is None or lng is None:
                raise ValidationError(
                    "Sorting by distance requires 'pickup_lat' and 'pickup_lng' "
                    "query parameters."
                )
            try:
                lat = float(lat)
                lng = float(lng)
            except (TypeError, ValueError):
                raise ValidationError("'pickup_lat' and 'pickup_lng' must be numbers.")

            queryset = self._annotate_distance(queryset, lat, lng)
            direction = "" if ordering == "distance" else "-"
            # Tie-break on the primary key for a stable, paginable order.
            return queryset.order_by(f"{direction}distance_km", "id_ride")

        if ordering in self.ORDERING_MAP:
            return queryset.order_by(self.ORDERING_MAP[ordering], "id_ride")

        if ordering:
            raise ValidationError(
                "Invalid 'ordering'. Allowed values: pickup_time, -pickup_time, "
                "distance, -distance."
            )

        # Default ordering.
        return queryset.order_by("pickup_time", "id_ride")

    @staticmethod
    def _annotate_distance(queryset, lat, lng):
        """Annotate each ride with great-circle distance (km) from (lat, lng).

        Uses the haversine formula composed from database math functions so
        the computation and the ORDER BY happen server-side.
        """
        lat_rad = Radians(Value(lat, output_field=FloatField()))
        lng_rad = Radians(Value(lng, output_field=FloatField()))
        row_lat_rad = Radians(F("pickup_latitude"))
        row_lng_rad = Radians(F("pickup_longitude"))

        # cos(c) = sin(lat1)sin(lat2) + cos(lat1)cos(lat2)cos(lng2 - lng1)
        cos_central_angle = (
            Sin(lat_rad) * Sin(row_lat_rad)
            + Cos(lat_rad) * Cos(row_lat_rad) * Cos(row_lng_rad - lng_rad)
        )
        # Clamp to [-1, 1] to avoid ACos domain errors from float rounding.
        clamped = Least(
            Value(1.0, output_field=FloatField()),
            Greatest(Value(-1.0, output_field=FloatField()), cos_central_angle),
        )
        distance = ACos(clamped) * Value(EARTH_RADIUS_KM, output_field=FloatField())
        return queryset.annotate(distance_km=distance)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self._apply_ordering(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        from rest_framework.response import Response

        return Response(serializer.data)
