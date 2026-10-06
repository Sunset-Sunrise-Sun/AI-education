"""Read the verified SYSU undergraduate transcript PDF layout, locally only.

```text
PDF bytes
  ↓ PyMuPDF extracts positioned words (no OCR, no network, no script execution)
words → rows → 表格列（列边界由表头 x 坐标推导，而不是写死坐标）
  ↓
term / course_name / credits / grade / course_attribute
  ↓ normalize_completed_courses  →  CompletedCourse 元组（Curriculum 既有内部输入）
```

## 支持范围（⛔ 不要过度声称）

本模块只支持**当前已核验的中山大学本科成绩单 PDF 版面**（Case A 样本）：

- 表格以**四列一组**（`课程名称` / `学分` / `成绩` / `课程属性`）横向重复平铺；
- 学期行为 `2025-2026学年 第一学期` 形态；
- 成绩为数字（0–100）或 `P` / `NP`；
- 学分为整数或一位小数。

⛔ **不支持**：扫描件 / 图片型 PDF（无 OCR）、其它学校、其它版本的中大成绩单、
其它语言版面。版面不符时**一律 fail closed**，⛔ 不猜测、⛔ 不部分输出。

## 为什么解析后 `course_id` 为空

成绩单**不提供**官方课程号。本模块**不构造、不推断、不借用**任何课程号：
所有记录以 `CourseIdStatus.PENDING` + `course_id=None` 输出，由既有的
`app/curriculum/matching.py` 按"身份未确认"保守处理（⛔ 不会因为课程名相似而自动抵认）。
课程号只能由人工在官方来源侧（如"成绩转换"页面）补全，⛔ 不在本模块。

内部模型 `CompletedCourse` **本来就允许** `course_id=None`，因此本模块
⛔ 不新增中间对象、⛔ 不改任何内部或公共契约。

## 隐私

- ⛔ 不读取、不返回、不记录姓名 / 学号 / 学院 / 专业 / 绩点 / 排名：
  表头以上的学生信息区块在解析时直接丢弃，不进入任何中间结构；
- ⛔ 错误信息只含**固定通用文案**，⛔ 不含课程名、成绩、学号、姓名、页内位置取值；
- ⛔ 无 `print` / `logging`，⛔ 不写任何临时文件；PDF 字节只在内存中解析；
- ⛔ 解析器告警被抑制（告警文案可能夹带字体 / 内容片段）；
- ⛔ 不执行 PDF 内嵌脚本 / 动作。
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from app.curriculum.completed_courses import CompletedCourse, normalize_completed_courses
from app.curriculum.errors import CurriculumNormalizationError

__all__ = [
    "TranscriptParse",
    "TranscriptRecord",
    "completed_records_for",
    "load_completed_courses_pdf",
    "parse_transcript_pdf",
    "parse_transcript_pdf_bytes",
]

#: 表格列头（已核验版面）。顺序即打印顺序。
_COLUMN_LABELS = ("课程名称", "学分", "成绩", "课程属性")

#: 成绩单标题；用于确认拿到的是**本版面**的成绩单，而不是别的 PDF。
_TRANSCRIPT_TITLE = "本科生成绩单"

#: 学期行必须同时出现的两段文字（`2025-2026学年` + `第一学期`）。
_YEAR_MARKER = "学年"
_TERM_MARKERS = (
    "第一学期", "第二学期", "第三学期", "第四学期",
    "春季学期", "秋季学期", "春夏学期", "秋冬学期",
)

#: 课程属性的已知取值；其余文本⛔ 不得冒充课程属性。
_ATTRIBUTE_VALUES = ("公必", "公选", "专必", "专选", "必修", "选修", "限选", "任选")

#: 规模上限：异常 / 恶意 PDF 不得让解析无界增长。
_MAX_PAGES = 20
_MAX_WORDS_PER_PAGE = 20000
_MAX_COURSES = 2000

#: 学分的合理区间；超出即视为**不是**学分单元格。
_MAX_PLAUSIBLE_CREDIT = 30.0

#: 同一基线 / 同一行的容差，以及列归属容差（PDF 用户单位，非像素）。
#: ⚠️ 同一行的四个单元格共享一个基线；相邻表格行相距约 9.4 个单位。
_LINE_TOLERANCE = 2.0
_X_TOLERANCE = 3.0
#: 表头带容差：已核验版面的表头分**两行**打印
#: （第一行 `课程名称 学分 成绩 课程`，第二行 `属性`），两行相距约 9.4 个单位，
#: 而表头与学期行相距约 9.2、与第一门课程相距约 18。取 10.0 正好只收表头自身。
_HEADER_BAND_TOLERANCE = 10.0
#: 名称续行与名称行、名称行与数据行的最大纵向间距。
_NAME_CONTINUATION_GAP = 12.0
_NAME_TO_DATA_GAP = 14.0
#: 名称续行的最大长度：更长的文本视为**新的课程名**，而不是上一门课的续行。
_MAX_CONTINUATION_LENGTH = 16

#: 明显属于汇总 / 页脚 / 说明的文字；这些**绝不能**变成课程名。
_REJECTED_NAME_TOKENS = (
    "学分", "绩点", "平均", "毕业", "应得", "实得", "审核", "印制",
    "评分体系", "题目", "总学分", "备注", "通过", "不通过",
)

_GRADE_VALUES = frozenset({
    "P", "NP", "合格", "不合格", "优秀", "良好", "中等", "及格", "不及格", "通过", "不通过",
})
_CREDIT_PATTERN = r"[0-9]{1,2}(?:\.[0-9])?"
_GRADE_PATTERN = r"[0-9]{1,3}|P|NP"


def _fail(message: str) -> NoReturn:
    """Fail closed with a fixed, privacy-free message."""

    raise CurriculumNormalizationError(message) from None


@dataclass(frozen=True, slots=True)
class TranscriptRecord:
    """One transcript course row, before any Curriculum interpretation.

    ``grade`` 是成绩单上的**原始成绩文本**（数字或 ``P`` / ``NP``），仅用于展示与
    审计；⛔ 不参与任何课程认定，⛔ 不推断原专业学分等级。
    ``course_attribute`` 是成绩单原始"课程属性"文本（提取不到时为 ``UNKNOWN``）。
    """

    term: str
    course_name: str
    credit: float
    grade: str
    course_attribute: str


@dataclass(frozen=True, slots=True)
class TranscriptParse:
    """Result of parsing the verified transcript layout.

    ⛔ 不含姓名 / 学号 / 学院 / 专业 / 绩点 / 排名，⛔ 不含课程号。
    """

    records: tuple[TranscriptRecord, ...]
    page_count: int
    columns_seen: int
    terms: tuple[str, ...]
    skipped_footer_lines: int


@dataclass(frozen=True, slots=True)
class _Word:
    """One positioned word. Never persisted outside the parse."""

    x: float
    right: float
    y: float
    text: str


@dataclass(frozen=True, slots=True)
class _Row:
    """A group of words sharing one printed baseline."""

    y: float
    words: tuple[_Word, ...]

    def text_in(self, lower: float, upper: float) -> str:
        """Join the words whose left edge falls inside ``[lower, upper)``."""

        return "".join(
            word.text for word in self.words if lower <= word.x < upper
        )


def _page_words(page: object) -> list[_Word]:
    """Extract positioned words from one page.

    ⚠️ 使用 ``PyMuPDF`` 的单词级坐标：同一表格行的四个单元格共享**同一个**基线，
    因此日期 / 成绩 / 属性天然对齐；``pypdf`` 的字符级回调按字体给出不同的基线偏移，
    会让同一行错位约 8 个用户单位，无法可靠地按行归并。
    """

    try:
        raw = page.get_text("words")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - 任何解码失败都必须 fail closed
        _fail("transcript: unreadable PDF text layer")
    if not isinstance(raw, (list, tuple)):
        _fail("transcript: unreadable PDF text layer")
    if len(raw) > _MAX_WORDS_PER_PAGE:
        _fail("transcript: page text limit exceeded")

    words: list[_Word] = []
    for entry in raw:
        try:
            x0, y0, x1, _y1, text = entry[0], entry[1], entry[2], entry[3], entry[4]
        except (IndexError, TypeError):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            words.append(_Word(
                x=round(float(x0), 2),
                right=round(float(x1), 2),
                y=round(float(y0), 2),
                text=text.strip(),
            ))
        except (TypeError, ValueError):
            continue
    return words


def _rows_per_page(page: object) -> list[_Row]:
    """Group one page's words into printed rows."""

    words = sorted(_page_words(page), key=lambda word: (word.y, word.x))
    rows: list[list[_Word]] = []
    for word in words:
        if rows and abs(word.y - rows[-1][0].y) <= _LINE_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [
        _Row(y=min(item.y for item in group), words=tuple(sorted(group, key=lambda w: w.x)))
        for group in rows
    ]


