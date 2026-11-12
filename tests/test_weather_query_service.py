
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.weather_record import WeatherRecord
from app.services.weather_query_service import (
    get_latest_weather,
    get_weather_history,
    get_weather_history_by_date,
)


# Creates a saved weather record for query-service tests.
def create_weather_record(latitude, longitude, recorded_at, rainfall=5.0):
    """Create and save a weather observation."""

    record = WeatherRecord(
        latitude=latitude,
        longitude=longitude,
        rainfall_mm=rainfall,
        temperature_c=30.0,
        wind_speed_kmh=10.0,
        source="Open-Meteo",
        recorded_at=recorded_at,
    )

    db.session.add(record)
    db.session.commit()

    return record


# Verifies that the latest query returns the newest matching record.
def test_get_latest_weather_returns_newest_record(app):
    with app.app_context():
        latitude = 23.0225
        longitude = 72.5714
        now = datetime.now(timezone.utc)

        create_weather_record(
            latitude,
            longitude,
            now - timedelta(hours=2),
            rainfall=2.0,
        )

        newest = create_weather_record(
            latitude,
            longitude,
            now,
            rainfall=8.0,
        )

        result = get_latest_weather(latitude, longitude)

        assert result is not None
        assert result["id"] == newest.id
        assert result["rainfall_mm"] == 8.0
        assert result["latitude"] == latitude
        assert result["longitude"] == longitude
        assert result["temperature_c"] == 30.0
        assert result["wind_speed_kmh"] == 10.0
        assert result["source"] == "Open-Meteo"
        assert result["recorded_at"] == now.replace(
            tzinfo=None
           ).isoformat()


# Verifies that the latest query returns None when no record exists.
def test_get_latest_weather_returns_none_when_not_found(app):
    with app.app_context():
        result = get_latest_weather(23.0225, 72.5714)

        assert result is None


# Verifies that weather history is ordered newest first.
def test_get_weather_history_returns_newest_first(app):
    with app.app_context():
        latitude = 23.0225
        longitude = 72.5714
        now = datetime.now(timezone.utc)

        create_weather_record(
            latitude,
            longitude,
            now - timedelta(hours=3),
        )

        newest = create_weather_record(
            latitude,
            longitude,
            now,
        )

        oldest = create_weather_record(
            latitude,
            longitude,
            now - timedelta(hours=5),
        )

        result = get_weather_history(latitude, longitude)

        assert len(result) == 3
        assert result[0]["id"] == newest.id
        assert result[2]["id"] == oldest.id


# Verifies that weather history respects the requested limit.
def test_get_weather_history_respects_limit(app):
    with app.app_context():
        latitude = 23.0225
        longitude = 72.5714
        now = datetime.now(timezone.utc)

        for hours in range(4):
            create_weather_record(
                latitude,
                longitude,
                now - timedelta(hours=hours),
            )

        result = get_weather_history(
            latitude,
            longitude,
            limit=2,
        )

        assert len(result) == 2


# Verifies that history returns an empty list when no records exist.
def test_get_weather_history_returns_empty_list(app):
    with app.app_context():
        result = get_weather_history(23.0225, 72.5714)

        assert result == []


# Verifies that weather history is restricted to exact coordinates.
def test_get_weather_history_filters_coordinates(app):
    with app.app_context():
        now = datetime.now(timezone.utc)

        create_weather_record(
            23.0225,
            72.5714,
            now,
        )

        create_weather_record(
            24.0000,
            73.0000,
            now,
        )

        result = get_weather_history(23.0225, 72.5714)

        assert len(result) == 1
        assert result[0]["latitude"] == 23.0225
        assert result[0]["longitude"] == 72.5714


# Verifies that date-range history returns matching records oldest first.
def test_get_weather_history_by_date_returns_matching_records(app):
    with app.app_context():
        latitude = 23.0225
        longitude = 72.5714
        now = datetime.now(timezone.utc)

        create_weather_record(
            latitude,
            longitude,
            now - timedelta(days=3),
        )

        middle = create_weather_record(
            latitude,
            longitude,
            now - timedelta(days=2),
        )

        newest = create_weather_record(
            latitude,
            longitude,
            now - timedelta(days=1),
        )

        start_date = (now - timedelta(days=2)).isoformat()
        end_date = now.isoformat()

        result = get_weather_history_by_date(
            latitude,
            longitude,
            start_date,
            end_date,
        )

        assert len(result) == 2
        assert result[0]["id"] == middle.id
        assert result[1]["id"] == newest.id


# Verifies that date-range queries include their boundary timestamps.
def test_get_weather_history_by_date_includes_boundaries(app):
    with app.app_context():
        latitude = 23.0225
        longitude = 72.5714
        now = datetime.now(timezone.utc)

        start = now - timedelta(hours=2)
        end = now

        first = create_weather_record(
            latitude,
            longitude,
            start,
        )

        last = create_weather_record(
            latitude,
            longitude,
            end,
        )

        result = get_weather_history_by_date(
            latitude,
            longitude,
            start.isoformat(),
            end.isoformat(),
        )

        result_ids = [record["id"] for record in result]

        assert first.id in result_ids
        assert last.id in result_ids


# Verifies that naive date strings are interpreted as UTC.
def test_get_weather_history_by_date_accepts_naive_dates(app):
    with app.app_context():
        latitude = 23.0225
        longitude = 72.5714
        now = datetime.now(timezone.utc).replace(microsecond=0)

        record = create_weather_record(
            latitude,
            longitude,
            now,
        )

        result = get_weather_history_by_date(
            latitude,
            longitude,
            (now - timedelta(minutes=1)).replace(tzinfo=None).isoformat(),
            (now + timedelta(minutes=1)).replace(tzinfo=None).isoformat(),
        )

        assert len(result) == 1
        assert result[0]["id"] == record.id


# Verifies that date-range history returns an empty list when no records match.
def test_get_weather_history_by_date_returns_empty_list(app):
    with app.app_context():
        now = datetime.now(timezone.utc)

        result = get_weather_history_by_date(
            23.0225,
            72.5714,
            (now - timedelta(days=10)).isoformat(),
            (now - timedelta(days=9)).isoformat(),
        )

        assert result == []
