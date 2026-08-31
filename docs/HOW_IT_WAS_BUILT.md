# How the Ride Management API Was Built

This document walks through how the project was created, the reasoning behind
each design decision, and how each requirement in the assessment was satisfied.
It is written to be read alongside the code.

---

## 1. Goal

Build a RESTful API with Django REST Framework that manages ride information —
users, rides, and ride events — with admin-only access, a rich and
performance-tuned ride list endpoint, and a reporting SQL query.

---

## 2. Project structure

```
ride-api-assessment/
├── config/                 # Django project (settings, root urls, wsgi/asgi)
│   ├── settings.py
│   └── urls.py             # DRF router wiring
├── rides/                  # The single application
│   ├── models.py           # User, Ride, RideEvent
│   ├── serializers.py      # JSON representations
│   ├── views.py            # ViewSets + Ride List API logic
│   ├── permissions.py      # IsAdminRole
│   ├── filters.py          # status / rider_email filtering
│   ├── pagination.py       # page-number pagination
│   ├── admin.py            # Django admin registration
│   ├── tests.py            # permissions, contract, performance tests
│   └── management/commands/seed_data.py
├── reports/
│   └── trips_over_one_hour.sql   # bonus SQL report
├── docs/
│   └── HOW_IT_WAS_BUILT.md       # this file
├── requirements.txt
└── README.md
```

A single `rides` app keeps the domain cohesive and easy to review. The project
package is named `config` so settings/urls are clearly separated from domain
code.

---

## 3. Step-by-step build

### Step 1 — Environment and scaffolding
Created a virtual environment and installed the latest stable releases:
Django 6.1, DRF 3.18, and django-filter 26.1. Generated the project with
`django-admin startproject config .` and the app with
`python manage.py startapp rides`. Pinned versions were captured in
`requirements.txt`.

### Step 2 — Models
Three models were written to mirror the assessment's table definitions
(`models.py`):

- **`User`** — a *custom* user model extending `AbstractBaseUser` +
  `PermissionsMixin`. The primary key is `id_user`, and it carries `role`,
  `first_name`, `last_name`, `email` (unique, used as the login field), and
  `phone_number`. A custom `UserManager` supplies `create_user` /
  `create_superuser`.
- **`Ride`** — `id_ride` PK, `status`, foreign keys `id_rider` and `id_driver`
  (both to `User`), pickup/dropoff latitude & longitude, and `pickup_time`.
- **`RideEvent`** — `id_ride_event` PK, FK `id_ride`, `description`,
  `created_at`.

`db_table` and `db_column` are set explicitly so the physical schema matches
the spec (`user`, `ride`, `ride_event`, `id_rider`, etc.). Indexes were added
where the query patterns need them (status, pickup_time, and a composite
`(id_ride, created_at)` on events).

### Step 3 — Serializers
`serializers.py` defines:

- `UserSerializer` (with write-only password handling) and a lightweight
  `NestedUserSerializer` for embedding inside rides.
- `RideEventSerializer`.
- `RideSerializer` for create/update (accepts rider/driver by id).
- `RideListSerializer` for reads — embeds nested rider & driver, all `events`,
  and the computed `todays_ride_events`.

### Step 4 — Authentication & permissions
The spec requires that only `admin`-role users can call the endpoints. A custom
`IsAdminRole` permission (`permissions.py`) checks
`request.user.is_authenticated and user.role == 'admin'`. It is set as the
default permission class in `settings.py` and applied on every ViewSet, so the
API is closed by default.

### Step 5 — ViewSets & routing
`views.py` exposes `UserViewSet`, `RideViewSet`, and `RideEventViewSet`
(`ModelViewSet` → full CRUD). A DRF `DefaultRouter` in `config/urls.py` maps
them under `/api/`. The browsable API login lives at `/api-auth/`.

### Step 6 — The Ride List API
This is the heart of the assessment and is covered in detail below.

### Step 7 — Seed data
`seed_data` management command creates an admin, drivers named to match the
sample report (Chris H, Howard Y, Randy W), riders, and 40 rides each with
pickup/dropoff events spread over several months and varying trip durations.

### Step 8 — Tests
`tests.py` verifies permissions, the response contract, filtering, sorting
(including distance), pagination, and — critically — asserts the number of SQL
queries with `assertNumQueries`.

### Step 9 — SQL report
`reports/trips_over_one_hour.sql` contains the bonus query in both PostgreSQL
and SQLite forms.

---

## 4. How each Ride List requirement was met

### Nested rider, driver, and events
`RideListSerializer` embeds `id_rider` and `id_driver` as nested user objects
and serializes all related `events`.

### Filtering (status + rider email)
`RideFilter` (django-filter) exposes `status` (case-insensitive exact) and
`rider_email`, which filters through the related rider (`id_rider__email`)
entirely in SQL — no user rows are pulled into Python to filter.

