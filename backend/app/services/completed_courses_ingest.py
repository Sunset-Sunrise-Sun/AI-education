"""已修课程 XLSX 导入适配器（Gate F）：⛔ 只做**摄取 + 归一化**，⛔ 不做课程认定。

```text
上传字节
  ↓ 媒体类型 / 声明长度 / 实际大小 / 空文件 校验
受控临时文件（进程自己的临时目录，请求结束立即删除）
  ↓ 复用 app/curriculum 既有的 load_completed_courses_xlsx
     （worksheet 抽取 + 字段映射 + 结构校验 + normalize_completed_courses）
CompletedCourse 元组（= Curriculum 既有内部输入）
```

## 硬边界（Gate F）

- ⛔ **不实现** Curriculum Diff / equivalence / recognition / makeup priority /
  prerequisite decision —— 全部继续由 `app/curriculum` 的既有实现负责；
  本适配器只回答"这些字节能不能变成**已归一化的已修课程事实**"；
- ⛔ **不信任文件名**：本模块**不接受**文件名 / 路径参数，任何调用方字符串都⛔ 不作为路径；
  导出的 `source_id` 由**内容摘要**派生（`upload:sha256:<16 hex>`）；
- ⛔ **不写到任意用户指定路径**：只写进程自己的临时目录（`tempfile.mkstemp`），
  且 `finally` 中无条件删除；临时路径⛔ 不出现在任何错误信息里；
- ⛔ **不执行公式 / 宏**：底层 reader 只解析 XML（`zipfile` + `ElementTree`，无 openpyxl），
  含 `<f>` 公式单元格 / 错误单元格的工作表直接 fail closed；
- ⛔ **不打印** worksheet / cell 行内容：错误信息只含通用文案与数字位置，
  绝不含课程名 / 学号 / 姓名 / 原始 XML / 路径 / stacktrace。

## 与 Case A 固定 case 的关系

本模块是**通用 XLSX 摄取能力**（general ingestion），⛔ **不接入**已冻结的 Case A
fixed-case runtime（`app/services/planning_runtime.py` 仍只装配固定 curriculum case）。
两者不要混淆，详见 `docs/data/XLSX_COMPLETED_COURSES_IMPORT.md`。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.xlsx_reader import load_completed_courses_xlsx

__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "APPROVED_WORKSHEET",
    "CompletedCoursesImport",
    "CompletedCoursesImportRejected",
    "MAX_COMPLETED_RECORDS",
    "MAX_UPLOAD_BYTES",
    "OCTET_STREAM_MEDIA_TYPE",
    "SOURCE_ID_PREFIX",
    "XLSX_MEDIA_TYPE",
    "import_completed_courses_xlsx_bytes",
    "normalize_media_type",
    "parse_declared_content_length",
]

#: 官方 XLSX 媒体类型。
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: 通用二进制流；浏览器 `fetch(url, {body: file})` 在部分环境会用它。
OCTET_STREAM_MEDIA_TYPE = "application/octet-stream"

#: 只允许这两种媒体类型（⛔ 不接受 `text/plain`、`multipart/*` 等）。
ALLOWED_MEDIA_TYPES = frozenset({XLSX_MEDIA_TYPE, OCTET_STREAM_MEDIA_TYPE})

#: 上传字节上限（压缩后）。解压后的总量上限由 Curriculum reader 自己把关（64 MiB）。
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

#: 单次导入的记录条数上限（⛔ 不设上限会让超大工作簿变成资源消耗面）。
MAX_COMPLETED_RECORDS = 2000

#: 唯一被支持的 worksheet（已批准的脱敏交接布局）。
APPROVED_WORKSHEET = "已修课程_脱敏"

#: `source_id` 前缀：由**内容摘要**派生，⛔ 不来自文件名 / 调用方字符串。
SOURCE_ID_PREFIX = "upload:sha256:"
_SOURCE_ID_DIGEST_LENGTH = 16

# --- 错误码（API 层把它们映射成明确的 HTTP 状态码） --- #
ERROR_UNSUPPORTED_MEDIA_TYPE = "completed_courses_upload_unsupported_media_type"
ERROR_LENGTH_REQUIRED = "completed_courses_upload_length_required"
ERROR_LENGTH_MISMATCH = "completed_courses_upload_length_mismatch"
ERROR_TOO_LARGE = "completed_courses_upload_too_large"
ERROR_EMPTY_UPLOAD = "completed_courses_upload_empty"
ERROR_INVALID = "completed_courses_invalid"
ERROR_NO_RECORDS = "completed_courses_empty"
ERROR_TOO_MANY_RECORDS = "completed_courses_too_many_records"


class CompletedCoursesImportRejected(Exception):
    """上传被拒绝（fail closed）；⛔ 不携带任何输入值 / 路径。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CompletedCoursesImport:
    """一次成功导入的结果（均为**已归一化**的事实，⛔ 未做任何认定）。"""

    source_id: str
    artifact_sha256: str
    worksheet: str
    courses: tuple[CompletedCourse, ...]

    @property
    def record_count(self) -> int:
        return len(self.courses)

    @property
    def confirmed_course_id_count(self) -> int:
        return sum(
            course.course_id_status is CourseIdStatus.CONFIRMED for course in self.courses
        )

    @property
    def pending_course_id_count(self) -> int:
        return self.record_count - self.confirmed_course_id_count

    @property
    def passed_count(self) -> int:
        return sum(course.passed for course in self.courses)

    @property
    def distinct_course_count(self) -> int:
        return len({course.course_id for course in self.courses if course.course_id is not None})

    @property
    def notes_present_count(self) -> int:
        return sum(course.notes is not None for course in self.courses)

    def case_records(self) -> tuple[dict[str, object], ...]:
        """返回**恰好**是 `completed.records` 输入形状的映射序列。

        ⚠️ 刻意**不导出 `notes`** 自由文本（唯一可能夹带个人信息的字段）：
        它与 Curriculum 的认定无关，因此导出层直接丢弃；
        需要的调用方仍可在服务端读取 `courses`。
        """

        return tuple(
            {
                "course_id": course.course_id,
                "course_name": course.course_name,
                "credit": course.credit,
                "semester": course.semester,
                "passed": course.passed,
                "course_type": course.course_type,
                "course_id_status": course.course_id_status.value,
                "id_match_source": course.id_match_source,
                "source_record": course.source_record,
            }
            for course in self.courses
        )


