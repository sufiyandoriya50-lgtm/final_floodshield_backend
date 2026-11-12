from datetime import datetime, timezone
from unittest.mock import Mock

import app.risk.combined_risk_engine as risk_engine
from app.risk.combined_risk_engine import (
    calculate_weighted_risk,
    classify_risk,
)


def test_combines_all_three_factors():
    factors = {
        "rainfall": {"available": True, "score": 80},
        "community_reports": {"available": True, "score": 75},
        "historical_floods": {"available": True, "score": 60},
    }

    result = calculate_weighted_risk(factors)

    assert result == 73.25


def test_renormalizes_when_rainfall_is_missing():
    factors = {
        "rainfall": {"available": False, "score": None},
        "community_reports": {"available": True, "score": 75},
        "historical_floods": {"available": True, "score": 60},
    }

    result = calculate_weighted_risk(factors)

    assert result == 68.75


def test_returns_none_when_all_factors_are_missing():
    factors = {
        "rainfall": {"available": False, "score": None},
        "community_reports": {"available": False, "score": None},
        "historical_floods": {"available": False, "score": None},
    }

    result = calculate_weighted_risk(factors)

    assert result is None


def test_rejects_invalid_score():
    factors = {
        "rainfall": {"available": True, "score": 150},
    }

    try:
        calculate_weighted_risk(factors)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_classifies_risk_levels():
    assert classify_risk(10) == "low"
    assert classify_risk(30) == "moderate"
    assert classify_risk(60) == "high"
    assert classify_risk(80) == "severe"

# Tests the combined assessment when no risk factors are available.
def test_assess_flood_risk_returns_insufficient_data(monkeypatch):
    now = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

    rainfall = Mock(return_value={
        "available": False,
        "score": None,
    })
    historical = Mock(return_value={
        "available": False,
        "score": None,
    })
    community = Mock(return_value={
        "available": False,
        "score": None,
    })
    historical_weather = Mock(return_value={
        "available": False,
        "category": "insufficient_data",
    })

    monkeypatch.setattr(risk_engine, "analyze_rainfall", rainfall)
    monkeypatch.setattr(
        risk_engine, "analyze_historical_flood_risk", historical
    )
    monkeypatch.setattr(
        risk_engine, "analyze_community_reports", community
    )
    monkeypatch.setattr(
        risk_engine, "analyze_historical_weather", historical_weather
    )

    result = risk_engine.assess_flood_risk(
        latitude=23.0225,
        longitude=72.5714,
        weather_records=[],
        historical_events=[],
        community_reports=[],
        now=now,
    )

    assert result["available"] is False
    assert result["risk_level"] == "insufficient_data"
    assert result["risk_score"] is None
    assert result["data_completeness_percent"] == 0
    assert result["message"] == (
        "Insufficient data to calculate flood risk."
    )
    assert result["assessed_at"] == now.isoformat()

    assert set(result["factors"]) == {
        "rainfall",
        "historical_floods",
        "community_reports",
    }

    rainfall.assert_called_once_with([], now=now)
    historical.assert_called_once()
    community.assert_called_once()
    historical_weather.assert_called_once_with(
        records=[],
        latitude=23.0225,
        longitude=72.5714,
        radius_km=5.0,
        now=now,
    )


# Tests the combined assessment when some risk factors are available.
def test_assess_flood_risk_combines_available_factors(monkeypatch):
    now = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    historical_weather_records = [Mock()]

    rainfall = Mock(return_value={
        "available": True,
        "score": 50,
    })
    historical = Mock(return_value={
        "available": True,
        "score": 80,
    })
    community = Mock(return_value={
        "available": False,
        "score": None,
    })
    historical_weather = Mock(return_value={
        "available": True,
        "category": "high",
    })

    monkeypatch.setattr(risk_engine, "analyze_rainfall", rainfall)
    monkeypatch.setattr(
        risk_engine, "analyze_historical_flood_risk", historical
    )
    monkeypatch.setattr(
        risk_engine, "analyze_community_reports", community
    )
    monkeypatch.setattr(
        risk_engine, "analyze_historical_weather", historical_weather
    )

    result = risk_engine.assess_flood_risk(
        latitude=23.0225,
        longitude=72.5714,
        weather_records=["weather"],
        historical_events=["event"],
        community_reports=["report"],
        radius_km=10.0,
        now=now,
        historical_weather_records=historical_weather_records,
    )

    assert result["available"] is True
    assert result["risk_score"] == 61.54
    assert result["risk_level"] == "high"
    assert result["data_completeness_percent"] == 65
    assert result["assessed_at"] == now.isoformat()
    assert result["historical_weather_context"] == {
        "available": True,
        "category": "high",
    }

    rainfall.assert_called_once_with(["weather"], now=now)
    historical.assert_called_once_with(
        ["event"],
        latitude=23.0225,
        longitude=72.5714,
        radius_km=10.0,
    )
    community.assert_called_once_with(
        ["report"],
        latitude=23.0225,
        longitude=72.5714,
        radius_km=10.0,
        now=now,
    )
    historical_weather.assert_called_once_with(
        records=historical_weather_records,
        latitude=23.0225,
        longitude=72.5714,
        radius_km=10.0,
        now=now,
    )
# Tests automatic UTC timestamp generation when now is not supplied.
def test_assess_flood_risk_generates_default_timestamp(monkeypatch):
    expected_now = datetime(
        2026, 11, 12, 10, 0, tzinfo=timezone.utc
    )

    datetime_mock = Mock()
    datetime_mock.now.return_value = expected_now

    monkeypatch.setattr(risk_engine, "datetime", datetime_mock)

    monkeypatch.setattr(
        risk_engine,
        "analyze_rainfall",
        Mock(return_value={"available": False, "score": None}),
    )
    monkeypatch.setattr(
        risk_engine,
        "analyze_historical_flood_risk",
        Mock(return_value={"available": False, "score": None}),
    )
    monkeypatch.setattr(
        risk_engine,
        "analyze_community_reports",
        Mock(return_value={"available": False, "score": None}),
    )
    monkeypatch.setattr(
        risk_engine,
        "analyze_historical_weather",
        Mock(return_value={"available": False}),
    )

    result = risk_engine.assess_flood_risk(
        latitude=23.0225,
        longitude=72.5714,
        weather_records=[],
        historical_events=[],
        community_reports=[],
    )

    datetime_mock.now.assert_called_once_with(timezone.utc)
    assert result["assessed_at"] == expected_now.isoformat()
    assert result["available"] is False
