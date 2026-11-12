"""tests that it 
Uploads valid photograph.
Rejects unsupported file.
Retrieves photograph metadata.
Retrieves actual image.
Deletes photograph."""
import io ,os,pytest
from PIL import Image
from app.extensions import db
from app.models.user import User
from app.models.flood_report import FloodReport
from app.models.report_media import FloodReportMedia
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage
from app.services.media_service import (
    validate_image_file,
    save_report_media,
    delete_report_media,
)
# Generates a real, valid PNG image in memory for automated upload tests.
def create_test_png():
    image_buffer = io.BytesIO()

    image = Image.new("RGB", (10, 10), color="blue")
    image.save(image_buffer, format="PNG")

    image_buffer.seek(0)
    return image_buffer
# Tests whether the API returns the photographs attached to a flood report.

# Creates a test citizen and a flood report for photograph-upload tests.
@pytest.fixture()
def test_report(app):
    with app.app_context():
        user = User(
            name="Media Test User",
            email="media-test@example.com"
        )

        user.set_password("TestPassword123")

        db.session.add(user)
        db.session.flush()

        report = FloodReport(
            user_id=user.id,
            latitude=23.0225,
            longitude=72.5714,
            water_depth_cm=25,
            description="Test waterlogging report",
            status="pending"
        )

        db.session.add(report)
        db.session.commit()

        return report.id
def test_get_report_photos(auth_client, app, test_report):
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

    upload_response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                 create_test_png(),
                "waterlogging.png"
             )
        },
        content_type="multipart/form-data"
    )

    assert upload_response.status_code == 201

    response = auth_client.get(
        f"/api/reports/{test_report}/media"
    )

    assert response.status_code == 200

    response_data = response.get_json()

    assert response_data["count"] == 1
    assert "original_filename" not in response_data["data"][0]
    assert "file_path" not in response_data["data"][0]
    assert response_data["data"][0]["mime_type"] == "image/png"
    assert "image_url" in response_data["data"][0]
# Tests whether the image endpoint returns the actual stored image bytes.
# Tests whether the image endpoint returns the exact uploaded image bytes.
def test_view_report_photo(auth_client, test_report):
    image_file = create_test_png()

    # Save the original generated PNG bytes before uploading.
    expected_image_bytes = image_file.getvalue()

    upload_response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                image_file,
                "waterlogging.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert upload_response.status_code == 201

    media_id = upload_response.get_json()["data"][0]["media_id"]

    # Request the actual photograph from the backend.
    response = auth_client.get(
        f"/api/reports/{test_report}/media/{media_id}"
    )

    assert response.status_code == 200

    # Compare the returned image against the original uploaded PNG.
    assert response.data == expected_image_bytes

    assert response.mimetype == "image/png"
# Tests whether deleting a photograph removes its database record and physical file.
def test_delete_report_photo(auth_client, app, test_report):
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

    upload_response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                 create_test_png(),
                "waterlogging.png"
             )
        },
        content_type="multipart/form-data"
    )

    assert upload_response.status_code == 201

    media_id = upload_response.get_json()["data"][0]["media_id"]

    with app.app_context():
        media = db.session.get(FloodReportMedia, media_id)
        saved_file = os.path.join(
            app.instance_path,
            media.file_path
        )

        assert os.path.exists(saved_file)

    # Send the DELETE request to remove the photograph.
    response = auth_client.delete(
        f"/api/reports/{test_report}/media/{media_id}"
    )

    assert response.status_code == 200

    with app.app_context():
        deleted_media = db.session.get(
            FloodReportMedia,
            media_id
        )

        assert deleted_media is None
        assert not os.path.exists(saved_file)

# Tests whether an image with a fake PNG extension is rejected.
def test_reject_fake_png(auth_client, test_report):
    fake_image = io.BytesIO(b"This is not a real PNG image")

    response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                fake_image,
                "fake.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


# Tests whether an image larger than the allowed 5 MB is rejected.
def test_reject_oversized_image(auth_client, test_report):
    oversized_image = io.BytesIO(b"A" * (5 * 1024 * 1024 + 1))

    response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                oversized_image,
                "large.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"

