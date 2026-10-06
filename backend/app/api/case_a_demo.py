"""Private Case A closed-loop demo endpoints; separate from production /plan."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.models.contracts import CourseOffering, MakeupTask, PlanResult, Preference
from app.services.case_a_demo import (
    CASE_A_DEMO_SCOPE_LABEL,
    CaseADemoInputError,
    CaseADemoRuntime,
    get_case_a_demo_runtime,
)
from app.services.completed_courses_ingest import CompletedCoursesImportRejected, MAX_UPLOAD_BYTES

router = APIRouter(prefix="/case-a-demo", tags=["case-a-demo"])


class CaseADemoPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semester: str = Field(min_length=1)
    transcript_pdf_base64: str = Field(min_length=1)
    current_schedule: list[CourseOffering]
    manual_schedule_attested: bool = False
    preference: Preference


class TranscriptSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    artifact_sha256: str
    record_count: int
    term_count: int
    terms: list[str]
    pending_course_id_count: int


class CaseADemoProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str
    curriculum: str
    course_data: str
    current_schedule: str
    planner: str
    is_full_semester: bool


class CaseADemoPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: TranscriptSummary
    makeup_tasks: list[MakeupTask]
    course_offerings: list[CourseOffering]
    preference: Preference
    plan_result: PlanResult
    provenance: CaseADemoProvenance


def _runtime_or_503(runtime: CaseADemoRuntime | None) -> CaseADemoRuntime:
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "case_a_demo_not_configured", "message": "Case A demo runtime is unavailable."},
        )
    return runtime


@router.get("/offerings", response_model=list[CourseOffering])
def get_case_a_offerings(
    semester: str,
    runtime: Annotated[CaseADemoRuntime | None, Depends(get_case_a_demo_runtime)],
) -> list[CourseOffering]:
    configured = _runtime_or_503(runtime)
    return configured.course_data.get_course_offerings(semester)


@router.post("/plan", response_model=CaseADemoPlanResponse)
def create_case_a_plan(
    request: CaseADemoPlanRequest,
    runtime: Annotated[CaseADemoRuntime | None, Depends(get_case_a_demo_runtime)],
) -> CaseADemoPlanResponse:
    configured = _runtime_or_503(runtime)
    if len(request.transcript_pdf_base64) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 4:
        raise HTTPException(status_code=413, detail="Transcript PDF is too large.")
    try:
        pdf_bytes = base64.b64decode(request.transcript_pdf_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="Transcript PDF encoding is invalid.") from None
    try:
        run = configured.run(
            pdf_bytes=pdf_bytes,
            semester=request.semester,
            current_schedule=request.current_schedule,
            manual_schedule_attested=request.manual_schedule_attested,
            preference=request.preference,
        )
    except CaseADemoInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except CompletedCoursesImportRejected as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code, "message": exc.message},
        ) from None

    manual = any(item.source == "manual-entry://current-schedule" for item in request.current_schedule)
    return CaseADemoPlanResponse(
        transcript=TranscriptSummary(
            source_id=run.transcript.source_id,
            artifact_sha256=run.transcript.artifact_sha256,
            record_count=run.transcript.record_count,
            term_count=run.transcript.term_count,
            terms=list(run.transcript.terms),
            pending_course_id_count=run.transcript.pending_course_id_count,
        ),
        makeup_tasks=run.makeup_tasks,
        course_offerings=run.offerings,
        preference=run.preference,
        plan_result=run.plan_result,
        provenance=CaseADemoProvenance(
            transcript="user-uploaded SYSU transcript PDF",
            curriculum="Case A target curriculum",
            course_data=CASE_A_DEMO_SCOPE_LABEL,
            current_schedule=("student-attested manual input" if manual else "selected accepted offering"),
            planner="actual RestrictedPlanner execution",
            is_full_semester=False,
        ),
    )
