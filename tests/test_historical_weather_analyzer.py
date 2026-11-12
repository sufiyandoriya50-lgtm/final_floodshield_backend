import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.risk.historical_weather_analyzer import analyze_historical_weather


"""Creates a sample historical weather record for testing."""

def make_weather_record(
    rainfall=5.0,
    interval=900,
    latitude=23.0225,
    longitude=72.5714,
    recorded_at=None,
):
    if recorded_at is None:
        recorded_at = datetime.now(timezone.utc)

    return SimpleNamespace(
        rainfall_mm=rainfall,
        precipitation_interval_seconds=interval,
        latitude=latitude,
        longitude=longitude,
        recorded_at=recorded_at,
    )


def test_analyze_recent_nearby_rainfall():
    now = datetime.now(timezone.utc)

    record = make_weather_record(
        rainfall=5.0,
        interval=900,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        records=[record],
        latitude=23.0225,
        longitude=72.5714,
        now=now,
    )

    assert result["available"] is True
    assert result["maximum_precipitation_rate_mm_per_hour"] == 20.0
    assert result["category"] == "severe"


def test_ignore_weather_outside_radius():
    now = datetime.now(timezone.utc)

    record = make_weather_record(
        latitude=23.2,
        longitude=72.5714,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        records=[record],
        latitude=23.0225,
        longitude=72.5714,
        radius_km=5,
        now=now,
    )

    assert result["available"] is False


def test_ignore_weather_older_than_30_days():
    now = datetime.now(timezone.utc)

    record = make_weather_record(
        recorded_at=now - timedelta(days=31),
    )

    result = analyze_historical_weather(
        records=[record],
        latitude=23.0225,
        longitude=72.5714,
        now=now,
    )

    assert result["available"] is False


def test_ignore_record_without_precipitation_interval():
    now = datetime.now(timezone.utc)

    record = make_weather_record(
        interval=None,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        records=[record],
        latitude=23.0225,
        longitude=72.5714,
        now=now,
    )

    assert result["available"] is False


def test_ignore_future_weather_record():
    now = datetime.now(timezone.utc)

    record = make_weather_record(
        recorded_at=now + timedelta(hours=1),
    )

    result = analyze_historical_weather(
        records=[record],
        latitude=23.0225,
        longitude=72.5714,
        now=now,
    )

    assert result["available"] is False


def test_no_historical_weather_records():
    now = datetime.now(timezone.utc)

    result = analyze_historical_weather(
        records=[],
        latitude=23.0225,
        longitude=72.5714,
        now=now,
    )

    assert result["available"] is False

@pytest.mark.parametrize(
    "invalid_now",
    [
        "2026-11-12",
        datetime(2026, 11, 12, 10, 0),
    ],
)
def test_invalid_now_is_rejected(invalid_now):
    with pytest.raises(ValueError):
        analyze_historical_weather(
            [],
            latitude=23.0225,
            longitude=72.5714,
            now=invalid_now,
        )


@pytest.mark.parametrize(
    "latitude,longitude,radius",
    [
        (True, 72.5714, 5),
        (23.0225, False, 5),
        ("23.0225", 72.5714, 5),
        (23.0225, 72.5714, "5"),
        (float("nan"), 72.5714, 5),
        (23.0225, float("inf"), 5),
        (23.0225, 72.5714, float("nan")),
        (23.0225, 72.5714, float("inf")),
    ],
)
def test_non_finite_or_invalid_coordinates_and_radius(
    latitude,
    longitude,
    radius,
):
    with pytest.raises(ValueError):
        analyze_historical_weather(
            [],
            latitude=latitude,
            longitude=longitude,
            radius_km=radius,
        )


@pytest.mark.parametrize(
    "latitude,longitude,radius",
    [
        (91, 72.5714, 5),
        (-91, 72.5714, 5),
        (23.0225, 181, 5),
        (23.0225, -181, 5),
        (23.0225, 72.5714, 0),
        (23.0225, 72.5714, -1),
    ],
)
def test_out_of_range_coordinates_and_nonpositive_radius(
    latitude,
    longitude,
    radius,
):
    with pytest.raises(ValueError):
        analyze_historical_weather(
            [],
            latitude=latitude,
            longitude=longitude,
            radius_km=radius,
        )


