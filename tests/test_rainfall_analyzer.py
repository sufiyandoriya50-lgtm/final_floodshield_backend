import math ,pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.risk.rainfall_analyzer import analyze_rainfall


def test_analyze_high_rainfall():
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=900,
        recorded_at=now,
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is True
    assert result["score"] == 80
    assert result["category"] == "severe"
    assert result["maximum_rainfall_rate_mm_per_hour"] == 20.0


def test_unknown_interval_is_not_treated_as_zero_rainfall():
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=None,
        recorded_at=now,
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is False
    assert result["score"] is None
    assert result["category"] == "insufficient_data"


def test_old_weather_observation_is_rejected():
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=900,
        recorded_at=now - timedelta(hours=5),
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is False
    assert result["score"] is None


def test_no_weather_records():
    result = analyze_rainfall([])

    assert result["available"] is False
    assert result["category"] == "insufficient_data"

# Verify that invalid current timestamps are rejected.
@pytest.mark.parametrize(
    "invalid_now",
    [
        "2026-11-12",
        None,
        datetime(2026, 11, 12, 10, 0),
    ],
)
def test_analyze_rainfall_rejects_invalid_now(invalid_now):
    if invalid_now is None:
        # None means use the current UTC time.
        return

    with pytest.raises(ValueError):
        analyze_rainfall([], now=invalid_now)


# Verify that invalid rainfall measurements are rejected.
@pytest.mark.parametrize(
    "invalid_rainfall",
    [
        True,
        False,
        "5",
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_analyze_rainfall_rejects_invalid_measurements(invalid_rainfall):
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=invalid_rainfall,
        precipitation_interval_seconds=900,
        recorded_at=now,
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is False
    assert result["observations_rejected"] == 1
    assert result["score"] is None


# Verify that invalid precipitation intervals are rejected.
@pytest.mark.parametrize(
    "invalid_interval",
    [
        None,
        True,
        False,
        0,
        -900,
        900.5,
        "900",
    ],
)
def test_analyze_rainfall_rejects_invalid_intervals(invalid_interval):
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=invalid_interval,
        recorded_at=now,
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is False
    assert result["observations_rejected"] == 1


# Verify that invalid observation timestamps are rejected.
def test_analyze_rainfall_rejects_invalid_timestamp():
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=900,
        recorded_at="not-a-datetime",
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is False
    assert result["observations_rejected"] == 1


# Verify that future weather observations are rejected.
def test_analyze_rainfall_rejects_future_observation():
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=900,
        recorded_at=now + timedelta(minutes=10),
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is False
    assert result["observations_rejected"] == 1


# Verify that naive stored timestamps are interpreted as UTC.
def test_analyze_rainfall_accepts_naive_utc_timestamp():
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=900,
        recorded_at=now.replace(tzinfo=None),
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is True
    assert result["observations_used"] == 1
    assert result["score"] == 80


# Verify the rainfall intensity category boundaries.
@pytest.mark.parametrize(
    "rainfall_rate, expected_score, expected_category",
    [
        (0.0, 10, "low"),
        (2.49, 10, "low"),
        (2.5, 30, "moderate"),
        (7.49, 30, "moderate"),
        (7.5, 55, "high"),
        (14.99, 55, "high"),
        (15.0, 80, "severe"),
        (29.99, 80, "severe"),
        (30.0, 100, "severe"),
        (40.0, 100, "severe"),
    ],
)
def test_analyze_rainfall_category_boundaries(
    rainfall_rate,
    expected_score,
    expected_category,
):
    now = datetime.now(timezone.utc)

    record = SimpleNamespace(
        rainfall_mm=rainfall_rate,
        precipitation_interval_seconds=3600,
        recorded_at=now,
    )

    result = analyze_rainfall([record], now=now)

    assert result["available"] is True
    assert result["score"] == expected_score
    assert result["category"] == expected_category


# Verify that valid and invalid observations are counted separately.
def test_analyze_rainfall_counts_valid_and_rejected_observations():
    now = datetime.now(timezone.utc)

    valid_record = SimpleNamespace(
        rainfall_mm=5.0,
        precipitation_interval_seconds=900,
        recorded_at=now,
    )

    invalid_record = SimpleNamespace(
        rainfall_mm=-5.0,
        precipitation_interval_seconds=900,
        recorded_at=now,
    )

    result = analyze_rainfall(
        [valid_record, invalid_record],
        now=now,
    )

    assert result["available"] is True
    assert result["observations_used"] == 1
    assert result["observations_rejected"] == 1