def _reject(code: str, message: str) -> None:
    raise CompletedCoursesImportRejected(code, message)


def normalize_media_type(value: object) -> str:
    """把 `Content-Type` 归一化成小写媒体类型（丢弃参数），⛔ 不信任其语义。"""

    if not isinstance(value, str) or not value.strip():
        _reject(ERROR_UNSUPPORTED_MEDIA_TYPE, "必须显式声明受支持的 XLSX 媒体类型。")
    media_type = value.split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_MEDIA_TYPES:
        _reject(
            ERROR_UNSUPPORTED_MEDIA_TYPE,
            "只接受 .xlsx（OOXML 工作簿）；其它媒体类型一律拒绝。",
        )
    return media_type


#: `Content-Length` 的**最大位数**（= `MAX_UPLOAD_BYTES` 的十进制位数）。
#: ⚠️ 先比位数再 `int()`：CPython 对超长十进制字符串的 `int()` 会抛
#: `ValueError: Exceeds the limit (4300 digits)`，那会变成 **500**，违反 fail-closed 约定。
_MAX_LENGTH_DIGITS = len(str(MAX_UPLOAD_BYTES))


def parse_declared_content_length(raw: object) -> int:
    """把 `Content-Length` 头解析成字节数；⛔ 任何异常输入都必须 fail closed。

    接受格式**仅限**纯 ASCII 十进制数字（`0-9`，⛔ 无前后空白、⛔ 无符号、
    ⛔ 无小数点、⛔ 无指数、⛔ 无十六进制、⛔ 无千分位逗号、
    ⛔ 无 Unicode 数字如全角 `８` / 阿拉伯-印度数字 `١`）：

    ```text
    缺失 / 非字符串 / 空串 / 非 ASCII / 非纯数字  → 411 completed_courses_upload_length_required
    纯 ASCII 数字但位数 > len(str(MAX)) 或数值 > MAX → 413 completed_courses_upload_too_large
    合法                                          → 该整数
    ```

    ⚠️ 位数先于 `int()` 判定：超长纯数字（数千位）**直接**判 413，
    ⛔ 不构造任意大整数、⛔ 不冒 `ValueError` 变成 500。
    """

    if not isinstance(raw, str) or not raw:
        _reject(ERROR_LENGTH_REQUIRED, "上传必须显式声明 Content-Length。")
    # ⚠️ 不做 `strip()`：带空白的值属于**格式非法**，不是"可容忍的写法"。
    if not raw.isascii() or not raw.isdigit():
        _reject(
            ERROR_LENGTH_REQUIRED,
            "Content-Length 必须是纯 ASCII 十进制数字（⛔ 不接受空白 / 符号 / 小数 / Unicode 数字）。",
        )
    if len(raw) > _MAX_LENGTH_DIGITS:
        # ⛔ 此处**绝不**调用 int()：超长十进制字符串会让 int() 抛 ValueError。
        _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")
    value = int(raw)
    if value > MAX_UPLOAD_BYTES:
        _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")
    return value


