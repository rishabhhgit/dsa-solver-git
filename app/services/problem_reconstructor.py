"""
Combines per-screenshot OCR output into a single reconstructed problem
statement, in screenshot order, ready to hand to the solver.

This module deliberately does NOT try to be clever about correcting
OCR errors beyond trivial whitespace/duplicate-line cleanup — it is
the solver's job (with the full assembled context) to reason about
ambiguous or unreadable text, and it is explicitly told to never
invent missing constraints or examples.
"""
from __future__ import annotations

from app.models.solver import OcrResult, ReconstructedProblem


def _clean_block(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    # collapse runs of 3+ blank lines down to 1
    cleaned: list[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


def reconstruct_problem(ocr_results: list[OcrResult]) -> ReconstructedProblem:
    ordered = sorted(ocr_results, key=lambda r: r.index)

    blocks: list[str] = []
    for r in ordered:
        header = f"SCREENSHOT {r.index + 1}"
        if r.unreadable or not r.text.strip():
            body = "[UNREADABLE: no text could be extracted from this screenshot]"
        else:
            body = _clean_block(r.text)
        blocks.append(f"{header}\n{body}")

    combined = "\n\n".join(blocks)

    preamble = (
        "The following problem statement was reconstructed from "
        f"{len(ordered)} screenshot(s), preserved in their original order. "
        "Sections marked UNREADABLE could not be OCR'd — treat any such "
        "gaps as genuinely missing information; do not invent constraints, "
        "examples, or input/output formats to fill them in.\n\n"
    )

    return ReconstructedProblem(
        text=preamble + combined,
        screenshot_count=len(ordered),
    )