# Verifies that a citizen cannot upload photos to another citizen's report.
def test_other_user_cannot_upload_photo(app, test_report):

    # Step 1: Create a second citizen.
    with app.app_context():
        other_user = User(
            name="Second Test User",
            email="second_test@example.com"
        )
        other_user.set_password("TestPassword123")

        db.session.add(other_user)
        db.session.commit()

        other_user_id = other_user.id

        # Step 2: Generate a JWT for the second citizen.
        token = create_access_token(
            identity=str(other_user_id)
        )

    # Step 3: Create a separate authenticated test client.
    client = app.test_client()

    # Step 4: Generate a valid image.
    image_file = create_test_png()

    # Step 5: Attempt to upload to the first citizen's report.
    response = client.post(
        f"/api/reports/{test_report}/media",
        headers={
            "Authorization": f"Bearer {token}"
        },
        data={
            "photos": (
                image_file,
                "unauthorized_photo.png"
            )
        },
        content_type="multipart/form-data"
    )

    # Step 6: Verify that the backend rejects the upload.
    assert response.status_code == 403   


# Verifies that a citizen cannot delete a photo attached to another citizen's report.
def test_other_user_cannot_delete_photo(app, test_report):

    # Step 1: Retrieve the report owner's ID and create another citizen.
    with app.app_context():
        report = db.session.get(FloodReport, test_report)
        owner_id = report.user_id

        other_user = User(
            name="Second Test User",
            email="second_test@example.com"
        )
        other_user.set_password("TestPassword123")

        db.session.add(other_user)
        db.session.commit()

        other_user_id = other_user.id

        # Generate separate JWT tokens for both citizens.
        owner_token = create_access_token(
            identity=str(owner_id)
        )

        other_user_token = create_access_token(
            identity=str(other_user_id)
        )

    # Step 2: Create a test client.
    client = app.test_client()

    # Step 3: Upload a photograph using the report owner's token.
    image_file = create_test_png()

    owner_response = client.post(
        f"/api/reports/{test_report}/media",
        headers={
            "Authorization": f"Bearer {owner_token}"
        },
        data={
            "photos": (
                image_file,
                "owner_photo.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert owner_response.status_code == 201

    # Step 4: Retrieve the uploaded photograph's ID.
    media_id = owner_response.get_json()["data"][0]["media_id"]

    # Step 5: Attempt deletion using the second citizen's token.
    response = client.delete(
        f"/api/reports/{test_report}/media/{media_id}",
        headers={
            "Authorization": f"Bearer {other_user_token}"
        }
    )

    # Step 6: Verify that the API rejects the unauthorized deletion.
    assert response.status_code == 403

    # Step 7: Verify that the photograph still exists in the database.
    with app.app_context():
        media = db.session.get(FloodReportMedia, media_id)

        assert media is not None


# Verifies that uploading photographs to a nonexistent report returns 404.
def test_upload_photo_to_missing_report(auth_client):

    response = auth_client.post(
        "/api/reports/99999/media",
        data={
            "photos": (
                create_test_png(),
                "missing_report.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert response.status_code == 404

    response_data = response.get_json()

    assert response_data["status"] == "error"
    assert response_data["message"] == "Flood report not found"


# Verifies that a report cannot contain more than three photographs.
def test_reject_more_than_three_photos_per_report(
    auth_client,
    app,
    test_report
):

    # Upload the maximum permitted three photographs.
    upload_response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": [
                (create_test_png(), "photo1.png"),
                (create_test_png(), "photo2.png"),
                (create_test_png(), "photo3.png")
            ]
        },
        content_type="multipart/form-data"
    )

    assert upload_response.status_code == 201
    assert upload_response.get_json()["count"] == 3

    # Attempt to upload one additional photograph.
    extra_response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                create_test_png(),
                "photo4.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert extra_response.status_code == 400

    response_data = extra_response.get_json()

    assert response_data["status"] == "error"
    assert response_data["message"] == (
        "A flood report can have a maximum of 3 photographs"
    )

    # Confirm that the report still has exactly three photographs.
    with app.app_context():
        photo_count = FloodReportMedia.query.filter_by(
            report_id=test_report
        ).count()

        assert photo_count == 3

# Verifies that the original photograph is restored if database deletion fails.
def test_delete_photo_restores_file_when_database_commit_fails(
    auth_client,
    app,
    test_report,
    monkeypatch
):
    # Upload a photograph.
    upload_response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                create_test_png(),
                "recovery_test.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert upload_response.status_code == 201

    media_id = upload_response.get_json()["data"][0]["media_id"]

    # Locate the uploaded physical image.
    with app.app_context():
        media = db.session.get(FloodReportMedia, media_id)

        original_path = os.path.join(
            app.instance_path,
            media.file_path
        )

        assert os.path.exists(original_path)

    # Simulate a database commit failure.
    def simulate_commit_failure():
        raise RuntimeError("Simulated database commit failure")

    monkeypatch.setattr(
        db.session,
        "commit",
        simulate_commit_failure
    )

    # Attempt to delete the photograph.
    response = auth_client.delete(
        f"/api/reports/{test_report}/media/{media_id}"
    )

    assert response.status_code == 500

    # Verify that the original image has been restored.
    assert os.path.exists(original_path)

    # Verify that the database record still exists.
    with app.app_context():
        media = db.session.get(FloodReportMedia, media_id)

        assert media is not None
# Creates an authenticated client for a second citizen.
@pytest.fixture()
def second_citizen_client(app):
    with app.app_context():
        user = User(
            name="Second Media Citizen",
            email="second_media_citizen@example.com"
        )

        user.set_password("TestPassword123")

        db.session.add(user)
        db.session.commit()

        token = create_access_token(
            identity=str(user.id)
        )

    client = app.test_client()
    client.environ_base["HTTP_AUTHORIZATION"] = (
        f"Bearer {token}"
    )

    return client

# Uploads a photograph using a token belonging to the actual report owner.
@pytest.fixture()
def uploaded_report_media(app, test_report):

    # Step 1: Retrieve the actual report owner's ID.
    with app.app_context():
        report = db.session.get(FloodReport, test_report)
        owner_id = report.user_id

        # Step 2: Generate a JWT for the report owner.
        token = create_access_token(
            identity=str(owner_id)
        )

    # Step 3: Create an authenticated client for the owner.
    owner_client = app.test_client()

    owner_client.environ_base["HTTP_AUTHORIZATION"] = (
        f"Bearer {token}"
    )

    # Step 4: Upload a photograph using the owner's identity.
    response = owner_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                create_test_png(),
                "permission_test.png"
            )
        },
        content_type="multipart/form-data"
    )

    assert response.status_code == 201

    return response.get_json()["data"][0]["media_id"]