def _row_text(row: _Row) -> str:
    return "".join(word.text for word in row.words)


@dataclass(frozen=True, slots=True)
class _Band:
    """One printed column group: name / credit / grade / attribute columns."""

    name_x: float
    credit_x: float
    grade_x: float
    attribute_x: float


def _read_bands(rows: Sequence[_Row]) -> tuple[list[_Band], float]:
    """Derive the repeated column groups from the table header.

    Returns the bands plus the y below which course rows start.

    已核验版面的表头分两行打印：第一行是 ``课程名称`` / ``学分`` / ``成绩`` / ``课程``，
    第二行是 ``属性``。因此先按"包含三个以上列头"定位表头行，再把它同组的相邻行
    （``课程`` / ``属性`` 行）合起来看；``课程属性`` 的起点取 ``课程`` 的 x。
    """

    anchor = None
    for row in rows:
        hits = sum(1 for label in _COLUMN_LABELS if label in _row_text(row))
        if hits >= 3:
            anchor = row
            break
    if anchor is None:
        _fail("transcript: course table header is missing")

    label_rows = [
        row for row in rows
        if any(label in _row_text(row) for label in _COLUMN_LABELS + ("课程", "属性"))
    ]
    below = sorted((row for row in label_rows if row.y >= anchor.y), key=lambda row: row.y)
    band_rows = [below[0]]
    for row in below[1:]:
        if row.y - band_rows[-1].y > _HEADER_BAND_TOLERANCE:
            break
        band_rows.append(row)
    bottom = max(row.y for row in band_rows)

    name_x = _first_word_x([anchor], "课程名称")
    credit_x = _first_word_x([anchor], "学分")
    grade_x = _first_word_x([anchor], "成绩")
    attribute_x = _first_word_x(band_rows, "课程", "属性")
    if None in (name_x, credit_x, grade_x, attribute_x):
        _fail("transcript: course table header is missing")
    if not (name_x < credit_x < grade_x < attribute_x):
        _fail("transcript: course table header is not the verified layout")

    # 每一列分组的起点：三个**固定**列头（课程名称 / 学分 / 成绩）都带列偏移，
    # 因此"起点" = 同一条表头行上，三个列头按各自偏移两两对齐的位置。
    offsets = (credit_x - name_x, grade_x - name_x, attribute_x - name_x)
    name_positions = _all_word_x([anchor], "课程名称")
    credit_positions = _all_word_x([anchor], "学分")
    starts = [
        origin for origin in sorted(name_positions)
        if any(abs(candidate - (origin + offsets[0])) <= _X_TOLERANCE for candidate in credit_positions)
    ]
    if len(starts) != 4:
        _fail("transcript: course table header is not the verified layout")

    return [
        _Band(
            name_x=origin,
            credit_x=origin + offsets[0],
            grade_x=origin + offsets[1],
            attribute_x=origin + offsets[2],
        )
        for origin in starts
    ], bottom


