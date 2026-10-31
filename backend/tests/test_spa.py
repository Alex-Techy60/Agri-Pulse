"""The single-page-app fallback: page routes get index.html; missing files and unknown API paths get a real 404."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_spa


def client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "secret.txt").write_text("top secret")
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in ("assets", "index.html"):
        (tmp_path / name).rename(dist / name)
    api = FastAPI()

    @api.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_spa(api, dist)
    return TestClient(api)


def test_page_routes_get_the_app_and_real_files_are_served(tmp_path):
    c = client(tmp_path)
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/some/page").text == "<html>app</html>"  # client-side route
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/ping").json() == {"ok": True}  # real API routes are untouched


def test_missing_files_and_unknown_api_paths_are_404_not_html(tmp_path):
    c = client(tmp_path)
    for path in ("/favicon.ico", "/robots.txt", "/old-bundle.js", "/api/nope", "/api/chats/x/y", "/api"):
        r = c.get(path)
        assert r.status_code == 404 and "<html" not in r.text, path


def test_path_traversal_cannot_leave_the_build_folder(tmp_path):
    c = client(tmp_path)
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
        assert "top secret" not in c.get(path).text, path
