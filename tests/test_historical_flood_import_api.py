import io

import pytest
from flask_jwt_extended import create_access_token
from io import BytesIO
from pathlib import Path
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
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_tokens(app):
    with app.app_context():
        admin = User(
            name="Import Administrator",
            email="import_admin@example.com",
            role="admin",
        )

        citizen = User(
            name="Import Citizen",
            email="import_citizen@example.com",
            role="citizen",
        )

        admin.set_password("AdminPassword123")
        citizen.set_password("CitizenPassword123")

        db.session.add_all([admin, citizen])
        db.session.commit()

        return {
            "admin": create_access_token(identity=str(admin.id)),
            "citizen": create_access_token(identity=str(citizen.id)),
        }


def test_import_csv_requires_authentication(client):
    response = client.post(
        "/api/admin/historical-floods/import"
    )

    assert response.status_code == 401


def test_citizen_cannot_import_csv(client, user_tokens):
    response = client.post(
        "/api/admin/historical-floods/import",
        headers={
            "Authorization": f"Bearer {user_tokens['citizen']}"
        },
    )

    assert response.status_code == 403


def test_admin_can_import_csv(client, app, user_tokens):
    csv_content = (
        "event_name,latitude,longitude,event_date,"
        "water_depth_cm,severity,description,source\n"
        "Ahmedabad Flood Test,23.0225,72.5714,"
        "2023-07-20T10:30:00+00:00,45,high,"
        "Heavy waterlogging,Test Dataset\n"
    )

    response = client.post(
        "/api/admin/historical-floods/import",
        data={
            "file": (
                io.BytesIO(csv_content.encode("utf-8")),
                "historical_floods.csv",
            )
        },
        headers={
            "Authorization": f"Bearer {user_tokens['admin']}"
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.json["result"]["imported_count"] == 1
    assert response.json["result"]["failed_count"] == 0

    with app.app_context():
        assert HistoricalFloodEvent.query.count() == 1


def test_import_rejects_non_csv_file(client, user_tokens):
    response = client.post(
        "/api/admin/historical-floods/import",
        data={
            "file": (
                io.BytesIO(b"This is not a CSV"),
                "document.txt",
            )
        },
        headers={
            "Authorization": f"Bearer {user_tokens['admin']}"
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400

# Tests that an administrator cannot import without uploading a file.
def test_import_historical_floods_without_file(client, user_tokens):
    response = client.post(
        "/api/admin/historical-floods/import",
        headers={
            "Authorization": f"Bearer {user_tokens['admin']}"
        },
    )

    assert response.status_code == 400
    assert response.json["status"] == "error"


# Tests that CSV import validation errors return HTTP 400.
def test_import_historical_floods_value_error(
    app, client, user_tokens, monkeypatch
):
    def mock_import(file_path):
        raise ValueError("Invalid CSV content")

    monkeypatch.setattr(
        "app.routes.historical_floods.import_historical_flood_csv",
        mock_import,
    )

    response = client.post(
        "/api/admin/historical-floods/import",
        headers={
            "Authorization": f"Bearer {user_tokens['admin']}"
        },
        data={
            "file": (BytesIO(b"invalid,csv"), "invalid.csv")
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.json["message"] == "Invalid CSV content"

    upload_directory = (
        Path(app.instance_path)
        / "uploads"
        / "historical_floods"
    )

    assert not (upload_directory / "invalid.csv").exists()


# Tests that unexpected import errors return HTTP 500 and remove the temporary file.
def test_import_historical_floods_unexpected_error(
    app, client, user_tokens, monkeypatch
):
    def mock_import(file_path):
        raise RuntimeError("Database failure")

    monkeypatch.setattr(
        "app.routes.historical_floods.import_historical_flood_csv",
        mock_import,
    )

    response = client.post(
        "/api/admin/historical-floods/import",
        headers={
            "Authorization": f"Bearer {user_tokens['admin']}"
        },
        data={
            "file": (BytesIO(b"valid,csv"), "temporary.csv")
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    assert response.json["status"] == "error"

    upload_directory = (
        Path(app.instance_path)
        / "uploads"
        / "historical_floods"
    )

    assert not (upload_directory / "temporary.csv").exists()
