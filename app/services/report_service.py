import math

from sqlalchemy import or_

from app.extensions import db
from app.models.flood_report import FloodReport
from app.models.moderation_history import ModerationHistory
from app.utils.geo import calculate_distance_km


# Create and persist a new flood report.
def create_flood_report(
    user_id,
    latitude,
    longitude,
    water_depth_cm=None,
    description=None
):
    # Create a new flood report object
    report = FloodReport(
        user_id=user_id,
        latitude=latitude,
        longitude=longitude,
        water_depth_cm=water_depth_cm,
        description=description,
        status="pending"
    )

    # Save the report to the database
    try:
        db.session.add(report)
        db.session.commit()

        return report

    except Exception:
        db.session.rollback()
        raise

# Retrieve flood reports with visibility, date, location, and pagination filters.
def get_all_flood_reports(
    status=None,
    latitude=None,
    longitude=None,
    radius_km=None,
    page=1,
    per_page=20,
    created_after=None,
    created_before=None,
    visible_to_user_id=None,
    include_all=False
):
    query = FloodReport.query

    # Restrict citizens to their own reports and publicly visible verified reports.
    if not include_all:
        if visible_to_user_id is None:
            raise ValueError("A user ID is required to retrieve visible reports")

        query = query.filter(
            or_(
                FloodReport.user_id == visible_to_user_id,
                FloodReport.status == "verified"
            )
        )
    # Filter reports by creation date.
    if created_after is not None:
       query = query.filter(FloodReport.created_at >= created_after)

    if created_before is not None:
       query = query.filter(FloodReport.created_at < created_before)

    # Apply status filter.
    if status:
        query = query.filter_by(status=status)

    # Sort newest reports first, using report ID as a stable tie-breaker.
    query = query.order_by(
        FloodReport.created_at.desc(),
        FloodReport.id.desc()
    )
    # Check whether location filtering is requested.
    location_filter = (
        latitude is not None
        and longitude is not None
        and radius_km is not None
    )
    if location_filter:
        # Calculate a conservative geographic bounding box.
        earth_radius_km = 6371.0
        angular_radius = radius_km / earth_radius_km

        center_lat = math.radians(latitude)
        center_lon = math.radians(longitude)

        min_lat = max(
            -math.pi / 2,
            center_lat - angular_radius
        )
        max_lat = min(
            math.pi / 2,
            center_lat + angular_radius
        )

        # Filter latitude in the database first.
        query = query.filter(
            FloodReport.latitude >= math.degrees(min_lat),
            FloodReport.latitude <= math.degrees(max_lat)
        )

        # Apply longitude filtering unless the bounding box reaches a pole.
        if min_lat > -math.pi / 2 and max_lat < math.pi / 2:
            max_lon_delta = math.asin(
                min(
                    1.0,
                    math.sin(angular_radius) / math.cos(center_lat)
                )
            )

            min_lon = center_lon - max_lon_delta
            max_lon = center_lon + max_lon_delta

            # Handle bounding boxes crossing the International Date Line.
            if min_lon < -math.pi:
                query = query.filter(
                    or_(
                        FloodReport.longitude >= math.degrees(
                            min_lon + 2 * math.pi
                        ),
                        FloodReport.longitude <= math.degrees(max_lon)
                    )
                )

            elif max_lon > math.pi:
                query = query.filter(
                    or_(
                        FloodReport.longitude >= math.degrees(min_lon),
                        FloodReport.longitude <= math.degrees(
                            max_lon - 2 * math.pi
                        )
                    )
                )

            else:
                query = query.filter(
                    FloodReport.longitude >= math.degrees(min_lon),
                    FloodReport.longitude <= math.degrees(max_lon)
                )

        # Load only reports inside the geographic bounding box.
        all_reports = query.all()
        # Calculate geographic distance for each report.
        filtered_reports = []

        for report in all_reports:
            distance = calculate_distance_km(
                latitude,
                longitude,
                report.latitude,
                report.longitude
            )

            if distance <= radius_km:
                filtered_reports.append((report, distance))

        total = len(filtered_reports)

        # Apply pagination after geographic filtering.
        start = (page - 1) * per_page
        end = start + per_page
        selected_reports = filtered_reports[start:end]

        report_data = [
            {
                "report_id": report.id,
                "user_id": report.user_id,
                "latitude": report.latitude,
                "longitude": report.longitude,
                "water_depth_cm": report.water_depth_cm,
                "description": report.description,
                "status": report.status,
                "distance_km": round(distance, 3),
                "created_at": report.created_at.isoformat()
            }
            for report, distance in selected_reports
        ]

    else:
        # Count reports before applying pagination.
        total = query.count()

        # Retrieve only the requested database page.
        selected_reports = (
            query
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        report_data = [
            {
                "report_id": report.id,
                "user_id": report.user_id,
                "latitude": report.latitude,
                "longitude": report.longitude,
                "water_depth_cm": report.water_depth_cm,
                "description": report.description,
                "status": report.status,
                "created_at": report.created_at.isoformat()
            }
            for report in selected_reports
        ]

    return {
        "reports": report_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_reports": total,
            "total_pages": (total + per_page - 1) // per_page
        }
    }

#this is used to get specific flood report by id
def get_flood_report_by_id(report_id):


    # Search for a report using its primary key
    report = FloodReport.query.filter_by(id=report_id).first()

    # Return None if the report does not exist
    if report is None:
        return None

    # Convert the database object into a dictionary
    return {
        "report_id": report.id,
        "user_id": report.user_id,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "water_depth_cm": report.water_depth_cm,
        "description": report.description,
        "status": report.status,
        "created_at": report.created_at.isoformat()
    }


"""
Updates a flood report's status and records the administrator's action.
Allowed statuses: pending, verified, rejected.
"""
def update_report_status(report_id, new_status, admin_id):

    allowed_statuses = {"pending", "verified", "rejected"}

    if new_status not in allowed_statuses:
        raise ValueError(
            "Status must be pending, verified or rejected"
        )

    report = db.session.get(FloodReport, report_id)

    if report is None:
        return None

    previous_status = report.status

    # Avoid creating duplicate history when the status is unchanged.
    if previous_status == new_status:
        return report

    try:
        # Update the report's current status.
        report.status = new_status

        # Create a history record for this administrator decision.
        history = ModerationHistory(
            report_id=report.id,
            admin_id=admin_id,
            previous_status=previous_status,
            new_status=new_status
        )

        db.session.add(history)

        # Save both changes together.
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return report