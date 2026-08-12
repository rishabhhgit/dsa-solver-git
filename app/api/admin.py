from __future__ import annotations

import io
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.models.solver import ExtractedImage
from app.security.admin_auth import (
    clear_session_cookie,
    issue_session_cookie,
    require_admin_session,
    verify_admin_password,
)
from app.security.api_keys import get_api_key_store
from app.services.gemini_solver import GeminiSolverError, solve_problem
from app.services.mistral_ocr import MistralOcrError, run_ocr_on_images
from app.services.provider_config import build_provider_config

router = APIRouter(tags=["admin"])

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _make_test_image() -> ExtractedImage:
    """A tiny in-memory PNG containing legible text, used only for the
    admin OCR connectivity check. Never persisted to disk."""
    img = Image.new("RGB", (300, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 30), "OCR TEST 12345", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return ExtractedImage(mime_type="image/png", data=buf.getvalue())


class LoginRequest(BaseModel):
    password: str


@router.post("/admin/login")
async def admin_login(body: LoginRequest, response: Response):
    if not verify_admin_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid administrator password.")
    issue_session_cookie(response)
    return {"status": "ok"}


@router.post("/admin/logout", dependencies=[Depends(require_admin_session)])
async def admin_logout(response: Response):
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/admin", response_class=FileResponse)
async def admin_page():
    """Serves the admin single-page UI. The page itself performs the
    password login via POST /admin/login before calling any protected
    endpoint — no credentials are embedded in this file."""
    return FileResponse(_STATIC_DIR / "admin.html")


@router.get("/admin/provider", dependencies=[Depends(require_admin_session)])
async def admin_get_provider(request: Request, reveal: bool = False, settings: Settings = Depends(get_settings)):
    store = get_api_key_store(settings.DATA_DIR, settings.PROVIDER_API_KEY, settings.ADMIN_SESSION_SECRET)
    config = build_provider_config(settings, store, request=request, reveal_key=reveal)
    return config


@router.post("/admin/provider/regenerate", dependencies=[Depends(require_admin_session)])
async def admin_regenerate_key(settings: Settings = Depends(get_settings)):
    store = get_api_key_store(settings.DATA_DIR, settings.PROVIDER_API_KEY, settings.ADMIN_SESSION_SECRET)
    try:
        store.regenerate()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return {"status": "ok", "message": "API key regenerated. The previous key is no longer valid."}


@router.post("/admin/test", dependencies=[Depends(require_admin_session)])
async def admin_test_backend(settings: Settings = Depends(get_settings)):
    """Runs a simple text-only Gemini round trip and a small in-memory
    image through Mistral OCR, reporting connectivity/success/latency
    for each without exposing provider credentials."""
    store = get_api_key_store(settings.DATA_DIR, settings.PROVIDER_API_KEY, settings.ADMIN_SESSION_SECRET)

    result = {
        "authentication": "ok",  # we're already authenticated as admin to reach here
        "gemini_connectivity": "unknown",
        "response_success": False,
        "latency_ms": None,
        "mistral_connectivity": "unknown",
        "mistral_success": False,
        "mistral_latency_ms": None,
    }

    # --- Gemini check ---
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient() as client:
            text = await solve_problem(
                settings,
                "Given an array of n integers, find the maximum subarray sum. n <= 10^5.",
                client=client,
            )
        result["gemini_connectivity"] = "ok"
        result["response_success"] = bool(text)
    except GeminiSolverError as exc:
        result["gemini_connectivity"] = "failed"
        result["error"] = str(exc)
    finally:
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)

    # --- Mistral OCR check ---
    mistral_start = time.perf_counter()
    try:
        test_image = _make_test_image()
        async with httpx.AsyncClient() as client:
            ocr_results = await run_ocr_on_images(settings, [test_image], client=client)
        extracted_text = ocr_results[0].text if ocr_results else ""
        result["mistral_connectivity"] = "ok"
        result["mistral_success"] = bool(extracted_text.strip())
        if not result["mistral_success"]:
            result["mistral_error"] = "OCR call succeeded but returned no text."
    except MistralOcrError as exc:
        result["mistral_connectivity"] = "failed"
        result["mistral_error"] = str(exc)
    finally:
        result["mistral_latency_ms"] = round((time.perf_counter() - mistral_start) * 1000, 1)

    # ensure the key store has been initialized even if this is the very
    # first admin action taken after a fresh deploy
    store.get_or_create()
    return result
