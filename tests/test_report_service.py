
import pytest

from datetime import datetime, timedelta, timezone

from app import create_app
from app.config import TestingConfig
from app.extensions import db

from app.models.user import User
from app.models.flood_report import FloodReport
from app.models.moderation_history import ModerationHistory

from app.services.report_service import (
    create_flood_report,
    get_all_flood_reports,
    get_flood_report_by_id,
    update_report_status,
)


@pytest.fixture
def app():
    app = create_app(TestingConfig)

    with app.app_context():
        db.create_all()

        admin = User(
            name="Report Admin",
            email="report_admin@example.com",
            role="admin",
        )

        citizen = User(
            name="Report Citizen",
            email="report_citizen@example.com",
            role="citizen",
        )

        db.session.add_all([admin, citizen])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def users(app):
    with app.app_context():
        admin = User.query.filter_by(
            email="report_admin@example.com"
        ).first()

        citizen = User.query.filter_by(
            email="report_citizen@example.com"
        ).first()

        return {
            "admin_id": admin.id,
            "citizen_id": citizen.id,
        }


def add_report(user_id, status="pending", latitude=23.0225,
               longitude=72.5714, created_at=None):
    report = FloodReport(
        user_id=user_id,
        latitude=latitude,
        longitude=longitude,
        water_depth_cm=25,
        description="Test flood report",
        status=status,
    )

    if created_at is not None:
        report.created_at = created_at

    db.session.add(report)
    db.session.commit()

    return report


# Verify that a flood report is created successfully.
def test_create_flood_report(app, users):
    with app.app_context():
        report = create_flood_report(
            user_id=users["citizen_id"],
            latitude=23.0225,
            longitude=72.5714,
            water_depth_cm=25,
            description="Waterlogging near a road",
        )

        assert report.id is not None
        assert report.status == "pending"
        assert report.water_depth_cm == 25


