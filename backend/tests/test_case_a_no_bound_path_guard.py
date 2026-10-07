"""Static guards: no dead or advertised `bound` transcript-binding path may return.

Rationale: the uploaded transcript can never safely rewrite the approved
satisfaction facts, because `CurriculumCase` binds completed rows to their own
`source_id`; doing so would require forging provenance. The path was therefore
removed **by design**, and a review found the leftovers that made it look
advertised-but-unreachable:

- `CaseADemoRun.completed_binding` defaulted to ``"bound"`` although nothing could
  produce it;
- the response model documented and branched on ``bound``;
- the frontend suppressed the provenance disclosure for ``bound``;
- `CaseADemoRuntime._curriculum()` was dead code with a stale two-value unpack.

These guards are source-level on purpose: they must fail even if the dead branch
happens never to be executed.
"""

from __future__ import annotations

import ast
import re
import typing
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

_SERVICE = BACKEND / "app" / "services" / "case_a_demo.py"
_API = BACKEND / "app" / "api" / "case_a_demo.py"
_VUE = REPO / "frontend" / "src" / "components" / "CaseADemoView.vue"
_TS = REPO / "frontend" / "src" / "api" / "caseADemo.ts"


def test_supported_binding_values_exclude_bound() -> None:
    """`CompletedBinding` 必须**只有** `not_bound` 一个取值。"""

    from app.services.case_a_demo import CompletedBinding

    allowed = typing.get_args(CompletedBinding)
    assert allowed == ("not_bound",), f"unexpected supported bindings: {allowed}"
    assert "bound" not in allowed


def test_runtime_run_default_is_not_bound() -> None:
    """`CaseADemoRun.completed_binding` 的默认值不得是 `bound`。"""

    import dataclasses

    from app.services.case_a_demo import CaseADemoRun

    field = next(f for f in dataclasses.fields(CaseADemoRun) if f.name == "completed_binding")
    assert field.default == "not_bound", field.default


def test_dead_curriculum_helper_is_gone() -> None:
    """`_curriculum()` 是死代码（且曾有两个返回值的过期解包）⇒ 必须不存在。"""

    from app.services.case_a_demo import CaseADemoRuntime

    assert not hasattr(CaseADemoRuntime, "_curriculum"), (
        "the dead _curriculum() helper may not return; it unpacked two values from a "
        "single-value _completed_binding()"
    )


def test_completed_binding_has_a_single_return_shape() -> None:
    """`_completed_binding` 只能返回 `CurriculumCase`（⛔ 不能是二元组）。"""

    tree = ast.parse(_SERVICE.read_text(encoding="utf-8"))
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_completed_binding":
            target = node
            break
    assert target is not None, "_completed_binding not found"

    returns = [node for node in ast.walk(target) if isinstance(node, ast.Return)]
    assert returns, "_completed_binding has no return"
    for node in returns:
        assert not isinstance(node.value, ast.Tuple), (
            "_completed_binding must return a single CurriculumCase, not a tuple "
            "(a tuple return is what left the stale unpack behind)"
        )


def test_service_source_does_not_advertise_bound() -> None:
    """服务层源码不得把 `bound` 作为受支持取值出现（注释里的⛔说明除外）。

    允许的写法只有**明确否定**（同一行含 ⛔ 或"不存在"/"不得"）。
    """

    offenders: list[str] = []
    for number, line in enumerate(_SERVICE.read_text(encoding="utf-8").splitlines(), start=1):
        if not re.search(r"completed_binding|\"bound\"|'bound'", line):
            continue
        if re.search(r"⛔|不存在|不得|不是", line):
            continue
        if '"bound"' in line or "'bound'" in line:
            offenders.append(f"_SERVICE:{number}: {line.strip()}")
    assert not offenders, "service source still advertises `bound`:\n" + "\n".join(offenders)


def test_api_response_model_documents_no_bound_state() -> None:
    """响应模型不得把 `bound` 描述成一个可用状态，也不得有 `bound` 分支。"""

    text = _API.read_text(encoding="utf-8")
    offending = [
        f"_API:{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), start=1)
        if re.search(r'==\s*"bound"|!=\s*"bound"|completed_binding.*"bound"', line)
    ]
    assert not offending, "API layer still branches on `bound`:\n" + "\n".join(offending)

    # 说明函数必须**始终**返回字符串（没有 `bound ⇒ None` 的抑制分支）
    from app.api.case_a_demo import _binding_note

    assert isinstance(_binding_note("not_bound"), str)


def test_frontend_has_no_bound_suppression() -> None:
    """前端不得存在任何可以抑制 provenance 提示的取值分支。"""

    vue = _VUE.read_text(encoding="utf-8")
    assert "'bound'" not in vue and '"bound"' not in vue, (
        "CaseADemoView must not special-case a `bound` binding: the disclosure must "
        "render for every value"
    )
    ts = _TS.read_text(encoding="utf-8")
    for number, line in enumerate(ts.splitlines(), start=1):
        if "'bound'" in line or '"bound"' in line:
            assert re.search(r"⛔|不存在|不得", line), (
                f"{_TS.name}:{number}: `bound` may only appear as an explicit denial"
            )
