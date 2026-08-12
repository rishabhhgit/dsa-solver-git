"""
Mistral OCR integration.

Sends each screenshot to Mistral's OCR API and returns extracted
Markdown/text, preserving headings, code blocks, tables, and
mathematical notation as best the OCR model provides them. Screenshots
are processed concurrently (bounded) and are never written to disk.
"""
from __future__ import annotations

import asyncio
import base64

import httpx

from app.config import Settings
from app.models.solver import ExtractedImage, OcrResult

MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
_MAX_CONCURRENCY = 5


class MistralOcrError(Exception):
    """Raised when the upstream OCR provider fails or is unreachable."""


async def _ocr_single_image(
    client: httpx.AsyncClient,
    settings: Settings,
    index: int,
    image: ExtractedImage,
    semaphore: asyncio.Semaphore,
) -> OcrResult:
    b64_data = base64.b64encode(image.data).decode("ascii")
    payload = {
        "model": settings.MISTRAL_OCR_MODEL,
        "document": {
            "type": "image_url",
            "image_url": f"data:{image.mime_type};base64,{b64_data}",
        },
    }
    headers = {"Authorization": f"Bearer {settings.MISTRAL_API_KEY}"}

    async with semaphore:
        try:
            resp = await client.post(
                MISTRAL_OCR_URL,
                json=payload,
                headers=headers,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise MistralOcrError(f"Failed to reach Mistral OCR: {exc}") from exc

    if resp.status_code >= 400:
        raise MistralOcrError(f"Mistral OCR returned HTTP {resp.status_code}.")

    try:
        data = resp.json()
        pages = data.get("pages", [])
        text = "\n\n".join(p.get("markdown", "") for p in pages).strip()
    except Exception as exc:  # noqa: BLE001
        raise MistralOcrError(f"Unexpected Mistral OCR response format: {exc}") from exc

    if not text:
        return OcrResult(index=index, text="", unreadable=True)

    return OcrResult(index=index, text=text, unreadable=False)


async def run_ocr_on_images(
    settings: Settings,
    images: list[ExtractedImage],
    client: httpx.AsyncClient | None = None,
) -> list[OcrResult]:
    """Runs OCR on all images concurrently, preserving input order in
    the returned list regardless of completion order."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient()
    try:
        tasks = [
            _ocr_single_image(client, settings, idx, img, semaphore)
            for idx, img in enumerate(images)
        ]
        results = await asyncio.gather(*tasks)
    finally:
        if owns_client:
            await client.aclose()

    return sorted(results, key=lambda r: r.index)
