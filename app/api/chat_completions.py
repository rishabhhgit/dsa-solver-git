from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.models.openai import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    make_error,
)
from app.models.solver import ExtractedImage
from app.security.auth import require_backend_api_key
from app.services.gemini_solver import GeminiSolverError, solve_problem
from app.services.mistral_ocr import MistralOcrError, run_ocr_on_images
from app.services.problem_reconstructor import reconstruct_problem
from app.utils.images import ImageValidationError, decode_and_validate_image, validate_image_count
from app.utils.logging import Timer, log_request_event, new_request_id

router = APIRouter(tags=["chat"])


def _extract_text_and_images(req: ChatCompletionRequest, max_image_mb: int) -> tuple[str, list[ExtractedImage]]:
    """Pulls out a single combined user-facing text prompt and any
    decoded/validated images, preserving message and part order."""
    text_parts: list[str] = []
    images: list[ExtractedImage] = []

    for msg in req.messages:
        if msg.role != "user":
            continue
        if isinstance(msg.content, str):
            if msg.content.strip():
                text_parts.append(msg.content.strip())
            continue
        for part in msg.content:
            if part.type == "text":
                if part.text.strip():
                    text_parts.append(part.text.strip())
            elif part.type == "image_url":
                decoded = decode_and_validate_image(part.image_url.url, max_image_mb)
                images.append(ExtractedImage(mime_type=decoded.mime_type, data=decoded.data))

    return "\n\n".join(text_parts), images


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    api_key: str = Depends(require_backend_api_key),
    settings: Settings = Depends(get_settings),
):
    request_id = new_request_id()
    overall_timer = Timer()

    if body.model != settings.PUBLIC_MODEL_NAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=make_error(
                f"Unknown model '{body.model}'. Use '{settings.PUBLIC_MODEL_NAME}'.",
                "invalid_request_error",
                param="model",
                code="model_not_found",
            ),
        )

    if body.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=make_error(
                "Streaming responses are not yet supported by this backend.",
                "invalid_request_error",
                param="stream",
                code="unsupported_feature",
            ),
        )

    with overall_timer:
        try:
            text, images = _extract_text_and_images(body, settings.MAX_IMAGE_SIZE_MB)
        except ImageValidationError as exc:
            log_request_event(request_id, success=False, http_status=400)
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if exc.code == "request_too_large" else status.HTTP_400_BAD_REQUEST
            raise HTTPException(
                status_code=status_code,
                detail=make_error(exc.message, "invalid_request_error", code=exc.code),
            )

        try:
            validate_image_count(len(images), settings.MAX_IMAGES)
        except ImageValidationError as exc:
            log_request_event(request_id, success=False, http_status=400)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(exc.message, "invalid_request_error", code=exc.code),
            )

        if not text and not images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error("Request contains no text or images to solve.", "invalid_request_error"),
            )

        ocr_duration_ms = None
        gemini_duration_ms = None

        if images:
            # Image path: OCR each screenshot, reconstruct, then solve once.
            ocr_timer = Timer()
            try:
                with ocr_timer:
                    ocr_results = await run_ocr_on_images(settings, images)
            except MistralOcrError:
                log_request_event(request_id, num_images=len(images), success=False, http_status=502)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=make_error("OCR provider failed to process the screenshots.", "upstream_error"),
                )
            ocr_duration_ms = ocr_timer.elapsed_ms

            reconstructed = reconstruct_problem(ocr_results)
            problem_text = reconstructed.text
            if text:
                problem_text = f"{problem_text}\n\nADDITIONAL USER NOTES:\n{text}"
        else:
            # Text-only path: never invoke OCR.
            problem_text = text

        gemini_timer = Timer()
        try:
            with gemini_timer:
                solution_text = await solve_problem(settings, problem_text)
        except GeminiSolverError:
            log_request_event(
                request_id,
                num_images=len(images),
                ocr_duration_ms=ocr_duration_ms,
                success=False,
                http_status=502,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=make_error("The solver provider failed to produce a response.", "upstream_error"),
            )
        gemini_duration_ms = gemini_timer.elapsed_ms

    response = ChatCompletionResponse(
        model=settings.PUBLIC_MODEL_NAME,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=solution_text),
                finish_reason="stop",
            )
        ],
    )

    log_request_event(
        request_id,
        num_images=len(images),
        ocr_duration_ms=ocr_duration_ms,
        gemini_duration_ms=gemini_duration_ms,
        total_latency_ms=overall_timer.elapsed_ms,
        success=True,
        http_status=200,
    )

    return response
