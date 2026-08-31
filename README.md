# Ride Management API

A RESTful API built with **Django 6.1** and **Django REST Framework 3.18** that
manages ride information: users, rides, and ride events. It exposes full CRUD
through ViewSets and a performance-tuned **Ride List API** that returns each
ride together with its rider, driver, and events.

---

## Tech stack

| Component      | Version |
| -------------- | ------- |
| Python         | 3.14    |
| Django         | 6.1     |
| DRF            | 3.18    |
| django-filter  | 26.1    |
| Database       | SQLite (dev) — Postgres-ready |

---

## Features

- **Models** for `User`, `Ride`, and `RideEvent` that follow the assessment's
  table/field naming (`id_user`, `id_ride`, `id_rider`, `id_ride_event`, ...).
- **Serializers** for every model, with nested rider/driver and events on the
  ride list response.
- **ViewSets** providing CRUD for all three resources.
- **Admin-only authentication** — only users whose `role` is `admin` can call
  any endpoint.
- **Ride List API** with:
  - pagination (`page`, `page_size`)
  - filtering by ride `status` and by `rider_email`
  - sorting by `pickup_time` **or** by distance to a supplied GPS point
  - an extra `todays_ride_events` field containing only events from the last
    24 hours
  - a low, bounded SQL query count (rides list = **4 queries**: rides + JOINed
    users, 2 prefetches, 1 pagination COUNT)
- **Raw SQL report** for trips longer than one hour, grouped by month & driver.

---

## Setup

Requires Python 3.10+ (developed on 3.14).

```bash
# 1. Clone and enter the project
git clone <your-repo-url> ride-api-assessment
cd ride-api-assessment

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply migrations
python manage.py migrate

# 5. Seed sample data (creates an admin + drivers + riders + rides + events)
python manage.py seed_data

# 6. Run the development server
python manage.py runserver
```

The seed command prints the admin credentials:

```
admin@example.com / admin12345
```

You can also create your own admin:

```bash
python manage.py createsuperuser
# createsuperuser sets role='admin' automatically
```

---

## Authentication

All API endpoints require an authenticated user with `role == 'admin'`.
Non-admin users receive `403 Forbidden`; anonymous requests receive `403`.

The easiest way to explore is the **browsable API**:

1. Start the server and open <http://127.0.0.1:8000/api/>.
2. Click **Log in** (top right) and sign in with the admin credentials.

For scripted access, HTTP Basic auth is enabled:

```bash
curl -u admin@example.com:admin12345 http://127.0.0.1:8000/api/rides/
```

---

## Endpoints

| Method                  | URL                     | Description                    |
| ----------------------- | ----------------------- | ------------------------------ |
| GET/POST                | `/api/users/`           | List / create users            |
| GET/PUT/PATCH/DELETE    | `/api/users/{id}/`      | Retrieve / update / delete     |
| GET/POST                | `/api/rides/`           | **Ride List API** / create     |
| GET/PUT/PATCH/DELETE    | `/api/rides/{id}/`      | Retrieve / update / delete     |
| GET/POST                | `/api/ride-events/`     | List / create ride events      |
| GET/PUT/PATCH/DELETE    | `/api/ride-events/{id}/`| Retrieve / update / delete     |

### Ride List API query parameters

| Parameter      | Example                         | Notes                                        |
| -------------- | ------------------------------- | -------------------------------------------- |
| `status`       | `?status=pickup`                | Filter by ride status                        |
| `rider_email`  | `?rider_email=alice@example.com`| Filter by rider email (case-insensitive)     |
| `ordering`     | `?ordering=pickup_time`         | Also `-pickup_time`, `distance`, `-distance` |
| `pickup_lat`   | `?pickup_lat=40.7128`           | Required when sorting by distance            |
| `pickup_lng`   | `?pickup_lng=-74.0060`          | Required when sorting by distance            |
| `page`         | `?page=2`                       | Page number                                  |
| `page_size`    | `?page_size=25`                 | 1–100                                        |