def _first_word_x(rows: Sequence[_Row], *words: str) -> float | None:
    """Return the leftmost x of any of ``words`` inside the header band."""

    found: list[float] = []
    for row in rows:
        for word in row.words:
            if word.text in words:
                found.append(word.x)
    return min(found) if found else None


def _all_word_x(rows: Sequence[_Row], word: str) -> list[float]:
    """Return every x where exactly ``word`` appears inside the header band."""

    return [w.x for row in rows for w in row.words if w.text == word]


def _parse_number(text: str) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return value


def _is_term_line(text: str) -> bool:
    collapsed = text.replace(" ", "")
    return _YEAR_MARKER in collapsed and any(marker in collapsed for marker in _TERM_MARKERS)


def _rejected_name(text: str) -> bool:
    """Return whether a name-column text must never be treated as a course name.

    ⛔ 汇总行 / 页脚 / 说明行（``学分 …`` / ``绩点 …`` / ``毕业应得学分 …`` /
    ``实得学分 …`` / ``主修全部课程平均绩点 …`` / ``审核人:``）在这里被排除。
    ⚠️ 刻意**不**按"含数字"排除：已核验版面里存在 ``遇见人工智能-o1`` 这类
    合法课程名。
    """

    collapsed = text.replace(" ", "")
    if not collapsed:
        return True
    if collapsed.isdigit():
        return True
    return any(token in collapsed for token in _REJECTED_NAME_TOKENS)