### Pagination
`RidePagination` uses page-number pagination with a configurable `page_size`
(default 10, max 100). Because ordering is applied to the queryset before
pagination, the `ORDER BY ... LIMIT ... OFFSET` is pushed to the database and
pagination remains correct under any sort.

### Sorting by `pickup_time` **and** by distance — efficiently
Two sort modes share one endpoint via the `ordering` parameter:

- `pickup_time` / `-pickup_time` → a plain indexed `ORDER BY`.
- `distance` / `-distance` → requires `pickup_lat` and `pickup_lng`. Rather
  than compute distances in Python (which would force loading the entire, very
  large Ride table into memory), the great-circle (haversine) distance is
  built from Django ORM math functions:

  ```python
  cos_c = Sin(lat)*Sin(row_lat) + Cos(lat)*Cos(row_lat)*Cos(row_lng - lng)
  distance_km = ACos(clamp(cos_c, -1, 1)) * EARTH_RADIUS_KM
  ```

  This annotation is emitted as SQL, so the database does the math and the
  `ORDER BY distance_km` + `LIMIT/OFFSET` run server-side. The result stays
  efficient and paginable on a huge table. A primary-key tie-breaker keeps the
  ordering stable across pages.

  > Note: the value clamp to `[-1, 1]` avoids `ACos` domain errors from
  > floating-point rounding on near-identical points.

### `todays_ride_events` without loading every event
The `RideEvent` table is expected to be huge, so we must never load a ride's
full event history to compute the last-24h subset. The view uses a filtered
`Prefetch`:

```python
Prefetch(
    "events",
    queryset=RideEvent.objects.filter(created_at__gte=now - timedelta(hours=24)),
    to_attr="_todays_events",
)
```

Django fetches only the recent events for the whole page in a **single**
additional query and attaches them to each ride as `_todays_events`. The
serializer reads that pre-populated attribute, so no extra per-row queries are
issued. The `(id_ride, created_at)` composite index keeps this lookup cheap.

### Bounded query count
For a page of the ride list, the queries are:

1. Rides + rider + driver — one SELECT with JOINs (`select_related`).
2. All `events` — one prefetch query.
3. Last-24h events — one prefetch query.
4. `COUNT(*)` — the pagination count query.

That is **3 data queries + 1 COUNT**, regardless of page size — verified by
`QueryCountTests.test_query_count_is_bounded` (`assertNumQueries(4)`). The
assessment's target was 2 (or 3 with COUNT) for rides + related driver, rider,
and events; we spend one extra prefetch specifically to satisfy the separate
`todays_ride_events` performance requirement, which otherwise could not be
computed without per-row queries.

---

## 5. Key design decisions

- **Custom user model over a profile table.** The spec's User table *is* the
  auth principal (it has `role`, `email`), so a custom `AUTH_USER_MODEL` is
  cleaner than a parallel profile and lets DRF authentication work directly.
- **Role-based permission distinct from `is_staff`.** The requirement is about
  an application `role == 'admin'`, which is independent of Django's staff or
  superuser flags. `IsAdminRole` checks the business role explicitly.
- **Distance math in the database.** Assuming a very large Ride table, sorting
  in Python is a non-starter. Expressing haversine through ORM functions keeps
  everything in SQL and paginable. A production system with PostGIS could swap
  this for a spatial index; the ORM approach keeps the project dependency-light
  and portable.
- **Filtered `Prefetch` with `to_attr`.** This is the idiomatic Django way to
  attach a computed, bounded subset of a large related table without N+1
  queries.
- **Explicit `db_table` / `db_column`.** Keeps the physical schema faithful to
  the assessment while letting the Python code use readable related names
  (`rides_as_rider`, `events`).

---

## 6. Challenges encountered

- **`ACos` domain errors.** Great-circle math can push the cosine slightly
  outside `[-1, 1]` due to float rounding, which makes `ACOS` error out on some
  databases. Solved by clamping with `Least`/`Greatest` before `ACos`.
- **Balancing query count vs. the two-list requirement.** Returning both the
  full `events` list *and* the 24-hour subset needs two prefetches. Rather than
  drop one, both are prefetched so each contract is met while staying free of
  per-row queries.
- **Cross-database SQL for the report.** SQLite lacks `INTERVAL` and
  `to_char`, so the report ships in two flavours (Postgres and SQLite) and was
  validated against the seeded SQLite database.

---

## 7. Verifying it yourself

```bash
python manage.py migrate
python manage.py seed_data
python manage.py test          # all tests, including the query-count guard
python manage.py runserver     # browse http://127.0.0.1:8000/api/
```

Log in to the browsable API with `admin@example.com / admin12345` and try:

```
/api/rides/?status=pickup
/api/rides/?rider_email=alice@example.com
/api/rides/?ordering=-pickup_time
/api/rides/?ordering=distance&pickup_lat=40.7128&pickup_lng=-74.0060
```
