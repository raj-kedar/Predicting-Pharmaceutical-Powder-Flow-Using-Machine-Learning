import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def web_client(settings, tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>PowderFlow</title>")
    (web / "admin.html").write_text("<!doctype html><title>Admin</title>")
    (web / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (web / "assets" / "index-abc123.js").write_text("console.log(1);" * 200)
    (tmp_path / "secret.txt").write_text("do-not-serve")
    with TestClient(create_app(settings, web), raise_server_exceptions=False) as client:
        yield client


def test_index_served_with_strict_csp_and_revalidation(web_client):
    response = web_client.get("/")
    assert response.status_code == 200 and "PowderFlow" in response.text
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-cache"


def test_only_the_public_app_may_load_razorpay(web_client):
    assert "checkout.razorpay.com" in web_client.get("/").headers["Content-Security-Policy"]
    admin = web_client.get("/admin")
    assert admin.status_code == 200 and "Admin" in admin.text
    assert "razorpay" not in admin.headers["Content-Security-Policy"]
    assert web_client.get("/admin/overview").status_code == 401


def test_hashed_assets_are_cached_and_compressed(web_client):
    response = web_client.get("/assets/index-abc123.js", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "immutable" in response.headers["Cache-Control"]
    assert response.headers["Content-Encoding"] == "gzip"


def test_missing_asset_is_404_and_not_cached(web_client):
    response = web_client.get("/assets/missing.js")
    assert response.status_code == 404 and response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/assets/../secret.txt", "/assets/%2e%2e/secret.txt",
                                  "/assets/..%2fsecret.txt"])
def test_path_traversal_blocked(web_client, path):
    response = web_client.get(path)
    assert "do-not-serve" not in response.text and response.status_code != 200


def test_api_routes_still_take_priority(web_client):
    assert web_client.get("/health").json()["status"] == "ok"
    assert web_client.get("/predictions").status_code == 401


def test_api_only_mode_without_a_build(settings, tmp_path):
    with TestClient(create_app(settings, tmp_path / "none")) as client:
        assert client.get("/").status_code == 404
        assert client.get("/health").status_code == 200