def _parse_grade(text: str) -> str | None:
    collapsed = text.replace(" ", "")
    if collapsed.isdigit():
        return collapsed if 0 <= int(collapsed) <= 100 else None
    return collapsed if collapsed in _GRADE_VALUES else None


@dataclass(frozen=True, slots=True)
class _NameEntry:
    """A course-name line plus the wrapped continuation lines that belong to it."""

    y: float
    text: str
    continuation_ys: tuple[float, ...]


def _parse_band(rows: Sequence[_Row], band: _Band) -> tuple[list[TranscriptRecord], int]:
    """Read one printed column group from top to bottom.

    已核验版面的列组从左到右依次是 ``课程名称`` / ``学分`` / ``成绩`` / ``课程属性``；
    名称格与三个数据格共享同一基线，而**换行的课程名**会产生
    "名称行 → 数据行 → 名称续行" 的形态（续行落在数据行之下）。

    因此本函数分两步：

    1. 先独立收集**名称行**与**数据行**——同一行既可能是名称行、也可能是数据行，
       两者都要保留，⛔ 不能二选一；
    2. 每个数据行配对它上方最近的、尚未被占用的名称行（允许名称行略低于数据行，
       即换行名称的续行）。

    ⛔ 学期行、每学期末的 ``学分 …`` / ``绩点 …`` 汇总行、页脚成绩说明、平均绩点行
    都**不会**进入结果（没有成对的学分 + 成绩单元格）；⛔ 没有名称的数据行、
    没有数据行的名称行都不会被猜成课程。
    """

    current_term: str | None = None
    names: list[_NameEntry] = []
    data: list[tuple[float, float, str, str]] = []
    skipped = 0
    #: 上一条**无名称数据行**的 y；换行课程名的续行必须紧跟在它之后。
    nameless_data_y: float | None = None

    # 列边界取相邻列头的中点，因此每列只读到自己那一格。
    name_upper = (band.name_x + band.credit_x) / 2
    credit_upper = (band.credit_x + band.grade_x) / 2
    grade_upper = (band.grade_x + band.attribute_x) / 2

    for row in rows:
        # ⚠️ 学期行跨越名称列与学分列（``2025-2026学年`` + ``第一学期``），
        # 因此必须用**整行**文本判定，而不是只取名称列。
        if _is_term_line(_row_text(row)):
            current_term = _row_text(row).replace(" ", "")
            nameless_data_y = None
            continue

        name_text = row.text_in(-1.0, name_upper)
        credit = _parse_number(row.text_in(name_upper, credit_upper))
        grade = _parse_grade(row.text_in(credit_upper, grade_upper))
        if credit is not None and grade is not None and 0.0 <= credit <= _MAX_PLAUSIBLE_CREDIT:
            # ⚠️ 学期必须**随该数据行一起**记录：`current_term` 会在后续行继续变化，
            # 若在最后统一取值，全部记录都会被打上最后一个学期。
            data.append((
                row.y,
                current_term or "UNKNOWN-TERM",
                credit,
                grade,
                row.text_in(grade_upper, float("inf")),
            ))

        if not name_text.strip() or _rejected_name(name_text):
            if name_text.strip():
                skipped += 1
            nameless_data_y = row.y
            continue

        # ⚠️ 只有"紧跟在**无名称数据行**之后、间距不超过一个行高"的名称文本才是
        # 换行课程名的续行：已核验版面把换行的后半段画在数据行之下的另一条基线上
        # （`……探索与` / 数据行 / `发现`）。普通课程名自带数据，绝不合并，
        # 否则会把相邻两门课粘成一门。
        if (
            nameless_data_y is not None
            and names
            and row.y - nameless_data_y <= _NAME_CONTINUATION_GAP
            and len(name_text) <= _MAX_CONTINUATION_LENGTH
        ):
            previous = names[-1]
            names[-1] = _NameEntry(
                y=previous.y,
                text=previous.text + name_text,
                continuation_ys=previous.continuation_ys + (row.y,),
            )
        else:
            names.append(_NameEntry(y=row.y, text=name_text, continuation_ys=()))
        nameless_data_y = None

    records: list[TranscriptRecord] = []
    used: set[int] = set()
    for y, term, credit, grade, attribute in data:
        name_index = None
        for index in range(len(names) - 1, -1, -1):
            if index in used:
                continue
            if names[index].y - y > _LINE_TOLERANCE:
                # 只有换行名称的续行才会落在数据行之下。
                continue
            if y - names[index].y > _NAME_TO_DATA_GAP:
                break
            name_index = index
            break
        if name_index is None:
            skipped += 1
            continue
        used.add(name_index)

        collapsed = names[name_index].text.replace(" ", "")
        if not collapsed:
            skipped += 1
            continue
        records.append(TranscriptRecord(
            term=term,
            course_name=collapsed,
            credit=credit,
            grade=grade,
            course_attribute=_attribute_value(attribute),
        ))

    return records, skipped