@pytest.mark.parametrize(
    "rainfall",
    [True, False, "5", -1, float("nan"), float("inf")],
)
def test_invalid_rainfall_is_rejected(rainfall):
    now = datetime.now(timezone.utc)
    record = make_weather_record(
        rainfall=rainfall,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        [record], 23.0225, 72.5714, now=now
    )

    assert result["available"] is False
    assert result["observations_rejected"] == 1


@pytest.mark.parametrize(
    "interval",
    [None, True, False, 0, -900, 900.5, "900"],
)
def test_invalid_precipitation_interval_is_rejected(interval):
    now = datetime.now(timezone.utc)
    record = make_weather_record(
        interval=interval,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        [record], 23.0225, 72.5714, now=now
    )

    assert result["available"] is False
    assert result["observations_rejected"] == 1


def test_invalid_recorded_at_is_rejected():
    record = make_weather_record(recorded_at="invalid")

    result = analyze_historical_weather(
        [record], 23.0225, 72.5714
    )

    assert result["available"] is False
    assert result["observations_rejected"] == 1


def test_naive_recorded_at_is_treated_as_utc():
    now = datetime.now(timezone.utc)
    record = make_weather_record(
        recorded_at=now.replace(tzinfo=None),
    )

    result = analyze_historical_weather(
        [record], 23.0225, 72.5714, now=now
    )

    assert result["available"] is True
    assert result["observations_used"] == 1


def test_record_at_exact_window_boundary_is_accepted():
    now = datetime.now(timezone.utc)
    record = make_weather_record(
        recorded_at=now - timedelta(days=30),
    )

    result = analyze_historical_weather(
        [record], 23.0225, 72.5714, now=now
    )

    assert result["available"] is True


def test_invalid_record_coordinates_are_rejected():
    now = datetime.now(timezone.utc)
    record = make_weather_record(
        latitude=100,
        longitude=72.5714,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        [record], 23.0225, 72.5714, now=now
    )

    assert result["available"] is False
    assert result["observations_rejected"] == 1


def test_distance_calculation_error_is_rejected(monkeypatch):
    import app.risk.historical_weather_analyzer as analyzer

    now = datetime.now(timezone.utc)
    record = make_weather_record(recorded_at=now)

    def raise_distance_error(*args):
        raise ValueError("Invalid coordinates")

    monkeypatch.setattr(
        analyzer,
        "calculate_distance_km",
        raise_distance_error,
    )

    result = analyzer.analyze_historical_weather(
        [record], 23.0225, 72.5714, now=now
    )

    assert result["available"] is False
    assert result["observations_rejected"] == 1


@pytest.mark.parametrize(
    "rainfall,expected_category",
    [
        (0, "low"),
        (2.49, "low"),
        (2.5, "moderate"),
        (7.49, "moderate"),
        (7.5, "high"),
        (14.99, "high"),
        (15, "severe"),
        (30, "severe"),
    ],
)
def test_precipitation_intensity_categories(
    rainfall,
    expected_category,
):
    now = datetime.now(timezone.utc)
    record = make_weather_record(
        rainfall=rainfall,
        interval=3600,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        [record], 23.0225, 72.5714, now=now
    )

    assert result["available"] is True
    assert result["category"] == expected_category


def test_average_precipitation_rate():
    now = datetime.now(timezone.utc)

    records = [
        make_weather_record(
            rainfall=5,
            interval=3600,
            recorded_at=now,
        ),
        make_weather_record(
            rainfall=10,
            interval=3600,
            recorded_at=now,
        ),
    ]

    result = analyze_historical_weather(
        records, 23.0225, 72.5714, now=now
    )

    assert result["available"] is True
    assert result["maximum_precipitation_rate_mm_per_hour"] == 10
    assert result["average_precipitation_rate_mm_per_hour"] == 7.5
    assert result["observations_used"] == 2


def test_mixed_valid_and_rejected_records():
    now = datetime.now(timezone.utc)

    valid_record = make_weather_record(recorded_at=now)
    invalid_record = make_weather_record(
        interval=None,
        recorded_at=now,
    )

    result = analyze_historical_weather(
        [valid_record, invalid_record],
        23.0225,
        72.5714,
        now=now,
    )

    assert result["available"] is True
    assert result["observations_used"] == 1
    assert result["observations_rejected"] == 1