def import_completed_courses_xlsx_bytes(
    payload: object,
    *,
    declared_length: object,
    media_type: object,
) -> CompletedCoursesImport:
    """把上传字节变成**已归一化**的已修课程事实（⛔ 不做任何认定）。

    - 媒体类型 / 声明长度 / 实际大小 / 空文件 均在读工作簿**之前**校验；
    - 空工作簿（只有表头、没有任何数据行）⇒ 拒绝（⛔ 不把"导入 0 条"当成功）；
    - `CurriculumNormalizationError` ⇒ `completed_courses_invalid`
      （沿用 reader 的**通用 / 数字位置**文案，⛔ 不含任何单元格取值）。
    """

    normalize_media_type(media_type)

    if not isinstance(payload, (bytes, bytearray)):
        _reject(ERROR_INVALID, "上传内容无法读取。")
    body = bytes(payload)

    if isinstance(declared_length, bool) or not isinstance(declared_length, int):
        _reject(ERROR_LENGTH_REQUIRED, "上传必须声明 Content-Length。")
    if declared_length > MAX_UPLOAD_BYTES:
        _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")
    if declared_length != len(body):
        _reject(ERROR_LENGTH_MISMATCH, "上传字节数与声明的 Content-Length 不一致。")
    if not body:
        _reject(ERROR_EMPTY_UPLOAD, "上传文件为空。")
    if len(body) > MAX_UPLOAD_BYTES:
        _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")

    digest = hashlib.sha256(body).hexdigest()
    source_id = f"{SOURCE_ID_PREFIX}{digest[:_SOURCE_ID_DIGEST_LENGTH]}"

    # ⚠️ 受控临时文件：进程自己的临时目录 + 固定后缀；⛔ 不使用任何调用方字符串作为路径。
    descriptor, name = tempfile.mkstemp(prefix="completed-courses-upload-", suffix=".xlsx")
    temporary_path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
        try:
            courses = load_completed_courses_xlsx(
                temporary_path, source_id=source_id, sheet_name=APPROVED_WORKSHEET
            )
        except CurriculumNormalizationError as exc:
            # reader 的文案只含通用描述与行列位置；⛔ 不含路径与单元格取值。
            _reject(ERROR_INVALID, str(exc))
    finally:
        try:
            os.unlink(temporary_path)
        except OSError:  # pragma: no cover - 删除失败不改变判定结果
            pass

    if not courses:
        _reject(ERROR_NO_RECORDS, "工作簿中没有可导入的已修课程记录。")
    if len(courses) > MAX_COMPLETED_RECORDS:
        _reject(ERROR_TOO_MANY_RECORDS, "工作簿中的记录条数超过上限。")

    return CompletedCoursesImport(
        source_id=source_id,
        artifact_sha256=digest,
        worksheet=APPROVED_WORKSHEET,
        courses=tuple(courses),
    )