# Verifies that another citizen cannot view pending report photographs.
def test_other_citizen_cannot_view_pending_report_photos(
    second_citizen_client,
    test_report,
    uploaded_report_media
):
    # Check photograph metadata.
    metadata_response = second_citizen_client.get(
        f"/api/reports/{test_report}/media"
    )

    assert metadata_response.status_code == 403

    # Check access to the actual image.
    image_response = second_citizen_client.get(
        f"/api/reports/{test_report}/media/{uploaded_report_media}"
    )

    assert image_response.status_code == 403


# Verifies that another citizen can view verified report photographs.
def test_other_citizen_can_view_verified_report_photos(
    app,
    second_citizen_client,
    test_report,
    uploaded_report_media
):
    # Mark the report as verified.
    with app.app_context():
        report = db.session.get(FloodReport, test_report)
        report.status = "verified"
        db.session.commit()

    # Check photograph metadata.
    metadata_response = second_citizen_client.get(
        f"/api/reports/{test_report}/media"
    )

    assert metadata_response.status_code == 200

    # Check access to the actual image.
    image_response = second_citizen_client.get(
        f"/api/reports/{test_report}/media/{uploaded_report_media}"
    )

    assert image_response.status_code == 200
    assert image_response.mimetype == "image/png"


# Verifies that another citizen cannot view rejected report photographs.
def test_other_citizen_cannot_view_rejected_report_photos(
    app,
    second_citizen_client,
    test_report,
    uploaded_report_media
):
    # Mark the report as rejected.
    with app.app_context():
        report = db.session.get(FloodReport, test_report)
        report.status = "rejected"
        db.session.commit()

    # Check photograph metadata.
    metadata_response = second_citizen_client.get(
        f"/api/reports/{test_report}/media"
    )

    assert metadata_response.status_code == 403

    # Check access to the actual image.
    image_response = second_citizen_client.get(
        f"/api/reports/{test_report}/media/{uploaded_report_media}"
    )

    assert image_response.status_code == 403

