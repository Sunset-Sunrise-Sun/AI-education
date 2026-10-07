"""Documentation guard: no **global** "everything is Mock" claim may survive.

Rationale: the backend now has three data paths (permanent Mock channel, the real
`/api/v1/plan` entry, and the Case A demo channel). A sentence that claims *all*
responses carry `X-Data-Source: mock` contradicts executable behaviour and is a
provenance/truthfulness defect — it was reported twice by review.

The guard is claim-unit based rather than line based: prose is split into sentence
units and Markdown table rows into cells, and each unit that asserts a Mock
data-source header must also name the scope it applies to.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

#: Every Markdown file whose capability claims a reviewer or an operator may read.
DOC_PATHS = (
    BACKEND / "README.md",
    REPO / "docs" / "ARCHITECTURE.md",
    REPO / "docs" / "status" / "integration.md",
)

#: A unit that asserts the Mock data-source header exists.
_HEADER_CLAIM = re.compile(r"(X-Data-Source|data_source).{0,12}mock|mock.{0,12}(X-Data-Source|data_source)", re.IGNORECASE)

#: Scope markers that make such a claim acceptable.
_SCOPE = (
    "/api/v1/mock",
    "Mock 通道",
    "mock/path",
    "永久 Mock",
    "本表",
    "仅",
    "只",
)

#: Sentences that explicitly *deny* a global claim are fine (and desirable).
_NEGATION = ("⛔", "不", "而非", "不是")


def _units(text: str) -> list[tuple[int, str]]:
    """Return `(first_line_number, claim_unit)` pairs.

    A claim unit is a Markdown table **cell**, or one **logical block** of prose
    (a bullet/paragraph plus its wrapped continuation lines). Grouping continuations
    matters: a scope stated on a wrapped line belongs to the same claim, and
    splitting every ``；`` would manufacture false positives out of list items.
    """

    out: list[tuple[int, str]] = []
    block: list[str] = []
    block_start = 0

    def flush() -> None:
        nonlocal block, block_start
        if block:
            out.append((block_start, " ".join(block).strip()))
            block = []
            block_start = 0

    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        # Markdown table rows: each cell is its own claim unit.
        if stripped.startswith("|") and stripped.endswith("|"):
            flush()
            for cell in stripped.strip("|").split("|"):
                if cell.strip():
                    out.append((number, cell.strip()))
            continue
        # A new bullet or numbered item starts a new logical block.
        starts_item = bool(re.match(r"^([-*+]|\d+\.)\s", stripped))
        if starts_item or not block:
            flush()
            block_start = number
        block.append(stripped)
    flush()
    return out


def test_no_global_all_responses_mock_header_claim() -> None:
    offenders: list[str] = []
    for path in DOC_PATHS:
        assert path.exists(), f"guard is pointed at a missing file: {path}"
        text = path.read_text(encoding="utf-8")
        for number, unit in _units(text):
            if not _HEADER_CLAIM.search(unit):
                continue
            scoped = any(marker in unit for marker in _SCOPE)
            denied = any(marker in unit for marker in _NEGATION)
            if not (scoped or denied):
                offenders.append(f"{path.name}:{number}: {unit}")
    assert not offenders, (
        "global Mock-header claim(s) found; scope them to /api/v1/mock/* "
        "(or state them as a denial):\n" + "\n".join(offenders)
    )


def test_backend_readme_api_inventory_lists_the_real_endpoints() -> None:
    """README 的 API 清单必须与真实 runtime / Case A 演示入口一致。"""

    text = (BACKEND / "README.md").read_text(encoding="utf-8")
    for endpoint in (
        "/api/v1/plan",
        "/api/v1/completed-courses/import",
        "/api/v1/completed-courses/import-pdf",
        "/api/v1/case-a-demo/offerings",
        "/api/v1/case-a-demo/plan",
        "/api/v1/case-a-demo/repair/apply",
    ):
        assert endpoint in text, f"README API inventory is missing {endpoint}"


def test_backend_readme_states_mock_scope_explicitly() -> None:
    """README 必须明确写出 Mock 响应头的**作用范围**。"""

    text = (BACKEND / "README.md").read_text(encoding="utf-8")
    assert "只有 `/api/v1/mock/*`" in text
