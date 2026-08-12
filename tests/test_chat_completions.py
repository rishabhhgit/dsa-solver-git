from tests.conftest import make_test_image_data_url

FAKE_SOLUTION = (
    "## Problem\n...\n## Key Observation\n...\n## Approach\n...\n## Algorithm\n1. ...\n"
    "## Correctness\n...\n## Complexity\nTime: O(n)\nSpace: O(1)\n## Code\n```cpp\nint main(){}\n```\n"
    "## Edge Cases\n...\n## Warnings\n..."
)


def _mock_solver(monkeypatch, captured=None):
    import app.api.chat_completions as cc

    async def fake_solve(settings, text, client=None):
        if captured is not None:
            captured.append(text)
        return FAKE_SOLUTION

    monkeypatch.setattr(cc, "solve_problem", fake_solve)


def _mock_ocr(monkeypatch):
    import app.api.chat_completions as cc
    from app.models.solver import OcrResult

    async def fake_ocr(settings, images, client=None):
        return [OcrResult(index=i, text=f"extracted text {i}") for i in range(len(images))]

    monkeypatch.setattr(cc, "run_ocr_on_images", fake_ocr)


def test_text_only_request_does_not_invoke_ocr(app_client, backend_api_key, monkeypatch):
    captured = []
    _mock_solver(monkeypatch, captured)

    import app.api.chat_completions as cc

    async def fail_if_called(*a, **kw):
        raise AssertionError("OCR must not be invoked for text-only requests")

    monkeypatch.setattr(cc, "run_ocr_on_images", fail_if_called)

    resp = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_api_key}"},
        json={"model": "dsa-solver", "messages": [{"role": "user", "content": "Solve: two sum, n <= 1e5"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "dsa-solver"
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == FAKE_SOLUTION
    assert body["choices"][0]["finish_reason"] == "stop"
    assert "Solve: two sum" in captured[0]


def test_multimodal_request_invokes_ocr_then_solver(app_client, backend_api_key, monkeypatch):
    _mock_ocr(monkeypatch)
    captured = []
    _mock_solver(monkeypatch, captured)

    img = make_test_image_data_url("PNG")
    resp = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_api_key}"},
        json={
            "model": "dsa-solver",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Solve this in C++17."},
                        {"type": "image_url", "image_url": {"url": img}},
                    ],
                }
            ],
        },
    )
    assert resp.status_code == 200
    assert "SCREENSHOT 1" in captured[0]
    assert "ADDITIONAL USER NOTES" in captured[0]


def test_multiple_images_preserve_order(app_client, backend_api_key, monkeypatch):
    _mock_ocr(monkeypatch)
    captured = []
    _mock_solver(monkeypatch, captured)

    imgs = [make_test_image_data_url("PNG") for _ in range(3)]
    resp = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_api_key}"},
        json={
            "model": "dsa-solver",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": u}} for u in imgs],
                }
            ],
        },
    )
    assert resp.status_code == 200
    text = captured[0]
    assert text.index("SCREENSHOT 1") < text.index("SCREENSHOT 2") < text.index("SCREENSHOT 3")


def test_wrong_model_name_rejected(app_client, backend_api_key, monkeypatch):
    _mock_solver(monkeypatch)
    resp = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_api_key}"},
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "model_not_found"


def test_streaming_returns_unsupported_error(app_client, backend_api_key, monkeypatch):
    _mock_solver(monkeypatch)
    resp = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_api_key}"},
        json={"model": "dsa-solver", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_feature"


def test_mocked_gemini_failure_returns_502(app_client, backend_api_key, monkeypatch):
    import app.api.chat_completions as cc
    from app.services.gemini_solver import GeminiSolverError

    async def failing_solve(settings, text, client=None):
        raise GeminiSolverError("boom")

    monkeypatch.setattr(cc, "solve_problem", failing_solve)

    resp = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_api_key}"},
        json={"model": "dsa-solver", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "upstream_error"


def test_mocked_mistral_failure_returns_502(app_client, backend_api_key, monkeypatch):
    import app.api.chat_completions as cc
    from app.services.mistral_ocr import MistralOcrError

    async def failing_ocr(settings, images, client=None):
        raise MistralOcrError("boom")

    monkeypatch.setattr(cc, "run_ocr_on_images", failing_ocr)
    _mock_solver(monkeypatch)

    img = make_test_image_data_url("PNG")
    resp = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_api_key}"},
        json={
            "model": "dsa-solver",
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": img}}]}],
        },
    )
    assert resp.status_code == 502