# Verifies that a missing photograph file returns a JSON 404 response.
def test_view_missing_photo_file_returns_404(
    auth_client,
    app,
    test_report,
    uploaded_report_media
):
    with app.app_context():
        media = db.session.get(
            FloodReportMedia,
            uploaded_report_media
        )

        assert media is not None

        filename = os.path.basename(media.file_path)

        upload_directory = os.path.join(
            app.instance_path,
            "uploads",
            "reports"
        )

        image_path = os.path.join(
            upload_directory,
            filename
        )

        # Simulate a photograph missing from physical storage.
        if os.path.exists(image_path):
            os.remove(image_path)

    response = auth_client.get(
        f"/api/reports/{test_report}/media/{uploaded_report_media}"
    )

    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["message"] == (
        "Photograph file is missing from storage"
    )

# Verifies that the database rejects photographs larger than 5 MB.
def test_database_rejects_oversized_media_record(
    app,
    test_report,
    uploaded_report_media
):
    with app.app_context():
        media = db.session.get(
            FloodReportMedia,
            uploaded_report_media
        )

        media.file_size_bytes = 6 * 1024 * 1024

        with pytest.raises(IntegrityError):
            db.session.commit()

        db.session.rollback()


# Verifies that the database rejects unsupported image MIME types.
def test_database_rejects_unsupported_media_mime_type(
    app,
    test_report,
    uploaded_report_media
):
    with app.app_context():
        media = db.session.get(
            FloodReportMedia,
            uploaded_report_media
        )

        media.mime_type = "application/octet-stream"

        with pytest.raises(IntegrityError):
            db.session.commit()

        db.session.rollback()


# Tests rejection of unsupported image extensions.
@pytest.mark.parametrize(
    "filename",
    ["photo.gif", "photo.bmp", "photo.txt", "photo"],
)
def test_validate_rejects_unsupported_extensions(filename):
    uploaded_file = FileStorage(
        stream=create_test_png(),
        filename=filename,
    )

    with pytest.raises(ValueError, match="Only JPEG, PNG and WebP"):
        validate_image_file(uploaded_file)


# Tests rejection of an empty image.
def test_validate_rejects_empty_image():
    uploaded_file = FileStorage(
        stream=io.BytesIO(b""),
        filename="empty.png",
    )

    with pytest.raises(ValueError, match="Uploaded image is empty"):
        validate_image_file(uploaded_file)


# Tests rejection of an image larger than the allowed file size.
def test_validate_rejects_oversized_file():
    uploaded_file = FileStorage(
        stream=io.BytesIO(b"A" * (5 * 1024 * 1024 + 1)),
        filename="large.png",
    )

    with pytest.raises(ValueError, match="5 MB or smaller"):
        validate_image_file(uploaded_file)


# Tests rejection when the image signature does not match its extension.
def test_validate_rejects_mismatched_signature():
    uploaded_file = FileStorage(
        stream=io.BytesIO(b"NOTPNG" + b"\x00" * 20),
        filename="photo.png",
    )

    with pytest.raises(ValueError, match="does not match"):
        validate_image_file(uploaded_file)


# Tests rejection when Pillow cannot identify a signed image.
def test_validate_rejects_corrupt_png():
    uploaded_file = FileStorage(
        stream=io.BytesIO(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
        ),
        filename="corrupt.png",
    )

    with pytest.raises(ValueError, match="not a valid or safe image"):
        validate_image_file(uploaded_file)


