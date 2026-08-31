-- Report: count of trips whose duration (pickup -> dropoff) exceeded 1 hour,
-- grouped by month and by driver.
--
-- Trip duration is derived from RideEvent rows:
--   * pickup  = event with description 'Status changed to pickup'
--   * dropoff = event with description 'Status changed to dropoff'
-- The difference between their created_at timestamps is the trip duration.
--
-- The Ride table structure cannot be changed, so the trip distance/duration
-- is computed on the fly from the events table.
--
-- This is the PostgreSQL-flavoured version. A SQLite variant (used by the
-- default dev database) is provided below.

-- ============================================================================
-- PostgreSQL
-- ============================================================================
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


-- ============================================================================
-- SQLite (default development database)
-- ============================================================================
-- SQLite has no INTERVAL type; compare julianday() differences (in days).
-- 1 hour = 1.0 / 24.0 days.
--
-- SELECT
--     strftime('%Y-%m', pickup.created_at)               AS month,
--     driver.first_name || ' ' || driver.last_name       AS driver,
--     COUNT(*)                                            AS trips_over_1hr
-- FROM ride AS r
-- JOIN ride_event AS pickup
--     ON pickup.id_ride = r.id_ride
--     AND pickup.description = 'Status changed to pickup'
-- JOIN ride_event AS dropoff
--     ON dropoff.id_ride = r.id_ride
--     AND dropoff.description = 'Status changed to dropoff'
-- JOIN user AS driver
--     ON driver.id_user = r.id_driver
-- WHERE (julianday(dropoff.created_at) - julianday(pickup.created_at)) > (1.0 / 24.0)
-- GROUP BY month, driver
-- ORDER BY month, driver;
