
import pytest

from app import create_app
from app.config import TestingConfig


# Creates a Flask application configured for API tests.
@pytest.fixture
def app():
    return create_app(TestingConfig)


# Provides a test client for sending API requests.
@pytest.fixture
def client(app):
    return app.test_client()


# Tests successful retrieval of current weather.
def test_current_weather_success(client, monkeypatch):
    expected = {"temperature": 30, "rainfall": 2}

    monkeypatch.setattr(
        "app.routes.weather.get_current_weather",
        lambda latitude, longitude: expected
    )

    response = client.get(
        "/api/weather/current?latitude=23.02&longitude=72.57"
    )

    assert response.status_code == 200
    assert response.json["status"] == "success"
    assert response.json["data"] == expected


# Tests missing coordinates for current weather.
def test_current_weather_missing_coordinates(client):
    response = client.get("/api/weather/current")

    assert response.status_code == 400


# Tests invalid current weather input.
def test_current_weather_value_error(client, monkeypatch):
    def mock_weather(latitude, longitude):
        raise ValueError("Invalid coordinates")

    monkeypatch.setattr(
        "app.routes.weather.get_current_weather",
        mock_weather
    )

    response = client.get(
        "/api/weather/current?latitude=23&longitude=72"
    )

    assert response.status_code == 400
    assert "Invalid coordinates" in response.json["message"]


# Tests external weather API failure.
def test_current_weather_runtime_error(client, monkeypatch):
    def mock_weather(latitude, longitude):
        raise RuntimeError("Weather provider unavailable")

    monkeypatch.setattr(
        "app.routes.weather.get_current_weather",
        mock_weather
    )

    response = client.get(
        "/api/weather/current?latitude=23&longitude=72"
    )

    assert response.status_code == 502


# Tests successful weather collection and storage.
def test_collect_weather_success(client, monkeypatch):
    weather = {"temperature": 30, "rainfall": 2}

    class SavedRecord:
        id = 101

    monkeypatch.setattr(
        "app.routes.weather.get_current_weather",
        lambda latitude, longitude: weather
    )
    monkeypatch.setattr(
        "app.routes.weather.save_weather_record",
        lambda data: SavedRecord()
    )

    response = client.post(
        "/api/weather/collect?latitude=23&longitude=72"
    )

    assert response.status_code == 201
    assert response.json["data"]["database_record_id"] == 101


# Tests missing coordinates during weather collection.
def test_collect_weather_missing_coordinates(client):
    response = client.post("/api/weather/collect")

    assert response.status_code == 400


# Tests invalid data during weather collection.
def test_collect_weather_value_error(client, monkeypatch):
    def mock_weather(latitude, longitude):
        raise ValueError("Invalid weather data")

    monkeypatch.setattr(
        "app.routes.weather.get_current_weather",
        mock_weather
    )

    response = client.post(
        "/api/weather/collect?latitude=23&longitude=72"
    )

    assert response.status_code == 400


# Tests external API failure during weather collection.
def test_collect_weather_runtime_error(client, monkeypatch):
    def mock_weather(latitude, longitude):
        raise RuntimeError("Weather provider unavailable")

    monkeypatch.setattr(
        "app.routes.weather.get_current_weather",
        mock_weather
    )

    response = client.post(
        "/api/weather/collect?latitude=23&longitude=72"
    )

    assert response.status_code == 502


# Tests successful retrieval of the latest weather record.
def test_latest_weather_success(client, monkeypatch):
    expected = {"temperature": 29, "rainfall": 4}

    monkeypatch.setattr(
        "app.routes.weather.get_latest_weather",
        lambda latitude, longitude: expected
    )

    response = client.get(
        "/api/weather/latest?latitude=23&longitude=72"
    )

    assert response.status_code == 200
    assert response.json["data"] == expected


# Tests missing coordinates when requesting latest weather.
def test_latest_weather_missing_coordinates(client):
    response = client.get("/api/weather/latest")

    assert response.status_code == 400