# Verify that database failures roll back report creation.
def test_create_flood_report_rolls_back_on_failure(
    app, users, monkeypatch
):
    with app.app_context():
        def fail_commit():
            raise RuntimeError("Simulated commit failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)

        with pytest.raises(RuntimeError):
            create_flood_report(
                user_id=users["citizen_id"],
                latitude=23.0225,
                longitude=72.5714,
            )

        assert FloodReport.query.count() == 0


# Verify that citizens receive their own reports and verified reports.
def test_get_all_flood_reports_visibility(app, users):
    with app.app_context():
        add_report(users["citizen_id"], "pending")
        add_report(users["admin_id"], "pending")
        add_report(users["admin_id"], "verified")

        result = get_all_flood_reports(
            visible_to_user_id=users["citizen_id"]
        )

        assert len(result["reports"]) == 2
        assert all(
            report["status"] in ("pending", "verified")
            for report in result["reports"]
        )


# Verify that retrieving citizen-visible reports requires a user ID.
def test_get_all_flood_reports_requires_user_id(app):
    with app.app_context():
        with pytest.raises(ValueError):
            get_all_flood_reports()


# Verify that administrators can retrieve all reports.
def test_get_all_flood_reports_include_all(app, users):
    with app.app_context():
        add_report(users["citizen_id"], "pending")
        add_report(users["admin_id"], "rejected")

        result = get_all_flood_reports(include_all=True)

        assert len(result["reports"]) == 2


# Verify status filtering.
def test_get_all_flood_reports_status_filter(app, users):
    with app.app_context():
        add_report(users["citizen_id"], "pending")
        add_report(users["citizen_id"], "verified")

        result = get_all_flood_reports(
            status="verified",
            visible_to_user_id=users["citizen_id"],
        )

        assert len(result["reports"]) == 1
        assert result["reports"][0]["status"] == "verified"


# Verify date filtering.
def test_get_all_flood_reports_date_filters(app, users):
    with app.app_context():
        now = datetime.now(timezone.utc)

        add_report(
            users["citizen_id"],
            created_at=now - timedelta(days=3),
        )
        add_report(
            users["citizen_id"],
            created_at=now - timedelta(days=1),
        )

        result = get_all_flood_reports(
            visible_to_user_id=users["citizen_id"],
            created_after=now - timedelta(days=2),
            created_before=now,
        )

        assert len(result["reports"]) == 1


# Verify pagination and total-page calculation.
def test_get_all_flood_reports_pagination(app, users):
    with app.app_context():
        for _ in range(5):
            add_report(users["citizen_id"])

        result = get_all_flood_reports(
            visible_to_user_id=users["citizen_id"],
            page=1,
            per_page=2,
        )

        assert len(result["reports"]) == 2
        assert result["pagination"]["total_reports"] == 5
        assert result["pagination"]["total_pages"] == 3


# Verify that location filtering returns reports within the radius.
def test_get_all_flood_reports_location_filter(app, users):
    with app.app_context():
        add_report(
            users["citizen_id"],
            latitude=23.0225,
            longitude=72.5714,
        )

        add_report(
            users["citizen_id"],
            latitude=28.6139,
            longitude=77.2090,
        )

        result = get_all_flood_reports(
            visible_to_user_id=users["citizen_id"],
            latitude=23.0225,
            longitude=72.5714,
            radius_km=5,
        )

        assert len(result["reports"]) == 1
        assert "distance_km" in result["reports"][0]


# Verify pagination after location filtering.
def test_get_all_flood_reports_location_pagination(app, users):
    with app.app_context():
        for _ in range(3):
            add_report(users["citizen_id"])

        result = get_all_flood_reports(
            visible_to_user_id=users["citizen_id"],
            latitude=23.0225,
            longitude=72.5714,
            radius_km=5,
            page=2,
            per_page=1,
        )

        assert len(result["reports"]) == 1
        assert result["pagination"]["total_reports"] == 3

# Verify location filtering across the International Date Line.
def test_get_all_flood_reports_location_antimeridian(app, users):
    with app.app_context():
        add_report(
            users["citizen_id"],
            latitude=0.0,
            longitude=-179.9,
        )

        add_report(
            users["citizen_id"],
            latitude=0.0,
            longitude=179.0,
        )

        result = get_all_flood_reports(
            visible_to_user_id=users["citizen_id"],
            latitude=0.0,
            longitude=179.9,
            radius_km=30,
        )

        assert len(result["reports"]) == 1
        assert result["pagination"]["total_reports"] == 1
        assert result["reports"][0]["longitude"] == -179.9


# Verify location filtering close to the North Pole.
def test_get_all_flood_reports_location_near_pole(app, users):
    with app.app_context():
        add_report(
            users["citizen_id"],
            latitude=89.9,
            longitude=90.0,
        )

        add_report(
            users["citizen_id"],
            latitude=89.9,
            longitude=180.0,
        )

        result = get_all_flood_reports(
            visible_to_user_id=users["citizen_id"],
            latitude=89.9,
            longitude=0.0,
            radius_km=20,
        )

        assert len(result["reports"]) == 1
        assert result["pagination"]["total_reports"] == 1
        assert result["reports"][0]["longitude"] == 90.0
# Verify that an individual report can be retrieved.
def test_get_flood_report_by_id(app, users):
    with app.app_context():
        report = add_report(users["citizen_id"])

        result = get_flood_report_by_id(report.id)

        assert result is not None
        assert result["report_id"] == report.id
        assert result["status"] == "pending"


# Verify that a missing report returns None.
def test_get_flood_report_by_id_not_found(app):
    with app.app_context():
        assert get_flood_report_by_id(99999) is None


# Verify that an administrator can update report status.
def test_update_report_status(app, users):
    with app.app_context():
        report = add_report(users["citizen_id"], "pending")

        updated_report = update_report_status(
            report.id,
            "verified",
            users["admin_id"],
        )

        assert updated_report.status == "verified"

        history = ModerationHistory.query.filter_by(
            report_id=report.id
        ).first()

        assert history is not None
        assert history.previous_status == "pending"
        assert history.new_status == "verified"


# Verify that invalid report statuses are rejected.
@pytest.mark.parametrize(
    "invalid_status",
    ["invalid", "", "approved", "deleted"],
)
def test_update_report_status_invalid(app, users, invalid_status):
    with app.app_context():
        report = add_report(users["citizen_id"])

        with pytest.raises(ValueError):
            update_report_status(
                report.id,
                invalid_status,
                users["admin_id"],
            )


# Verify that updating a missing report returns None.
def test_update_report_status_not_found(app, users):
    with app.app_context():
        result = update_report_status(
            99999,
            "verified",
            users["admin_id"],
        )

        assert result is None


# Verify that unchanged status does not create duplicate history.
def test_update_report_status_unchanged(app, users):
    with app.app_context():
        report = add_report(users["citizen_id"], "pending")

        result = update_report_status(
            report.id,
            "pending",
            users["admin_id"],
        )

        assert result.status == "pending"
        assert ModerationHistory.query.count() == 0


# Verify that failed moderation commits roll back.
def test_update_report_status_rolls_back_on_failure(
    app, users, monkeypatch
):
    with app.app_context():
        report = add_report(users["citizen_id"], "pending")

        def fail_commit():
            raise RuntimeError("Simulated moderation failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)

        with pytest.raises(RuntimeError):
            update_report_status(
                report.id,
                "verified",
                users["admin_id"],
            )

        db.session.expire_all()

        saved_report = db.session.get(FloodReport, report.id)

        assert saved_report.status == "pending"
        assert ModerationHistory.query.count() == 0
