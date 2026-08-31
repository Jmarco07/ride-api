"""Serializers converting the ride domain models to/from JSON."""
from rest_framework import serializers

from .models import Ride, RideEvent, User


class UserSerializer(serializers.ModelSerializer):
    """Full representation of a user, used for CRUD on the User endpoint."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id_user",
            "role",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "password",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class NestedUserSerializer(serializers.ModelSerializer):
    """Lightweight user representation embedded inside a Ride."""

    class Meta:
        model = User
        fields = [
            "id_user",
            "role",
            "first_name",
            "last_name",
            "email",
            "phone_number",
        ]


class RideEventSerializer(serializers.ModelSerializer):
    """Serializer for individual ride events."""

    id_ride = serializers.PrimaryKeyRelatedField(queryset=Ride.objects.all())

    class Meta:
        model = RideEvent
        fields = ["id_ride_event", "id_ride", "description", "created_at"]


class RideSerializer(serializers.ModelSerializer):
    """Serializer used for creating/updating a single ride.

    Accepts rider/driver by primary key on write and returns the nested
    objects on read.
    """

    id_rider = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    id_driver = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model = Ride
        fields = [
            "id_ride",
            "status",
            "id_rider",
            "id_driver",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
        ]


class RideListSerializer(serializers.ModelSerializer):
    """Read serializer for the Ride List API.

    Includes the related rider and driver as nested objects, all related
    ride events, and ``todays_ride_events`` which contains only the events
    from the last 24 hours.

    ``todays_ride_events`` reads from ``ride._todays_events`` when the view
    has prefetched it (the efficient path), and otherwise falls back to a
    filtered query so the serializer is safe to use standalone.
    """

    id_rider = NestedUserSerializer(read_only=True)
    id_driver = NestedUserSerializer(read_only=True)
    events = RideEventSerializer(many=True, read_only=True)
    todays_ride_events = serializers.SerializerMethodField()

    class Meta:
        model = Ride
        fields = [
            "id_ride",
            "status",
            "id_rider",
            "id_driver",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
            "events",
            "todays_ride_events",
        ]

    def get_todays_ride_events(self, ride):
        # Prefer the attribute populated by the view's Prefetch. This avoids
        # issuing an additional query per ride.
        events = getattr(ride, "_todays_events", None)
        if events is None:
            from django.utils import timezone
            from datetime import timedelta

            cutoff = timezone.now() - timedelta(hours=24)
            events = ride.events.filter(created_at__gte=cutoff)
        return RideEventSerializer(events, many=True).data