# Tests rejection when image dimensions exceed the permitted width.
def test_validate_rejects_excessive_image_dimensions():
    image_buffer = io.BytesIO()
    image = Image.new("RGB", (6001, 1))
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)

    uploaded_file = FileStorage(
        stream=image_buffer,
        filename="wide.png",
    )

    with pytest.raises(ValueError, match="dimensions must not exceed"):
        validate_image_file(uploaded_file)


# Tests rejection of an image exceeding the total pixel limit.
def test_validate_rejects_excessive_pixel_count():
    image_buffer = io.BytesIO()
    image = Image.new("RGB", (5001, 5001))
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)

    uploaded_file = FileStorage(
        stream=image_buffer,
        filename="pixels.png",
    )

    with pytest.raises(ValueError, match="too many pixels"):
        validate_image_file(uploaded_file)


# Tests rejection of animated GIF content renamed with a PNG extension.
def test_validate_rejects_animated_image():
    image_buffer = io.BytesIO()

    first_frame = Image.new("RGB", (10, 10), color="red")
    second_frame = Image.new("RGB", (10, 10), color="blue")

    first_frame.save(
        image_buffer,
        format="PNG",
        save_all=True,
        append_images=[second_frame],
    )

    # Pillow does not support animated PNG writing in this form.
    # Use an animated WebP image instead.
    image_buffer = io.BytesIO()

    first_frame.save(
        image_buffer,
        format="WEBP",
        save_all=True,
        append_images=[second_frame],
        duration=100,
        loop=0,
    )

    image_buffer.seek(0)

    uploaded_file = FileStorage(
        stream=image_buffer,
        filename="animated.webp",
    )

    with pytest.raises(ValueError, match="Animated images are not allowed"):
        validate_image_file(uploaded_file)



# Tests rejection when Pillow detects a format different from the extension.
def test_validate_rejects_format_extension_mismatch(monkeypatch):
    uploaded_file = FileStorage(
        stream=io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 20),
        filename="photo.jpg",
    )

    class FakeImage:
        format = "PNG"
        n_frames = 1
        size = (10, 10)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.services.media_service.Image.open",
        lambda *args, **kwargs: FakeImage(),
    )

    with pytest.raises(ValueError, match="Image format does not match"):
        validate_image_file(uploaded_file)

# Tests the fallback filename when sanitization produces an empty result.
def test_save_media_uses_fallback_filename(
    app, test_report, monkeypatch
):
    from app.models.flood_report import FloodReport

    monkeypatch.setattr(
        "app.services.media_service.secure_filename",
        lambda filename: "",
    )

    with app.app_context():
        report = db.session.get(FloodReport, test_report)

        records = save_report_media(
            report,
            [
                FileStorage(
                    stream=create_test_png(),
                    filename="photo.png",
                )
            ],
        )

        assert len(records) == 1
        assert records[0].original_filename == "image"


# Tests uploaded-file cleanup when database commit fails.
def test_save_media_cleans_files_after_commit_failure(
    app, test_report, monkeypatch
):
    from app.models.flood_report import FloodReport

    saved_paths = []
    original_save = FileStorage.save

    def capture_saved_file(uploaded_file, destination, *args, **kwargs):
        original_save(uploaded_file, destination, *args, **kwargs)
        saved_paths.append(destination)

    monkeypatch.setattr(FileStorage, "save", capture_saved_file)

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    with app.app_context():
        report = db.session.get(FloodReport, test_report)

        with pytest.raises(RuntimeError, match="Database commit failed"):
            save_report_media(
                report,
                [
                    FileStorage(
                        stream=create_test_png(),
                        filename="rollback.png",
                    )
                ],
            )

    assert len(saved_paths) == 1
    assert not os.path.exists(saved_paths[0])