def _attribute_value(text: str) -> str:
    collapsed = text.replace(" ", "")
    for value in _ATTRIBUTE_VALUES:
        if collapsed == value:
            return value
    for value in _ATTRIBUTE_VALUES:
        if collapsed.startswith(value):
            return value
    return "UNKNOWN"


def parse_transcript_pdf_bytes(payload: object) -> TranscriptParse:
    """Parse the verified transcript layout into term-grouped records.

    ⛔ 不做课程认定、⛔ 不生成课程号、⛔ 不落盘。版面不符即抛
    :class:`CurriculumNormalizationError`（固定文案，不含任何输入取值）。
    """

    if not isinstance(payload, (bytes, bytearray)):
        _fail("transcript: expected PDF bytes")
    body = bytes(payload)
    if not body:
        _fail("transcript: empty PDF")
    if not body.lstrip()[:5] == b"%PDF-":
        _fail("transcript: not a PDF document")

    try:
        import pymupdf
    except ImportError:  # pragma: no cover - 运行环境缺少解析库
        _fail("transcript: PDF support is not installed in this environment")

    try:
        document = pymupdf.open(stream=body, filetype="pdf")
    except Exception:  # noqa: BLE001 - 第三方解码异常一律 fail closed
        _fail("transcript: malformed PDF")

    records: list[TranscriptRecord] = []
    columns_seen = 0
    skipped_footer = 0
    seen_title = False
    try:
        try:
            page_count = document.page_count
        except Exception:  # noqa: BLE001
            _fail("transcript: malformed PDF")
        if page_count == 0:
            _fail("transcript: empty PDF")
        if page_count > _MAX_PAGES:
            _fail("transcript: page count limit exceeded")

        for page_index in range(page_count):
            try:
                # ⛔ 抑制解析器告警：告警可能夹带字体 / 内容片段文案，绝不能外泄。
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    rows = _rows_per_page(document.load_page(page_index))
            except CurriculumNormalizationError:
                raise
            except Exception:  # noqa: BLE001
                _fail("transcript: malformed PDF")

            if not seen_title:
                if any(_TRANSCRIPT_TITLE in _row_text(row) for row in rows):
                    seen_title = True
                else:
                    _fail("transcript: unsupported layout (transcript title not found)")

            bands, header_bottom = _read_bands(rows)
            columns_seen += len(bands)
            # 表头以上的学生信息区块（姓名 / 学号 / 学院 / 专业）在这里被整体丢弃。
            body_rows = [row for row in rows if row.y > header_bottom + _LINE_TOLERANCE]

            for band in bands:
                band_records, skipped = _parse_band(body_rows, band)
                records.extend(band_records)
                skipped_footer += skipped
    finally:
        try:
            document.close()
        except Exception:  # noqa: BLE001 - 关闭失败不改变判定结果
            pass

    if not records:
        _fail("transcript: no course table rows found")
    if len(records) > _MAX_COURSES:
        _fail("transcript: course row limit exceeded")

    terms: list[str] = []
    for record in records:
        if record.term not in terms:
            terms.append(record.term)

    return TranscriptParse(
        records=tuple(records),
        page_count=page_count,
        columns_seen=columns_seen,
        terms=tuple(terms),
        skipped_footer_lines=skipped_footer,
    )


