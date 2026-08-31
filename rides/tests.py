"""Tests for the ride management API.

Covers authentication/permissions, the Ride List API contract (nested
rider/driver, events, todays_ride_events), filtering, sorting, pagination,
and the critical query-count performance requirement.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Ride, RideEvent, User


class BaseAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            password="pw",
            first_name="Ada",
            last_name="Admin",
        )
        self.non_admin = User.objects.create_user(
            email="rider@example.com",
            password="pw",
            role=User.Role.RIDER,
            first_name="Rae",
            last_name="Rider",
        )
        self.driver = User.objects.create_user(
            email="driver@example.com",
            password="pw",
            role=User.Role.DRIVER,
            first_name="Chris",
            last_name="H",
        )

    def _make_ride(self, rider, driver, lat, lng, pickup_time=None, status="pickup"):
        return Ride.objects.create(
            status=status,
            id_rider=rider,
            id_driver=driver,
            pickup_latitude=lat,
            pickup_longitude=lng,
            dropoff_latitude=lat + 0.1,
            dropoff_longitude=lng + 0.1,
            pickup_time=pickup_time or timezone.now(),
        )


class AuthPermissionTests(BaseAPITestCase):
    def test_anonymous_denied(self):
        resp = self.client.get("/api/rides/")
        self.assertIn(resp.status_code, (401, 403))

    def test_non_admin_denied(self):
        self.client.force_authenticate(self.non_admin)
        resp = self.client.get("/api/rides/")
        self.assertEqual(resp.status_code, 403)

    def test_admin_allowed(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/rides/")
        self.assertEqual(resp.status_code, 200)


class RideListContractTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        now = timezone.now()
        self.ride = self._make_ride(self.non_admin, self.driver, 40.7, -74.0, now)
        # One recent event (within 24h) and one old event (outside 24h).
        RideEvent.objects.create(
            id_ride=self.ride, description="Status changed to pickup", created_at=now
        )
        RideEvent.objects.create(
            id_ride=self.ride,
            description="old event",
            created_at=now - timedelta(hours=48),
        )

    def test_list_includes_nested_and_events(self):
        resp = self.client.get("/api/rides/")
        self.assertEqual(resp.status_code, 200)
        result = resp.data["results"][0]
        self.assertEqual(result["id_rider"]["email"], "rider@example.com")
        self.assertEqual(result["id_driver"]["email"], "driver@example.com")
        self.assertEqual(len(result["events"]), 2)
        # Only the event within 24h should appear in todays_ride_events.
        self.assertEqual(len(result["todays_ride_events"]), 1)
        self.assertEqual(
            result["todays_ride_events"][0]["description"], "Status changed to pickup"
        )

    def test_filter_by_status(self):
        self._make_ride(self.non_admin, self.driver, 1, 1, status="en-route")
        resp = self.client.get("/api/rides/?status=en-route")
        self.assertEqual(resp.data["count"], 1)

    def test_filter_by_rider_email(self):
        other = User.objects.create_user(
            email="other@example.com", password="pw", role=User.Role.RIDER,
            first_name="O", last_name="T",
        )
        self._make_ride(other, self.driver, 2, 2)
        resp = self.client.get("/api/rides/?rider_email=other@example.com")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id_rider"]["email"], "other@example.com")

    def test_sort_by_pickup_time(self):
        now = timezone.now()
        self._make_ride(self.non_admin, self.driver, 3, 3, now + timedelta(days=1))
        resp = self.client.get("/api/rides/?ordering=-pickup_time")
        times = [r["pickup_time"] for r in resp.data["results"]]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_sort_by_distance_requires_coords(self):
        resp = self.client.get("/api/rides/?ordering=distance")
        self.assertEqual(resp.status_code, 400)

    def test_sort_by_distance(self):
        # Near point should come before far point.
        near = self._make_ride(self.non_admin, self.driver, 40.71, -74.01)
        far = self._make_ride(self.non_admin, self.driver, 10.0, 10.0)
        resp = self.client.get(
            "/api/rides/?ordering=distance&pickup_lat=40.7128&pickup_lng=-74.0060"
        )
        ids = [r["id_ride"] for r in resp.data["results"]]
        self.assertLess(ids.index(near.id_ride), ids.index(far.id_ride))

    def test_pagination_with_sorting(self):
        for i in range(15):
            self._make_ride(self.non_admin, self.driver, i, i)
        resp = self.client.get("/api/rides/?ordering=pickup_time&page_size=5")
        self.assertEqual(len(resp.data["results"]), 5)
        self.assertIsNotNone(resp.data["next"])


class QueryCountTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        now = timezone.now()
        for i in range(10):
            ride = self._make_ride(self.non_admin, self.driver, i, i, now)
            for j in range(3):
                RideEvent.objects.create(
                    id_ride=ride, description=f"event {j}", created_at=now
                )

    def test_query_count_is_bounded(self):
        # 1 rides(+JOINed users) + 2 prefetch (events, todays) + 1 COUNT = 4.
        with self.assertNumQueries(4):
            resp = self.client.get("/api/rides/?page_size=10")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(resp.data["results"]), 10)
