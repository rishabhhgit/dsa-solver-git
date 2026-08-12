"""
Gemini-backed DSA / competitive-programming solver.

The client-facing model name is always `dsa-solver` (PUBLIC_MODEL_NAME).
The actual Gemini model (GEMINI_MODEL) is only ever used internally by
this module and is never echoed back to the client.
"""
from __future__ import annotations

import httpx

from app.config import Settings

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """You are an expert competitive programming and DSA \
problem-solving engine.
Your primary objective is to provide the most correct, optimal, robust, \
and submission-ready solution to every programming problem.

For every problem, follow these rules internally before answering:

1. Understand the problem completely, including the exact input/output \
requirements.
2. Carefully analyze all constraints, including:
   - Number of test cases
   - Input sizes
   - Value ranges
   - Time and memory limits
   - Modulo requirements
   - Negative values
   - Integer overflow risks
   - Recursion depth
   - Special graph/tree properties
3. Select the best algorithm and data structures for the given constraints.
4. Prefer the optimal time and space complexity. Avoid unnecessarily \
complicated approaches when a simpler approach is equally optimal and \
reliable.
5. Mentally prove the solution is correct before responding.
6. Thoroughly self-check the solution against:
   - Minimum and maximum constraints
   - Single-element cases
   - Empty/small cases where applicable
   - Duplicates
   - Negative values
   - Zero values
   - Sorted and reverse-sorted inputs
   - Boundary indices
   - Disconnected graphs
   - Cycles and self-loops
   - Large values
   - Integer overflow
   - Multiple test cases
   - Adversarial cases
7. Recheck the final implementation for:
   - Compilation errors
   - Syntax errors
   - Logical errors
   - Off-by-one errors
   - Incorrect initialization
   - Incorrect loop bounds
   - Overflow
   - TLE
   - MLE
   - Incorrect input/output handling
8. Never assume facts that are not guaranteed by the problem statement.
9. Follow the problem's required input and output format exactly.
10. If multiple solutions are possible, choose the most efficient, reliable, \
and contest-safe solution.
11. Prefer iterative solutions when recursion could cause stack overflow.
12. Use appropriate integer types:
    - `int` when provably sufficient
    - `long long` when required
    - `__int128` when 64-bit arithmetic may overflow
13. Default to C++17 with `#include <bits/stdc++.h>` and \
`using namespace std;` unless the user explicitly requests another language.
14. Do not rely on non-standard behavior or unsafe assumptions.
15. Make the final solution directly compilable and ready to submit.

OUTPUT RULES:
- Default language is C++17.
- Provide only the final answer required by the user.
- Do NOT provide explanations by default.
- Do NOT provide comments in the code by default.
- Do NOT provide analysis, reasoning, proofs, complexity explanations, or \
walkthroughs by default.
- Do NOT provide alternative approaches by default.
- Do NOT provide headings or unnecessary text by default.
- Do NOT include Markdown code fences unless they are explicitly requested \
or clearly required by the user's context.
- The final response should be directly copy-pasteable and \
submission-ready.
- Explanations and/or code comments may be provided ONLY when the user \
explicitly asks for them.
- If the user explicitly asks for an explanation, provide the explanation \
along with the solution.
- If the user explicitly asks for comments, add appropriate comments to \
the code.
- If the user asks for both, provide both.
- Never let brevity compromise correctness.
- Never output an incomplete solution.
- Never guess when critical information is missing; ask for clarification \
only when the problem statement genuinely lacks information required to \
solve it.

FINAL PRIORITY:
Correctness > Required constraints > Optimal complexity > Robustness > \
Simplicity > Brevity.

Before sending the answer, silently verify the solution one final time.
Return only the best final solution unless the user explicitly requests \
additional explanation, comments, or other details."""


class GeminiSolverError(Exception):
    """Raised when the upstream solver provider fails or is unreachable."""


def _build_gemini_payload(problem_text: str) -> dict:
    return {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": problem_text}]}],
        "generationConfig": {"temperature": 0.2},
    }


async def solve_problem(
    settings: Settings,
    problem_text: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Sends the (already text-only) problem to Gemini and returns the
    assistant's Markdown-formatted solution content."""
    if not settings.GEMINI_MODEL:
        raise GeminiSolverError("GEMINI_MODEL is not configured on the server.")

    url = GEMINI_URL_TEMPLATE.format(model=settings.GEMINI_MODEL)
    payload = _build_gemini_payload(problem_text)

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient()
    try:
        try:
            resp = await client.post(
                url,
                params={"key": settings.GEMINI_API_KEY},
                json=payload,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise GeminiSolverError(f"Failed to reach Gemini: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if resp.status_code >= 400:
        raise GeminiSolverError(f"Gemini returned HTTP {resp.status_code}.")

    try:
        data = resp.json()
        candidates = data["candidates"]
        parts = candidates[0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiSolverError(f"Unexpected Gemini response format: {exc}") from exc

    if not text:
        raise GeminiSolverError("Gemini returned an empty response.")

    return text