def parse_transcript_pdf(path: Path | str) -> TranscriptParse:
    """Parse a local transcript PDF file (read-only, nothing persisted)."""

    if not isinstance(path, (str, Path)):
        _fail("transcript: invalid input path")
    try:
        body = Path(path).read_bytes()
    except (OSError, ValueError, RuntimeError):
        _fail("transcript: unreadable PDF file")
    return parse_transcript_pdf_bytes(body)


def completed_records_for(parsed: TranscriptParse) -> list[dict[str, object]]:
    """Project parsed rows onto the existing completed-course input contract.

    ⛔ ``course_id`` 恒为 ``None`` + ``pending``：成绩单没有官方课程号，
    本模块也不构造替代品。
    """

    return [
        {
            "course_id": None,
            "course_name": record.course_name,
            "credit": record.credit,
            "semester": record.term,
            "passed": record.grade not in {"NP", "不合格", "不及格", "不通过"},
            "course_type": (
                record.course_attribute if record.course_attribute != "UNKNOWN" else None
            ),
            "course_id_status": "pending",
            "id_match_source": None,
            "source_record": f"pdf:{index}",
            "notes": f"grade={record.grade}",
        }
        for index, record in enumerate(parsed.records, start=1)
    ]


def load_completed_courses_pdf(
    path: Path | str, *, source_id: str
) -> tuple[CompletedCourse, ...]:
    """Read the verified transcript layout and return completed-course facts.

    Produces the **existing** Curriculum internal input (``CompletedCourse``);
    ⛔ 不新增中间模型、⛔ 不做认定、⛔ 不改任何公共契约。
    """

    normalize_completed_courses([], source_id=source_id)
    return normalize_completed_courses(
        completed_records_for(parse_transcript_pdf(path)), source_id=source_id
    )