# Tests logging when an uploaded file cannot be removed after a save failure.
def test_save_media_logs_cleanup_failure(
    app, test_report, monkeypatch
):
    from app.models.flood_report import FloodReport

    def fail_commit():
        raise RuntimeError("Database commit failed")

    def fail_remove(path):
        raise OSError("Simulated file cleanup failure")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    monkeypatch.setattr(
        "app.services.media_service.os.remove",
        fail_remove,
    )

    with app.app_context():
        report = db.session.get(FloodReport, test_report)

        with pytest.raises(RuntimeError, match="Database commit failed"):
            save_report_media(
                report,
                [
                    FileStorage(
                        stream=create_test_png(),
                        filename="cleanup.png",
                    )
                ],
            )


# Tests deletion when the requested media record does not exist.
def test_delete_media_returns_false_when_missing(app, test_report):
    with app.app_context():
        result = delete_report_media(
            test_report,
            999999,
        )

        assert result is False


# Tests logging when a staged image cannot be restored after a DB failure.
def test_delete_media_logs_restore_failure(
    app,
    test_report,
    uploaded_report_media,
    monkeypatch,
):
    original_replace = os.replace
    replace_calls = {"count": 0}

    def fail_restore(source, destination):
        replace_calls["count"] += 1

        if replace_calls["count"] == 2:
            raise OSError("Simulated restore failure")

        return original_replace(source, destination)

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(
        "app.services.media_service.os.replace",
        fail_restore,
    )
    monkeypatch.setattr(db.session, "commit", fail_commit)

    with app.app_context():
        with pytest.raises(RuntimeError, match="Database commit failed"):
            delete_report_media(
                test_report,
                uploaded_report_media,
            )

    assert replace_calls["count"] == 2


# Tests logging when staged-file cleanup fails after database deletion.
def test_delete_media_logs_staged_cleanup_failure(
    app,
    test_report,
    uploaded_report_media,
    monkeypatch,
):
    def fail_remove(path):
        raise OSError("Simulated staged-file cleanup failure")

    monkeypatch.setattr(
        "app.services.media_service.os.remove",
        fail_remove,
    )

    with app.app_context():
        result = delete_report_media(
            test_report,
            uploaded_report_media,
        )

        assert result is True

        assert db.session.get(
            FloodReportMedia,
            uploaded_report_media,
        ) is None
# Tests that an upload request without a photograph is rejected.
def test_upload_rejects_missing_photograph(auth_client, test_report):
    response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == (
        "Please select at least one photograph"
    )


# Tests that an upload with a blank filename is rejected.
def test_upload_rejects_blank_filename(auth_client, test_report):
    response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                create_test_png(),
                "",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == (
        "Please select at least one photograph"
    )


# Tests that an upload containing more than three photographs is rejected.
def test_upload_rejects_more_than_three_photographs(
    auth_client,
    test_report,
):
    response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": [
                (create_test_png(), "one.png"),
                (create_test_png(), "two.png"),
                (create_test_png(), "three.png"),
                (create_test_png(), "four.png"),
            ]
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == (
        "You can upload a maximum of 3 photographs at once"
    )


# Tests that unexpected media-service errors return a safe API response.
def test_upload_handles_unexpected_service_error(
    auth_client,
    test_report,
    monkeypatch,
):
    def simulate_upload_failure(*args, **kwargs):
        raise RuntimeError("Simulated upload failure")

    monkeypatch.setattr(
        "app.routes.reports.save_report_media",
        simulate_upload_failure,
    )

    response = auth_client.post(
        f"/api/reports/{test_report}/media",
        data={
            "photos": (
                create_test_png(),
                "failure.png",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    assert response.get_json()["message"] == (
        "Unable to upload photographs"
    )


# Tests that requesting a nonexistent media record returns 404.
def test_view_nonexistent_media_returns_404(
    auth_client,
    test_report,
):
    response = auth_client.get(
        f"/api/reports/{test_report}/media/999999"
    )

    assert response.status_code == 404
    assert response.get_json()["message"] == "Photograph not found"


# Tests that deleting a nonexistent media record returns 404.
def test_delete_nonexistent_media_returns_404(
    auth_client,
    test_report,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.routes.reports.delete_report_media",
        lambda report_id, media_id: False,
    )

    response = auth_client.delete(
        f"/api/reports/{test_report}/media/999999"
    )

    assert response.status_code == 404
    assert response.get_json()["message"] == "Photograph not found"