
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from app.risk.historical_flood_analyzer import (
    analyze_historical_flood_risk,
)


def test_nearby_severe_flood_event():
    event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity="severe",
        event_date=datetime.now(timezone.utc) - timedelta(days=10),
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is True
    assert result["score"] == 100
    assert result["category"] == "severe"
    assert result["nearby_events"] == 1


def test_event_outside_search_radius():
    event = SimpleNamespace(
        latitude=23.2,
        longitude=72.8,
        severity="severe",
        event_date=datetime.now(timezone.utc),
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is False
    assert result["score"] is None


def test_no_historical_events():
    result = analyze_historical_flood_risk(
        [],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is False
    assert result["category"] == "insufficient_data"


def test_invalid_latitude():
    with pytest.raises(ValueError):
        analyze_historical_flood_risk(
            [],
            latitude=100,
            longitude=72.5714,
        )


def test_future_event_is_ignored():
    event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity="severe",
        event_date=datetime.now(timezone.utc) + timedelta(days=10),
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is False
    assert result["score"] is None


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (True, 72.5714),
        (23.0225, False),
        ("23.0225", 72.5714),
        (float("nan"), 72.5714),
        (23.0225, float("inf")),
        (-91, 72.5714),
        (23.0225, 181),
    ],
)
def test_invalid_coordinates_are_rejected(latitude, longitude):
    with pytest.raises(ValueError):
        analyze_historical_flood_risk(
            [],
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    "radius",
    [True, False, 0, -1, float("nan"), float("inf"), "5"],
)
def test_invalid_radius_is_rejected(radius):
    with pytest.raises(ValueError):
        analyze_historical_flood_risk(
            [],
            latitude=23.0225,
            longitude=72.5714,
            radius_km=radius,
        )


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (True, 72.5714),
        (100, 72.5714),
        (23.0225, False),
        (23.0225, -181),
    ],
)
def test_invalid_event_coordinates_are_ignored(latitude, longitude):
    event = SimpleNamespace(
        latitude=latitude,
        longitude=longitude,
        severity="severe",
        event_date=datetime.now(timezone.utc),
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is False
    assert result["nearby_events"] == 0


@pytest.mark.parametrize(
    "severity",
    [None, "", "unknown", "critical"],
)
def test_invalid_severity_is_ignored(severity):
    event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity=severity,
        event_date=datetime.now(timezone.utc),
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is False


@pytest.mark.parametrize(
    "event_date",
    ["invalid date", None, 123],
)
def test_invalid_event_date_is_ignored(event_date):
    event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity="severe",
        event_date=event_date,
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is False


def test_naive_event_timestamp_is_supported():
    event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity="high",
        event_date=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is True
    assert result["category"] == "high"


@pytest.mark.parametrize(
    "severity,expected_score,expected_category",
    [
        ("low", 20, "low"),
        ("moderate", 45, "moderate"),
        ("high", 70, "high"),
        ("severe", 100, "severe"),
    ],
)
def test_historical_severity_categories(
    severity,
    expected_score,
    expected_category,
):
    event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity=severity,
        event_date=datetime.now(timezone.utc),
    )

    result = analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is True
    assert result["score"] == expected_score
    assert result["category"] == expected_category


def test_zero_weight_returns_insufficient_data(monkeypatch):
    import app.risk.historical_flood_analyzer as analyzer

    event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity="severe",
        event_date=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(
        analyzer,
        "calculate_distance_km",
        lambda *args: 5.0,
    )

    result = analyzer.analyze_historical_flood_risk(
        [event],
        latitude=23.0225,
        longitude=72.5714,
        radius_km=5.0,
    )

    assert result["available"] is False
    assert result["nearby_events"] == 1
    assert result["category"] == "insufficient_data"


def test_invalid_event_does_not_prevent_valid_event():
    invalid_event = SimpleNamespace(
        latitude=100,
        longitude=72.5714,
        severity="severe",
        event_date=datetime.now(timezone.utc),
    )

    valid_event = SimpleNamespace(
        latitude=23.0225,
        longitude=72.5714,
        severity="moderate",
        event_date=datetime.now(timezone.utc),
    )

    result = analyze_historical_flood_risk(
        [invalid_event, valid_event],
        latitude=23.0225,
        longitude=72.5714,
    )

    assert result["available"] is True
    assert result["nearby_events"] == 1
    assert result["category"] == "moderate"
