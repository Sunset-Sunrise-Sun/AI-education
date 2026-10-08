"""Personal Planning 测试共用的 **Mock** 输入夹具。

> ⚠️ 本文件里的培养方案、课程、学分与学生记录**全部是人工构造的显式 Mock**，
> 不是中山大学的正式条款，也**不是**任何真实学生的材料。
> `source_id` / `evidence` 一律以 `mock://` 开头，以便
> `CurriculumCase.__post_init__` 的"Mock 来源不得标为 real" 守卫在
> 误用时立刻失败。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.curriculum.catalog import CurriculumCatalog, load_curriculum_catalog
from app.models.contracts import DataSource

#: 源方案（人工构造）。
OLD_VERSION_ID = "mock-old-2025"
#: 目标方案（人工构造）。
TARGET_VERSION_ID = "mock-target-2025"

TARGET_SOURCE_ID = "mock://personal/plan/target"
OLD_SOURCE_ID = "mock://personal/plan/old"
TARGET_GROUP_ID = "MOCK-TGT-ELECTIVE"

#: 目标方案课程表：两门必修（3 + 4 学分）+ 一个 4 学分选修池（2 门各 2 学分）。
_TARGET_COURSES: tuple[dict, ...] = (
    {
        "course_id": "TGT100", "course_name": "示例目标必修一", "credit": 3,
        "requirement": "required", "source_record": "row:TGT100",
        "recommended_term_text": "2026-1", "prerequisites": [],
    },
    {
        "course_id": "TGT101", "course_name": "示例目标必修二", "credit": 4,
        "requirement": "required", "source_record": "row:TGT101",
        "recommended_term_text": "2026-1", "prerequisites": [],
    },
    {
        "course_id": "TGT201", "course_name": "示例目标选修一", "credit": 1,
        "requirement": "elective", "group_id": TARGET_GROUP_ID,
        "source_record": "row:TGT201", "recommended_term_text": "2026-2", "prerequisites": [],
    },
    {
        "course_id": "TGT202", "course_name": "示例目标选修二", "credit": 1,
        "requirement": "elective", "group_id": TARGET_GROUP_ID,
        "source_record": "row:TGT202", "recommended_term_text": "2026-2", "prerequisites": [],
    },
)

_TARGET_GROUPS: tuple[dict, ...] = ({
    "group_id": TARGET_GROUP_ID, "name": "示例目标选修池",
    "minimum_credit": 1, "source_record": "group:MOCK-TGT-ELECTIVE",
},)

#: 源方案课程表：与目标方案**没有**相同 course_id（真实转专业场景就是这样）。
_OLD_COURSES: tuple[dict, ...] = (
    {
        "course_id": "OLD100", "course_name": "示例源必修一", "credit": 3,
        "requirement": "required", "source_record": "row:OLD100",
        "recommended_term_text": "2025-1", "prerequisites": [],
    },
    {
        "course_id": "OLD101", "course_name": "示例源必修二", "credit": 4,
        "requirement": "required", "source_record": "row:OLD101",
        "recommended_term_text": "2025-2", "prerequisites": [],
    },
)


def _version_entry(
    version_id: str,
    *,
    major: str,
    cohort: str,
    source_id: str,
    courses: tuple[dict, ...] | list[dict],
    groups: tuple[dict, ...] | list[dict] = (),
    verified: bool = True,
    supported: bool = True,
    unsupported_reason: str | None = None,
    complete: bool = True,
    verification_evidence: str | None = None,
) -> dict:
    return {
        "version_id": version_id,
        "major": major,
        "cohort": cohort,
        "campus": "示例校区",
        "track": "示例方向",
        "source_id": source_id,
        "verification": {
            "verified": verified,
            "evidence": verification_evidence or f"mock://personal/plan/{version_id}/核验依据",
            "verified_by": "示例核验人",
        },
        "supported": supported,
        "unsupported_reason": unsupported_reason,
        "complete": complete,
        "completeness_evidence": f"mock://personal/plan/{version_id}/完整范围说明",
        "total_credit": 20,
        "practice_credit": 2,
        "study_years": 4,
        "group_records": list(groups),
        "course_records": list(courses),
    }


def catalog_payload(
    *,
    extra_entries: tuple[dict, ...] = (),
    version_entry_overrides: dict | None = None,
) -> dict:
    """完整的目录 artifact（人工 Mock）。"""

    target = _version_entry(
        TARGET_VERSION_ID, major="示例目标专业", cohort="2025",
        source_id=TARGET_SOURCE_ID, courses=_TARGET_COURSES, groups=_TARGET_GROUPS,
    )
    old = _version_entry(
        OLD_VERSION_ID, major="示例源专业", cohort="2025",
        source_id=OLD_SOURCE_ID, courses=_OLD_COURSES,
    )
    if version_entry_overrides:
        target = {**target, **version_entry_overrides}
    return {"catalog_version": 1, "versions": [old, target, *extra_entries]}


def write_catalog(tmp_path: Path, payload: dict | None = None, *, name: str = "catalog.json") -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(payload if payload is not None else catalog_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_catalog(tmp_path: Path, payload: dict | None = None) -> CurriculumCatalog:
    path = write_catalog(tmp_path, payload)
    return load_curriculum_catalog(tmp_path, file_name=path.name)


# --------------------------------------------------------------------------- #
# 两位**独立**的 Mock 学生（不复用彼此任何事实）
# --------------------------------------------------------------------------- #

def student_one_input() -> dict:
    """学生一：两门目标必修都已通过 → TGT100/TGT101 应为 `satisfied`。"""

    return {
        "completed": {
            "complete": True,
            "completeness_evidence": "mock://personal/student-one/完整成绩范围",
            "records": [
                {
                    "course_id": "TGT100", "course_name": "示例目标必修一", "credit": 3,
                    "semester": "2025-1", "passed": True, "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "mock://personal/student-one/TGT100-课程号依据",
                    "source_record": "row:1",
                },
                {
                    "course_id": "TGT101", "course_name": "示例目标必修二", "credit": 4,
                    "semester": "2025-2", "passed": True, "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "mock://personal/student-one/TGT101-课程号依据",
                    "source_record": "row:2",
                },
            ],
        },
        # 选修池需要一次**显式**的选课计划，否则既不算已满足、也不存在可执行计划。
        # 选修池只要求 1 学分，因此这里选一门即可覆盖组要求。
        "elective_selections": [{
            "group_id": TARGET_GROUP_ID,
            "course_ids": ["TGT201"],
            "evidence": "mock://personal/student-one/选修计划（人工确认，Mock）",
        }],
        "rules": {
            "evidence": "mock://personal/student-one/本 case 匹配规则（人工 Mock）",
            "allow_exact_match": True,
            "allow_confirmed_absence": True,
        },
    }


def student_two_input() -> dict:
    """学生二：只通过 TGT100；TGT101 缺修 → 应为 `required`。

    刻意**不**复用学生一的任何已修事实、认定或规则取值。
    """

    return {
        "completed": {
            "complete": True,
            "completeness_evidence": "mock://personal/student-two/完整成绩范围",
            "records": [
                {
                    "course_id": "TGT100", "course_name": "示例目标必修一", "credit": 3,
                    "semester": "2024-1", "passed": True, "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "mock://personal/student-two/TGT100-课程号依据",
                    "source_record": "row:1",
                },
                {
                    "course_id": "TGT100", "course_name": "示例目标必修一", "credit": 3,
                    "semester": "2024-2", "passed": False, "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "mock://personal/student-two/TGT100-课程号依据",
                    "source_record": "row:2",
                },
            ],
        },
        "elective_selections": [{
            "group_id": TARGET_GROUP_ID,
            "course_ids": ["TGT201"],
            "evidence": "mock://personal/student-two/选修计划（人工确认，Mock）",
        }],
        "rules": {
            "evidence": "mock://personal/student-two/本 case 匹配规则（人工 Mock）",
            "allow_exact_match": True,
            "allow_confirmed_absence": True,
        },
    }


def data_source_mock() -> DataSource:
    return DataSource.MOCK
