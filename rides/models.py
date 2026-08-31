"""Data models for the ride management API.

The table/field names follow the assessment's specification (``id_ride``,
``id_rider``, ``id_ride_event`` etc.) while still integrating with Django's
authentication system through a custom ``User`` model.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    """Manager for the custom :class:`User` model.

    Django's auth framework expects ``create_user`` / ``create_superuser``
    helpers. We key users off ``email`` since the spec has no username field.
    """

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Application user.

    Maps to the assessment's ``User`` table. The primary key column is named
    ``id_user`` to match the specification.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        DRIVER = "driver", "Driver"
        RIDER = "rider", "Rider"

    id_user = models.AutoField(primary_key=True)
    role = models.CharField(max_length=50, choices=Role.choices, default=Role.RIDER)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=32, blank=True)

    # Flags required by django.contrib.auth.
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "user"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} <{self.email}>".strip()

    @property
    def is_admin_role(self) -> bool:
        """Business-role check used by the admin-only permission class."""
        return self.role == self.Role.ADMIN


class Ride(models.Model):
    """A single ride/trip, matching the assessment's ``Ride`` table."""

    class Status(models.TextChoices):
        EN_ROUTE = "en-route", "En route"
        PICKUP = "pickup", "Pickup"
        DROPOFF = "dropoff", "Dropoff"

    id_ride = models.AutoField(primary_key=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    id_rider = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="rides_as_rider",
        db_column="id_rider",
    )
    id_driver = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="rides_as_driver",
        db_column="id_driver",
    )
    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    dropoff_latitude = models.FloatField()
    dropoff_longitude = models.FloatField()
    pickup_time = models.DateTimeField()

    class Meta:
        db_table = "ride"
        indexes = [
            # Supports filtering by status and sorting by pickup_time,
            # which is important once the Ride table grows very large.
            models.Index(fields=["status"]),
            models.Index(fields=["pickup_time"]),
        ]

    def __str__(self):
        return f"Ride #{self.id_ride} ({self.status})"


class RideEvent(models.Model):
    """An event that happened during a ride, e.g. status changes."""

    id_ride_event = models.AutoField(primary_key=True)
    id_ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name="events",
        db_column="id_ride",
    )
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "ride_event"
        indexes = [
            # The RideEvent table is expected to be huge; this composite index
            # makes the "last 24 hours" lookup per ride cheap.
            models.Index(fields=["id_ride", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Event #{self.id_ride_event} for Ride #{self.id_ride_id}"
