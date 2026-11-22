import io
import struct
import zlib

import pytest
from PIL import Image

from api.db.models import AuditLog, Role, User
from api.media import LocalStorage, S3Storage, sanitize_image

SECRET_TEXT = b"GPS-LAT-18.52-LON-73.85"


def jpeg_with_exif(size=(800, 600), color=(200, 120, 60)) -> bytes:
    image = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[0x010E] = SECRET_TEXT.decode()      # ImageDescription
    exif[0x0110] = "Secret Camera Model"     # Model
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def png(size=(300, 300), mode="RGBA") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, (10, 20, 30, 128) if mode == "RGBA" else (10, 20, 30)).save(out, format="PNG")
    return out.getvalue()


def huge_png(width, height) -> bytes:
    """A tiny file that claims enormous dimensions (decompression-bomb style)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = zlib.compress(b"\x00" * (width // 8 + 1) * 4)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def put_photo(client, headers, data, content_type="image/jpeg"):
    return client.put("/profile/me/photo", content=data,
                      headers={**headers, "Content-Type": content_type})


def test_upload_strips_metadata_and_reencodes(client, analyst, settings):
    _, headers = analyst
    original = jpeg_with_exif()
    assert SECRET_TEXT in original
    response = put_photo(client, headers, original)
    assert response.status_code == 200 and response.json()["has_photo"] is True
    assert response.json()["photo_locked"] is True        # locked by default
    photo = client.get(response.json()["photo_url"], headers=headers)
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/webp"
    assert SECRET_TEXT not in photo.content and b"Secret Camera" not in photo.content
    with Image.open(io.BytesIO(photo.content)) as decoded:
        assert decoded.format == "WEBP" and decoded.size == (512, 512)
        assert not decoded.info.get("exif") and not decoded.info.get("icc_profile")
    stored = list((settings.upload_dir / "profile").glob("*.webp"))
    assert len(stored) == 1 and SECRET_TEXT not in stored[0].read_bytes()


def test_image_response_headers_block_misuse(client, analyst):
    _, headers = analyst
    url = put_photo(client, headers, png(), "image/png").json()["photo_url"]
    photo = client.get(url, headers=headers)
    assert photo.headers["x-content-type-options"] == "nosniff"
    assert photo.headers["cross-origin-resource-policy"] == "same-origin"
    assert "sandbox" in photo.headers["content-security-policy"]
    assert photo.headers["cache-control"] == "private, no-store"


def test_profile_lock_controls_who_can_see(client, make_user):
    owner, owner_h = make_user(Role.analyst, "owner@example.com")
    _, other_h = make_user(Role.analyst, "other@example.com")
    _, reviewer_h = make_user(Role.reviewer, "rev@example.com")
    _, admin_h = make_user(Role.admin, "adm@example.com")
    url = put_photo(client, owner_h, jpeg_with_exif()).json()["photo_url"]
    assert client.get(url).status_code == 401
    assert client.get(url, headers=other_h).status_code == 404
    assert client.get(url, headers=reviewer_h).status_code == 404
    assert client.get(url, headers=admin_h).status_code == 200
    assert client.patch("/profile/me", headers=owner_h, json={"photo_locked": False}).status_code == 200
    assert client.get(url, headers=other_h).status_code == 200
    for bad in ("no", 0, "false", None):
        assert client.patch("/profile/me", headers=owner_h, json={"photo_locked": bad}).status_code == 422


def test_users_without_photo_get_404(client, analyst, make_user):
    user, _ = analyst
    _, other_h = make_user(Role.admin, "a2@example.com")
    assert client.get(f"/profile/{user.id}/photo", headers=other_h).status_code == 404
    assert client.get("/profile/99999/photo", headers=other_h).status_code == 404


@pytest.mark.parametrize("data,content_type", [
    (b"just some text", "image/png"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml"),
    (b"GIF89a" + b"\x00" * 100, "image/gif"),
    (b"\x89PNG\r\n\x1a\n<html><script>alert(1)</script></html>", "image/png"),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 50, "image/jpeg"),
    (b"", "image/png"),
    (b"\xff\xd8\xff" + b"A" * 64, "text/html"),
])
def test_malicious_or_invalid_files_rejected(client, analyst, data, content_type):
    _, headers = analyst
    assert put_photo(client, headers, data, content_type).status_code == 422
    assert client.get("/profile/me", headers=headers).json()["has_photo"] is False


@pytest.mark.parametrize("size", [(9000, 40), (7000, 7000), (20, 20)])
def test_bad_dimensions_rejected(client, analyst, size):
    _, headers = analyst
    data = huge_png(*size) if size[0] > 100 else png(size, "RGB")
    assert put_photo(client, headers, data, "image/png").status_code == 422


def test_png_disguised_as_jpeg_is_reencoded_safely(client, analyst):
    _, headers = analyst
    response = put_photo(client, headers, png(), "image/jpeg")
    assert response.status_code == 200


def test_mismatched_magic_and_format_rejected():
    data = b"RIFF\x00\x00\x00\x00WEBP" + png()[12:]
    with pytest.raises(Exception):
        sanitize_image(data, "image/webp", "profile")


def test_oversized_upload_rejected_before_reading(client, analyst):
    _, headers = analyst
    response = put_photo(client, headers, b"\xff\xd8\xff" + b"0" * (6 * 1024 * 1024), "image/jpeg")
    assert response.status_code == 413


def test_normal_requests_keep_small_body_limit(client, analyst):
    _, headers = analyst
    assert client.post("/classify", headers=headers, content=b"x" * 70000).status_code == 413


def test_replace_and_delete_remove_old_files(client, analyst, settings):
    _, headers = analyst
    put_photo(client, headers, jpeg_with_exif())
    put_photo(client, headers, png(), "image/png")
    assert len(list((settings.upload_dir / "profile").glob("*.webp"))) == 1
    assert client.delete("/profile/me/photo", headers=headers).status_code == 200
    assert list((settings.upload_dir / "profile").glob("*.webp")) == []
    assert client.delete("/profile/me/photo", headers=headers).status_code == 404


def test_upload_rate_limit(client, analyst):
    _, headers = analyst
    small = png((40, 40), "RGB")
    codes = [put_photo(client, headers, small, "image/png").status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_admin_can_remove_photo_but_not_a_superadmins(client, make_user):
    _, user_h = make_user(Role.analyst, "u@example.com")
    target = client.get("/auth/me", headers=user_h).json()["id"]
    sup, sup_h = make_user(Role.superadmin, "sup@example.com")
    _, admin_h = make_user(Role.admin, "adm@example.com")
    put_photo(client, user_h, jpeg_with_exif())
    put_photo(client, sup_h, jpeg_with_exif())
    assert client.delete(f"/admin/users/{target}/photo", headers=user_h).status_code == 403
    assert client.delete(f"/admin/users/{target}/photo", headers=admin_h).status_code == 200
    assert client.get("/profile/me", headers=user_h).json()["has_photo"] is False
    assert client.delete(f"/admin/users/{sup.id}/photo", headers=admin_h).status_code == 403


def test_uploads_are_audited(client, analyst, db):
    user, headers = analyst
    put_photo(client, headers, jpeg_with_exif())
    assert db.query(AuditLog).filter_by(user_id=user.id, action="upload_image").count() == 1


def test_storage_rejects_path_traversal(tmp_path):
    storage = LocalStorage(tmp_path)
    for key in ("../escape.webp", "profile/../../x.webp", "profile/abc.webp", "/etc/passwd"):
        with pytest.raises(ValueError):
            storage.put(key, b"x")


class FakeS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.objects, self.calls = {}, []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


def test_s3_storage_is_private_and_encrypted():
    fake = FakeS3()
    storage = S3Storage("bucket", "ap-south-1", client=fake)
    key = "profile/" + "a" * 32 + ".webp"
    storage.put(key, b"data")
    call = fake.calls[0]
    assert call["ServerSideEncryption"] == "AES256" and call["ContentType"] == "image/webp"
    assert "ACL" not in call
    assert storage.get(key) == b"data"
    storage.delete(key)
    assert storage.get(key) is None
    with pytest.raises(ValueError):
        storage.put("../" + key, b"x")


# ---------------------------------------------------------------- site content

def test_public_site_content_defaults(client):
    body = client.get("/site/content").json()
    assert len(body["team"]) == 4 and len(body["guides"]) == 2
    assert all(p["photo_url"] is None for p in body["team"] + body["guides"])


def _content(**over):
    base = {"team": [{"name": "Asha Patil", "role": "ML lead", "photo_id": None}],
            "guides": [{"name": "Dr. Guide One", "role": "Guide"}, {"name": "Dr. Guide Two", "role": "Co-guide"}],
            "business": {"name": "FlowLytix", "email": "help@example.com", "phone": "1",
                         "address": "Lab", "last_updated": "22 Nov 2026"}}
    base.update(over)
    return base


def test_only_superadmin_edits_site(client, make_user):
    _, admin_h = make_user(Role.admin)
    _, sup_h = make_user(Role.superadmin, "s@example.com")
    assert client.put("/site/content", json=_content()).status_code == 401
    assert client.put("/site/content", headers=admin_h, json=_content()).status_code == 403
    response = client.put("/site/content", headers=sup_h, json=_content())
    assert response.status_code == 200
    assert client.get("/site/content").json()["guides"][1]["name"] == "Dr. Guide Two"
    assert client.post("/site/photos", headers={**admin_h, "Content-Type": "image/png"},
                       content=png()).status_code == 403


def test_site_photo_flow(client, make_user, analyst, db):
    _, sup_h = make_user(Role.superadmin, "s@example.com")
    uploaded = client.post("/site/photos", headers={**sup_h, "Content-Type": "image/jpeg"},
                           content=jpeg_with_exif())
    assert uploaded.status_code == 201
    photo_id = uploaded.json()["id"]
    team = [{"name": "Asha Patil", "role": "ML lead", "photo_id": photo_id}]
    assert client.put("/site/content", headers=sup_h, json=_content(team=team)).status_code == 200
    url = client.get("/site/content").json()["team"][0]["photo_url"]
    public = client.get(url)
    assert public.status_code == 200 and SECRET_TEXT not in public.content
    assert public.headers["cross-origin-resource-policy"] == "same-origin"
    user, user_h = analyst
    put_photo(client, user_h, jpeg_with_exif())
    from api.db.models import UserProfile
    profile_image_id = db.get(UserProfile, user.id).photo_id
    # A private profile photo is never reachable through the public site-photo route.
    assert client.get(f"/site/photos/{profile_image_id}").status_code == 404


@pytest.mark.parametrize("change", [
    {"team": [{"name": "   ", "role": ""}]},
    {"team": [{"name": "x" * 81}]},
    {"team": [{"name": "A", "photo_id": "f" * 32}]},
    {"team": [{"name": "A", "photo_id": "../../etc"}]},
    {"team": [{"name": f"M{i}"} for i in range(9)]},
    {"guides": [{"name": "G", "script": "<b>"}]},
    {"extra": True},
])
def test_site_content_validation(client, make_user, change):
    _, sup_h = make_user(Role.superadmin, "s@example.com")
    assert client.put("/site/content", headers=sup_h, json=_content(**change)).status_code == 422


@pytest.mark.parametrize("path", ["/site/photos/../../etc/passwd", "/site/photos/" + "g" * 32,
                                  "/site/photos/" + "a" * 32])
def test_site_photo_bad_ids(client, path):
    assert client.get(path).status_code in (404, 422)


# ------------------------------------------------------------------ superadmin

def test_superadmin_powers_and_limits(client, make_user):
    sup, sup_h = make_user(Role.superadmin, "s@example.com")
    adm, adm_h = make_user(Role.admin, "a@example.com")
    assert client.get("/admin/overview", headers=sup_h).status_code == 200
    assert client.get("/users", headers=sup_h).status_code == 200
    new = {"email": "new@example.com", "full_name": "New S", "password": "password123", "role": "superadmin"}
    assert client.post("/users", headers=adm_h, json=new).status_code == 403
    assert client.patch(f"/users/{sup.id}", headers=adm_h, json={"full_name": "Hacked"}).status_code == 403
    assert client.patch(f"/users/{sup.id}", headers=adm_h, json={"password": "takeover-123"}).status_code == 403
    assert client.patch(f"/users/{adm.id}", headers=adm_h, json={"role": "superadmin"}).status_code == 403
    assert client.patch(f"/users/{sup.id}", headers=sup_h, json={"role": "admin"}).status_code == 409
    assert client.patch(f"/users/{adm.id}", headers=sup_h, json={"role": "superadmin"}).status_code == 200
    assert client.patch(f"/users/{sup.id}", headers=sup_h, json={"role": "admin"}).status_code == 200


def test_make_superadmin_script(settings, db, make_user, monkeypatch):
    import sys
    from scripts import make_superadmin
    user, _ = make_user(Role.admin, "promote@example.com")
    monkeypatch.setattr(make_superadmin, "load_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["x", "PROMOTE@example.com"])
    make_superadmin.main()
    db.expire_all()
    assert db.get(User, user.id).role == Role.superadmin


def test_make_superadmin_can_change_email(settings, db, make_user, monkeypatch):
    import sys
    from scripts import make_superadmin
    user, _ = make_user(Role.admin, "admin@flowtool.local")
    make_user(Role.analyst, "taken@example.com")
    monkeypatch.setattr(make_superadmin, "load_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["x", "admin@flowtool.local", "--new-email", "taken@example.com"])
    with pytest.raises(SystemExit):
        make_superadmin.main()
    monkeypatch.setattr(sys, "argv", ["x", "admin@flowtool.local", "--new-email", " Owner@Example.com "])
    make_superadmin.main()
    db.expire_all()
    changed = db.get(User, user.id)
    assert changed.email == "owner@example.com" and changed.role == Role.superadmin
    monkeypatch.setattr(sys, "argv", ["x", "owner@example.com", "--new-email", "not-an-email"])
    with pytest.raises(SystemExit):
        make_superadmin.main()