# Tests when no latest weather record exists.
def test_latest_weather_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.weather.get_latest_weather",
        lambda latitude, longitude: None
    )

    response = client.get(
        "/api/weather/latest?latitude=23&longitude=72"
    )

    assert response.status_code == 404


# Tests unexpected errors when retrieving latest weather.
def test_latest_weather_internal_error(client, monkeypatch):
    def mock_weather(latitude, longitude):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        "app.routes.weather.get_latest_weather",
        mock_weather
    )

    response = client.get(
        "/api/weather/latest?latitude=23&longitude=72"
    )

    assert response.status_code == 500


# Tests successful retrieval of weather history.
def test_weather_history_success(client, monkeypatch):
    expected = [{"temperature": 29}, {"temperature": 30}]

    monkeypatch.setattr(
        "app.routes.weather.get_weather_history",
        lambda latitude, longitude, limit: expected
    )

    response = client.get(
        "/api/weather/history?latitude=23&longitude=72&limit=10"
    )

    assert response.status_code == 200
    assert response.json["count"] == 2
    assert response.json["data"] == expected


# Tests missing coordinates for weather history.
def test_weather_history_missing_coordinates(client):
    response = client.get("/api/weather/history")

    assert response.status_code == 400


# Tests weather history limit below the allowed range.
def test_weather_history_limit_too_low(client):
    response = client.get(
        "/api/weather/history?latitude=23&longitude=72&limit=0"
    )

    assert response.status_code == 400


# Tests weather history limit above the allowed range.
def test_weather_history_limit_too_high(client):
    response = client.get(
        "/api/weather/history?latitude=23&longitude=72&limit=101"
    )

    assert response.status_code == 400


# Tests unexpected errors when retrieving weather history.
def test_weather_history_internal_error(client, monkeypatch):
    def mock_history(latitude, longitude, limit):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        "app.routes.weather.get_weather_history",
        mock_history
    )

    response = client.get(
        "/api/weather/history?latitude=23&longitude=72"
    )

    assert response.status_code == 500


# Tests successful retrieval of weather within a date range.
def test_weather_history_date_range_success(client, monkeypatch):
    expected = [{"temperature": 29}]

    monkeypatch.setattr(
        "app.routes.weather.get_weather_history_by_date",
        lambda latitude, longitude, start_date, end_date: expected
    )

    response = client.get(
        "/api/weather/history/date-range"
        "?latitude=23&longitude=72"
        "&start_date=2026-01-01"
        "&end_date=2026-01-31"
    )

    assert response.status_code == 200
    assert response.json["count"] == 1
    assert response.json["data"] == expected


# Tests missing required date-range parameters.
def test_weather_history_date_range_missing_parameters(client):
    response = client.get(
        "/api/weather/history/date-range"
    )

    assert response.status_code == 400


# Tests invalid ISO date formats.
def test_weather_history_date_range_invalid_date(client):
    response = client.get(
        "/api/weather/history/date-range"
        "?latitude=23&longitude=72"
        "&start_date=invalid"
        "&end_date=2026-01-31"
    )

    assert response.status_code == 400
    assert "Invalid date format" in response.json["message"]


# Tests a date range whose start is after its end.
def test_weather_history_date_range_reversed(client):
    response = client.get(
        "/api/weather/history/date-range"
        "?latitude=23&longitude=72"
        "&start_date=2026-02-01"
        "&end_date=2026-01-01"
    )

    assert response.status_code == 400


# Tests unexpected errors when retrieving date-range weather.
def test_weather_history_date_range_internal_error(client, monkeypatch):
    def mock_history(latitude, longitude, start_date, end_date):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        "app.routes.weather.get_weather_history_by_date",
        mock_history
    )

    response = client.get(
        "/api/weather/history/date-range"
        "?latitude=23&longitude=72"
        "&start_date=2026-01-01"
        "&end_date=2026-01-31"
    )

    assert response.status_code == 500
