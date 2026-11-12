
import pytest

from datetime import datetime, timezone
from flask_jwt_extended import create_access_token

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models.user import User
from app.models.historical_flood_event import HistoricalFloodEvent


@pytest.fixture
def app():
    app = create_app(TestingConfig)

    with app.app_context():
        db.create_all()

        event = HistoricalFloodEvent(
            event_name="Ahmedabad Flood 2023",
            latitude=23.0225,
            longitude=72.5714,
            event_date=datetime(2023, 7, 22, tzinfo=timezone.utc),
            water_depth_cm=45,
            severity="high",
            description="Heavy waterlogging",
            source="Official Dataset",
            source_reference="TEST-2023",
        )

        admin = User(
            name="Historical Admin",
            email="historical_admin@example.com",
            role="admin",
        )

        citizen = User(
            name="Historical Citizen",
            email="historical_citizen@example.com",
            role="citizen",
        )

        db.session.add_all([event, admin, citizen])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def tokens(app):
    with app.app_context():
        admin = User.query.filter_by(
            email="historical_admin@example.com"
        ).first()

        citizen = User.query.filter_by(
            email="historical_citizen@example.com"
        ).first()

        return {
            "admin": create_access_token(identity=str(admin.id)),
            "citizen": create_access_token(identity=str(citizen.id)),
        }


def test_get_historical_floods_success(client):
    response = client.get("/api/historical-floods")

    assert response.status_code == 200
    assert response.json["status"] == "success"
    assert response.json["total"] == 1
    assert len(response.json["events"]) == 1
    assert response.json["events"][0]["event_name"] == "Ahmedabad Flood 2023"


def test_get_historical_floods_with_severity_filter(client):
    response = client.get(
        "/api/historical-floods?severity=high"
    )

    assert response.status_code == 200
    assert response.json["total"] == 1


def test_get_historical_floods_with_date_filters(client):
    response = client.get(
        "/api/historical-floods"
        "?start_date=2023-01-01&end_date=2023-12-31"
    )

    assert response.status_code == 200
    assert response.json["total"] == 1


def test_get_historical_floods_with_location_filters(client):
    response = client.get(
        "/api/historical-floods"
        "?latitude=23.0225&longitude=72.5714&radius_km=5"
    )

    assert response.status_code == 200
    assert response.json["total"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "?page=0",
        "?per_page=0",
        "?per_page=101",
    ],
)
def test_get_historical_floods_rejects_invalid_pagination(
    client,
    query,
):
    response = client.get("/api/historical-floods" + query)

    assert response.status_code == 400
    assert response.json["status"] == "error"


def test_get_historical_floods_rejects_invalid_severity(client):
    response = client.get(
        "/api/historical-floods?severity=extreme"
    )

    assert response.status_code == 400


def test_get_historical_floods_rejects_invalid_date(client):
    response = client.get(
        "/api/historical-floods?start_date=not-a-date"
    )

    assert response.status_code == 400


def test_get_historical_floods_rejects_invalid_coordinates(client):
    response = client.get(
        "/api/historical-floods"
        "?latitude=200&longitude=72.5714&radius_km=5"
    )

    assert response.status_code == 400


def test_get_historical_floods_handles_service_exception(
    client,
    monkeypatch,
):
    def raise_error(**kwargs):
        raise RuntimeError("Database failure")

    monkeypatch.setattr(
        "app.routes.historical_floods.get_all_historical_flood_events",
        raise_error,
    )

    response = client.get("/api/historical-floods")

    assert response.status_code == 500
    assert response.json["status"] == "error"


def test_get_historical_flood_details_success(client):
    response = client.get("/api/historical-floods/1")

    assert response.status_code == 200
    assert response.json["status"] == "success"
    assert response.json["event"]["event_name"] == "Ahmedabad Flood 2023"


def test_get_historical_flood_details_not_found(client):
    response = client.get("/api/historical-floods/999")

    assert response.status_code == 404
    assert response.json["status"] == "error"


def test_create_historical_flood_requires_authentication(client):
    response = client.post(
        "/api/historical-floods",
        json={},
    )

    assert response.status_code == 401


def test_citizen_cannot_create_historical_flood(client, tokens):
    response = client.post(
        "/api/historical-floods",
        json={},
        headers={
            "Authorization": f"Bearer {tokens['citizen']}"
        },
    )

    assert response.status_code == 403


def test_admin_can_create_historical_flood(client, tokens):
    response = client.post(
        "/api/historical-floods",
        json={
            "event_name": "New Historical Flood",
            "latitude": 23.03,
            "longitude": 72.58,
            "event_date": "2024-07-20T10:00:00+00:00",
            "water_depth_cm": 30,
            "severity": "moderate",
            "description": "Historical waterlogging event",
            "source": "Test Dataset",
            "source_reference": "TEST-2024",
        },
        headers={
            "Authorization": f"Bearer {tokens['admin']}"
        },
    )

    assert response.status_code == 201
    assert response.json["status"] == "success"


def test_create_historical_flood_rejects_invalid_json(client, tokens):
    response = client.post(
        "/api/historical-floods",
        data="not-json",
        content_type="application/json",
        headers={
            "Authorization": f"Bearer {tokens['admin']}"
        },
    )

    assert response.status_code == 400


def test_create_historical_flood_rejects_invalid_data(client, tokens):
    response = client.post(
        "/api/historical-floods",
        json={
            "event_name": "Invalid Event",
            "latitude": 200,
            "longitude": 72.58,
            "event_date": "2024-07-20T10:00:00+00:00",
            "source": "Test Dataset",
        },
        headers={
            "Authorization": f"Bearer {tokens['admin']}"
        },
    )

    assert response.status_code == 400


def test_create_historical_flood_handles_service_exception(
    client,
    tokens,
    monkeypatch,
):
    def raise_error(**kwargs):
        raise RuntimeError("Database failure")

    monkeypatch.setattr(
        "app.routes.historical_floods.create_historical_flood_event",
        raise_error,
    )

    response = client.post(
        "/api/historical-floods",
        json={
            "event_name": "Test Event",
            "latitude": 23.03,
            "longitude": 72.58,
            "event_date": "2024-07-20T10:00:00+00:00",
            "source": "Test Dataset",
        },
        headers={
            "Authorization": f"Bearer {tokens['admin']}"
        },
    )

    assert response.status_code == 500
    assert response.json["status"] == "error"
