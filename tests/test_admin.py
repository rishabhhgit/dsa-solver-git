def test_admin_login_wrong_password(app_client):
    resp = app_client.post("/admin/login", json={"password": "wrong"})
    assert resp.status_code == 401


def test_admin_login_correct_password(app_client):
    resp = app_client.post("/admin/login", json={"password": "test-admin-pw"})
    assert resp.status_code == 200
    assert "dsa_admin_session" in resp.cookies


def test_admin_provider_requires_session(app_client):
    resp = app_client.get("/admin/provider")
    assert resp.status_code == 401


def test_admin_provider_accessible_after_login(admin_client):
    resp = admin_client.get("/admin/provider")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "DSA Practice Solver"
    assert body["model"] == "dsa-solver"


def test_admin_page_serves_html(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_admin_test_backend_requires_session(app_client):
    resp = app_client.post("/admin/test")
    assert resp.status_code == 401


def test_admin_test_backend_reports_gemini_and_mistral(admin_client, monkeypatch):
    import app.api.admin as admin_module
    from app.models.solver import OcrResult

    async def fake_solve(settings, text, client=None):
        return "## Problem\n...\n## Code\n```cpp\nint main(){}\n```"

    async def fake_ocr(settings, images, client=None):
        return [OcrResult(index=0, text="OCR TEST 12345")]

    monkeypatch.setattr(admin_module, "solve_problem", fake_solve)
    monkeypatch.setattr(admin_module, "run_ocr_on_images", fake_ocr)

    resp = admin_client.post("/admin/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gemini_connectivity"] == "ok"
    assert body["response_success"] is True
    assert body["mistral_connectivity"] == "ok"
    assert body["mistral_success"] is True


def test_admin_test_backend_reports_mistral_failure(admin_client, monkeypatch):
    import app.api.admin as admin_module
    from app.services.mistral_ocr import MistralOcrError

    async def fake_solve(settings, text, client=None):
        return "## Problem\n...\n## Code\n```cpp\nint main(){}\n```"

    async def failing_ocr(settings, images, client=None):
        raise MistralOcrError("simulated OCR failure")

    monkeypatch.setattr(admin_module, "solve_problem", fake_solve)
    monkeypatch.setattr(admin_module, "run_ocr_on_images", failing_ocr)

    resp = admin_client.post("/admin/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gemini_connectivity"] == "ok"
    assert body["mistral_connectivity"] == "failed"
    assert body["mistral_success"] is False
    assert "mistral_error" in body