Example — nearest rides to a pickup point, second page:

```bash
curl -u admin@example.com:admin12345 \
  "http://127.0.0.1:8000/api/rides/?ordering=distance&pickup_lat=40.7128&pickup_lng=-74.0060&page=2&page_size=10"
```

### Ride List response shape

```json
{
  "count": 40,
  "next": "http://127.0.0.1:8000/api/rides/?page=2",
  "previous": null,
  "results": [
    {
      "id_ride": 12,
      "status": "pickup",
      "id_rider": {
        "id_user": 5, "role": "rider",
        "first_name": "Alice", "last_name": "Nguyen",
        "email": "alice@example.com", "phone_number": "+15552220000"
      },
      "id_driver": { "id_user": 2, "role": "driver", "...": "..." },
      "pickup_latitude": 40.7128,
      "pickup_longitude": -74.006,
      "dropoff_latitude": 40.8128,
      "dropoff_longitude": -73.906,
      "pickup_time": "2026-08-30T12:00:00Z",
      "events": [ { "id_ride_event": 23, "id_ride": 12, "description": "...", "created_at": "..." } ],
      "todays_ride_events": [ { "id_ride_event": 24, "id_ride": 12, "description": "...", "created_at": "..." } ]
    }
  ]
}
```

---

## Running the tests

```bash
python manage.py test
```

The suite covers authentication/permissions, the list contract (nested
rider/driver, events, `todays_ride_events`), filtering, sorting (including
distance), pagination, and a **query-count assertion** that guards the
performance requirement.

---

## Bonus — SQL report

Report of trips whose duration (pickup → dropoff) exceeded one hour, grouped by
month and driver. Full script (PostgreSQL + SQLite variants) lives in
[`reports/trips_over_one_hour.sql`](reports/trips_over_one_hour.sql).

PostgreSQL version:

```sql
SELECT
    to_char(pickup.created_at, 'YYYY-MM')            AS month,
    driver.first_name || ' ' || driver.last_name     AS driver,
    COUNT(*)                                          AS trips_over_1hr
FROM ride AS r
JOIN ride_event AS pickup
    ON pickup.id_ride = r.id_ride
    AND pickup.description = 'Status changed to pickup'
JOIN ride_event AS dropoff
    ON dropoff.id_ride = r.id_ride
    AND dropoff.description = 'Status changed to dropoff'
JOIN "user" AS driver
    ON driver.id_user = r.id_driver
WHERE dropoff.created_at - pickup.created_at > INTERVAL '1 hour'
GROUP BY month, driver
ORDER BY month, driver;
```

Sample output shape:

```
Month    Driver     Count of Trips > 1 hr
2024-01  Chris H    4
2024-01  Howard Y   5
2024-02  Chris H    7
```

---

## Design notes & decisions

See [`docs/HOW_IT_WAS_BUILT.md`](docs/HOW_IT_WAS_BUILT.md) for a detailed
walkthrough of how the project was built, the design decisions behind each
requirement, and the challenges encountered.

Highlights:

- **Custom user model** (`AUTH_USER_MODEL = 'rides.User'`) so the `role` /
  `email` / `phone_number` columns match the spec while still plugging into
  Django auth.
- **Distance sorting in SQL**, not Python. The haversine formula is composed
  from Django ORM math functions (`Radians`, `Sin`, `Cos`, `ACos`) so the
  `ORDER BY` and `LIMIT/OFFSET` run in the database — this keeps sorting and
  pagination efficient even when the Ride table is very large.
- **`todays_ride_events` via `Prefetch`** with a filtered queryset and
  `to_attr`. Django never loads the full event list per ride; the last-24h
  events are fetched in a single additional query for the whole page.
- **Bounded query count**: `select_related` for rider/driver + two prefetches
  gives 1 rides query, 2 prefetch queries, and 1 pagination COUNT.
