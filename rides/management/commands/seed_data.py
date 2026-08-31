"""Populate the database with sample users, rides, and ride events.

Usage::

    python manage.py seed_data

Creates an admin user (email: admin@example.com / password: admin12345),
several drivers and riders, and a spread of rides with pickup/dropoff events
so the Ride List API and the SQL report can be exercised end-to-end.
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from rides.models import Ride, RideEvent, User


DRIVERS = [
    ("Chris", "H"),
    ("Howard", "Y"),
    ("Randy", "W"),
]

RIDERS = [
    ("Alice", "Nguyen", "alice@example.com"),
    ("Bob", "Smith", "bob@example.com"),
    ("Carol", "Diaz", "carol@example.com"),
]

# Rough GPS anchors so distance sorting produces a visible spread.
LOCATIONS = [
    (40.7128, -74.0060),   # New York
    (34.0522, -118.2437),  # Los Angeles
    (41.8781, -87.6298),   # Chicago
    (29.7604, -95.3698),   # Houston
    (47.6062, -122.3321),  # Seattle
]


class Command(BaseCommand):
    help = "Seed the database with sample data for the ride API."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Clearing existing data...")
        RideEvent.objects.all().delete()
        Ride.objects.all().delete()
        User.objects.all().delete()

        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="admin12345",
            first_name="Ada",
            last_name="Admin",
            phone_number="+15550000000",
        )
        self.stdout.write(self.style.SUCCESS(f"Created admin: {admin.email} / admin12345"))

        drivers = [
            User.objects.create_user(
                email=f"{first.lower()}.{last.lower()}@drivers.example.com",
                password="driver12345",
                role=User.Role.DRIVER,
                first_name=first,
                last_name=last,
                phone_number="+15551110000",
            )
            for first, last in DRIVERS
        ]

        riders = [
            User.objects.create_user(
                email=email,
                password="rider12345",
                role=User.Role.RIDER,
                first_name=first,
                last_name=last,
                phone_number="+15552220000",
            )
            for first, last, email in RIDERS
        ]

        now = timezone.now()
        statuses = [s for s, _ in Ride.Status.choices]
        rides_created = 0
        events_created = 0

        # Spread rides across the last few months for the SQL report, plus
        # a few very recent ones so todays_ride_events has data.
        for i in range(40):
            driver = random.choice(drivers)
            rider = random.choice(riders)
            pickup_loc = random.choice(LOCATIONS)
            dropoff_loc = random.choice(LOCATIONS)

            days_ago = random.randint(0, 150)
            pickup_time = now - timedelta(days=days_ago, hours=random.randint(0, 23))

            ride = Ride.objects.create(
                status=random.choice(statuses),
                id_rider=rider,
                id_driver=driver,
                pickup_latitude=pickup_loc[0],
                pickup_longitude=pickup_loc[1],
                dropoff_latitude=dropoff_loc[0],
                dropoff_longitude=dropoff_loc[1],
                pickup_time=pickup_time,
            )
            rides_created += 1

            # Pickup event.
            pickup_event_time = pickup_time
            RideEvent.objects.create(
                id_ride=ride,
                description="Status changed to pickup",
                created_at=pickup_event_time,
            )
            events_created += 1

            # Dropoff event: sometimes > 1 hour to exercise the report.
            trip_minutes = random.choice([25, 45, 70, 95, 130])
            dropoff_event_time = pickup_event_time + timedelta(minutes=trip_minutes)
            RideEvent.objects.create(
                id_ride=ride,
                description="Status changed to dropoff",
                created_at=dropoff_event_time,
            )
            events_created += 1

            # A few recent rides also get an extra recent event.
            if days_ago == 0:
                RideEvent.objects.create(
                    id_ride=ride,
                    description="Driver en route",
                    created_at=now - timedelta(minutes=random.randint(1, 120)),
                )
                events_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {len(drivers)} drivers, {len(riders)} riders, "
                f"{rides_created} rides, {events_created} ride events."
            )
        )
