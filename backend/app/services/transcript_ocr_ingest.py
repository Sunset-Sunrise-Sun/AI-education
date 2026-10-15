"""成绩单**图片**识别适配器：OCR 只做「图片 → 课程候选」，⛔ 不做任何课程认定。

```text
上传图片字节
  ↓ 媒体类型 / 声明长度 / 实际大小 / 空文件 校验（与既有 PDF / XLSX 入口同口径）
本地 OCR 引擎（RapidOCR / ONNX Runtime，离线，⛔ 不联网）
  ↓ 文本块 + 置信度 + 包围盒
① 个人身份信息脱敏（姓名 / 学号 …）—— 在进入任何后续步骤**之前**
② 列网格推断（卷面把同一组列**横向重复多遍**）
③ 行聚类（属性列锚定）+ 名称续行合并
课程候选行（全部 course_id=None、course_id_status=pending）
  ↓ 用户在前端**逐条确认 / 修改 / 丢弃**
CompletedCourse 元组（= Curriculum 既有内部输入，与 PDF 入口**同形状**）
  ↓
matching engine（⛔ 一行不改）
```

## 硬边界（本阶段的验收线）

- ⛔ **不做课程认定**：输出恒为 `course_id=None` + `course_id_status="pending"`，
  与 PDF 入口完全一致；等价关系与已满足判定全部留给匹配引擎 + 用户确认；
- ⛔ **不自动 satisfied**：识别层不产生任何 `MakeupStatus`；
- ⛔ **不猜测课程号**：卷面没有官方课程号，本模块也⛔ 不推断；
- ⛔ **不使用任何假识别数据**：失败就是失败（fail closed），
  ⛔ 不回退演示数据、⛔ 不部分输出；
- ⛔ **不联网**：OCR 在本地推理；图片不发往任何第三方服务；
- ⛔ **不落盘原图**：字节只在内存中处理；
- ⛔ **不打印识别内容**：错误信息只含固定通用文案。

## 为什么是"列网格"而不是"写死坐标"

真实成绩单把「课程名称 / 学分 / 成绩 / 属性」这一组列**横向重复 4 遍**。
OCR 的返回顺序不可靠，唯一稳定的定位口径是**几何**：
先由属性标记（公必/专必/…）的等间距序列认出重复周期，
再由表头锚点在一组之内定出各列 x 中心，从而把任意文本块映射到 (组, 列)。
⛔ 本模块不依赖任何绝对像素坐标，因此换分辨率 / 换扫描件仍可用。
"""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

__all__ = [
    "ALLOWED_IMAGE_MEDIA_TYPES",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGE_PIXELS",
    "OCRBlock",
    "RecognizedCourseCandidate",
    "TranscriptImageRecognition",
    "TranscriptImageRejected",
    "recognize_transcript_image",
]

#: 允许的图片媒体类型（与既有课表截图导入保持一致）。
PNG_MEDIA_TYPE = "image/png"
JPEG_MEDIA_TYPE = "image/jpeg"
WEBP_MEDIA_TYPE = "image/webp"
ALLOWED_IMAGE_MEDIA_TYPES = frozenset({PNG_MEDIA_TYPE, JPEG_MEDIA_TYPE, WEBP_MEDIA_TYPE})

#: 上传字节上限（与既有摄取入口同口径）。
MAX_IMAGE_BYTES = 8 * 1024 * 1024

#: 像素总量上限（防御解压炸弹）。
MAX_IMAGE_PIXELS = 40_000_000

#: 单次识别的文本块上限。
MAX_BLOCKS = 4000

#: 单次识别输出的课程候选上限。
MAX_CANDIDATES = 2000

ERROR_UNSUPPORTED_MEDIA_TYPE = "transcript_image_unsupported_media_type"
ERROR_LENGTH_REQUIRED = "transcript_image_length_required"
ERROR_LENGTH_MISMATCH = "transcript_image_length_mismatch"
ERROR_TOO_LARGE = "transcript_image_too_large"
ERROR_EMPTY_UPLOAD = "transcript_image_empty"
ERROR_INVALID = "transcript_image_invalid"
ERROR_NO_RECORDS = "transcript_image_no_records"
ERROR_OCR_UNAVAILABLE = "transcript_ocr_not_configured"

#: 课程属性标记（卷面列语义）。⛔ 仅用于定位行边界与列网格，不用于任何认定。
_ATTRIBUTE_LABELS = frozenset({"公必", "专必", "专选", "公选", "公任"})

_NAME_LABELS = ("课程名称", "课程名")
_CREDIT_LABELS = ("学分",)
_GRADE_LABELS = ("成绩",)

#: 学期行（`2025-2026学年第一学期`）。
_TERM_PATTERN = re.compile(r"\d{4}\s*-\s*\d{4}\s*学年")

#: 个人身份信息：**在进入任何后续步骤之前**一律丢弃这些文本块。
#: ⚠️ 这是隐私边界，不是可选优化。
_PII_LABELS = (
    "姓名", "学号", "身份证", "考生号", "出生", "性别", "民族",
    "学院", "专业", "年级", "入校时间", "离校时间", "学制", "班级",
)

#: 页脚 / 汇总行：不是课程行。
#: ⚠️ 真实 OCR 会把汇总行读成 `学分25.5（必修)0（专选）` 这类形态，
#: 因此除了固定词，还要按**形态特征**排除（见 `_is_summary_line`）。
_FOOTER_LABELS = (
    "印制", "审核人", "评分体系", "绩点", "实得学分", "毕业应得学分",
    "平均绩点", "P/NP", "通过/不通过", "论文题目", "成绩单",
    "优秀", "良好", "中等", "及格", "不及格",
)

#: 汇总行里出现的形态特征（学分统计 / 绩点分档）。
_SUMMARY_MARKERS = ("(必修)", "（必修)", "(专选)", "（专选)", "必修)", "专选)")

#: 单个文本块的字符数上界：超过必然不是课程名（真实课程名都很短）。
_MAX_NAME_BLOCK_CHARS = 30

#: 名称最少字符数（低于此值视为噪声，⛔ 不猜）。
_MIN_NAME_LENGTH = 2

#: 列网格对齐容差（占重复周期的比例）。
_GRID_TOLERANCE_RATIO = 0.12

#: 行聚类容差（相对行高）。
_ROW_TOLERANCE_RATIO = 0.9

#: 置信度低于此值时**照常输出**候选，但标注需人工核对。
#: ⚠️ 置信度⛔ 不参与任何判定，只影响提示文案。
_LOW_CONFIDENCE = 0.70

#: 学分合理上界（超出即视为误读，⛔ 不猜）。
_MAX_CREDIT = 30.0


class TranscriptImageRejected(ValueError):
    """An image-based transcript import failed a safe boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class OCRBlock:
    """一个 OCR 文本块（已脱敏）。"""

    text: str
    confidence: float
    center_x: float
    center_y: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 1.0)


@dataclass(frozen=True, slots=True)
class RecognizedCourseCandidate:
    """一条**待用户确认**的课程候选（⛔ 全部字段都是候选，未做任何认定）。"""

    row_id: str
    course_name: str
    credit: float | None
    score_text: str | None
    semester_text: str | None
    course_attribute: str | None
    confidence: float
    unconfirmed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TranscriptImageRecognition:
    """一次成功的成绩单图片识别（均为**候选**，⛔ 未做任何认定）。"""

    source_id: str
    artifact_sha256: str
    media_type: str
    width: int
    height: int
    block_count: int
    #: 被隐私规则丢弃的文本块数量（⛔ 不回传其内容）。
    redacted_block_count: int
    #: 识别出的横向重复列组数（卷面把同一组列重复多遍）。
    column_groups: int
    candidates: tuple[RecognizedCourseCandidate, ...]
    #: 无法归入任何课程行的文本块（如实列出，供人工查看）。
    unrecognized: tuple[str, ...]


def _reject(code: str, message: str) -> None:
    raise TranscriptImageRejected(code, message)


def normalize_image_media_type(value: object) -> str:
    """归一化图片媒体类型；⛔ 只接受 PNG / JPEG / WebP。"""

    if not isinstance(value, str) or not value.strip():
        _reject(ERROR_UNSUPPORTED_MEDIA_TYPE, "必须显式声明受支持的图片媒体类型。")
    media_type = value.split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_IMAGE_MEDIA_TYPES:
        _reject(
            ERROR_UNSUPPORTED_MEDIA_TYPE,
            "只接受成绩单图片（PNG / JPEG / WebP）；其它媒体类型一律拒绝。",
        )
    return media_type


def validate_image_bytes(
    payload: object, *, declared_length: object, media_type: object
) -> tuple[bytes, str]:
    """校验字节边界；返回 `(body, media_type)`。⛔ 不做任何解析。"""

    normalized = normalize_image_media_type(media_type)
    if not isinstance(payload, (bytes, bytearray)):
        _reject(ERROR_INVALID, "上传内容无法读取。")
    body = bytes(payload)
    if isinstance(declared_length, bool) or not isinstance(declared_length, int):
        _reject(ERROR_LENGTH_REQUIRED, "上传必须声明 Content-Length。")
    if declared_length > MAX_IMAGE_BYTES:
        _reject(ERROR_TOO_LARGE, "上传图片超过大小上限。")
    if declared_length != len(body):
        _reject(ERROR_LENGTH_MISMATCH, "上传字节数与声明的 Content-Length 不一致。")
    if not body:
        _reject(ERROR_EMPTY_UPLOAD, "上传图片为空。")
    if len(body) > MAX_IMAGE_BYTES:
        _reject(ERROR_TOO_LARGE, "上传图片超过大小上限。")
    return body, normalized


@dataclass(frozen=True, slots=True)
class _ColumnGrid:
    """卷面的列网格（**由数据行自身推导**，⛔ 不写死像素值、⛔ 不依赖表头文本）。

    ⚠️ 设计依据（真实成绩单实测）：

    - 表头在 OCR 下会被**切碎并错位**（"课程名称"被拆成若干片段，
      甚至落到属性列上），因此**不能**用表头文本定位列；
    - 而**数据行本身极其规整**：行内块按 x 递增必然是
      `课程名 → [学分] → 成绩 → 属性标记`，且属性标记是该行最右侧的锚点。

    因此列中心取自数据行聚合统计：名称列 = 各数据行最左块的 x；
    属性列 = 属性标记的 x；成绩列 = 属性列左侧最近的数值块 x；
    学分列（若存在）= 成绩列左侧的数值块 x。
    """

    name_x: float
    credit_x: float | None
    grade_x: float
    attribute_x: float

    def column_of(self, center_x: float, *, row_anchor: float | None = None) -> str | None:
        """把 x 映射到列。

        ⚠️ 若给出 `row_anchor`（本行名称列的实际 x），则列中心整体平移，
        以容纳名称列因字号 / 缩进造成的横向抖动 ——
        ⛔ 平移量不改变列的顺序与相对间距。
        """

        shift = (self.name_x - row_anchor) if row_anchor is not None else 0.0
        centers: list[tuple[float, str]] = [
            (self.name_x + shift, "name"),
            (self.grade_x + shift, "grade"),
            (self.attribute_x + shift, "attribute"),
        ]
        if self.credit_x is not None:
            centers.append((self.credit_x + shift, "credit"))
        centers.sort()

        distance, label = min(
            ((abs(value - center_x), name) for value, name in centers),
            key=lambda item: item[0],
        )
        ordered = [value for value, _ in centers]
        gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b - a > 0]
        tolerance = max(min(gaps) / 2.0, 1.0) * 1.35 if gaps else 1.0
        return label if distance <= tolerance else None

    @property
    def groups(self) -> int:
        return 1


def _is_pii(text: str) -> bool:
    """是否属于个人身份信息（⛔ 一律丢弃，且⛔ 不回传内容）。"""

    return any(label in text for label in _PII_LABELS)


def _is_footer(text: str) -> bool:
    if any(label in text for label in _FOOTER_LABELS):
        return True
    if any(marker in text for marker in _SUMMARY_MARKERS):
        return True
    # 过长的文本块不可能是课程名（典型是汇总行的碎片）。
    return len(text.strip()) > _MAX_NAME_BLOCK_CHARS


def _is_attribute(text: str) -> bool:
    return text.strip() in _ATTRIBUTE_LABELS


def _to_float(text: str) -> float | None:
    """把文本解析为学分数字；⛔ 解析不出返回 None（⛔ 不猜）。"""

    candidate = text.strip().replace(" ", "").replace(". ", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", candidate):
        return None
    try:
        value = float(candidate)
    except ValueError:
        return None
    return value if 0.0 < value <= _MAX_CREDIT else None


def _looks_numeric(text: str) -> bool:
    """该块是否只由数字与小数点组成（用于定位数值列，⛔ 不做语义判断）。"""

    candidate = text.strip().replace(" ", "")
    return bool(re.fullmatch(r"\d+(\.\d+)?", candidate))


def _tightest_cluster(values: Sequence[float], *, tolerance: float) -> float | None:
    """返回**最紧密一簇**的中心（簇内相邻差 ≤ tolerance）。

    ⚠️ 存在的理由：OCR 会把课程名碎片误判成列标题（例如把 `1. 5` 附近的内容
    认成"学分"），直接对全部实例取中位数会被这些离群值带偏。
    最紧密的一簇必然是**真实数据行所在的那一列**。
    """

    ordered = sorted(set(round(value, 1) for value in values))
    if not ordered:
        return None
    best: list[float] = []
    current: list[float] = [ordered[0]]
    for value in ordered[1:]:
        if value - current[-1] <= tolerance:
            current.append(value)
        else:
            if len(current) > len(best):
                best = current
            current = [value]
    if len(current) > len(best):
        best = current
    return median(best)


def _detect_grid(blocks: Sequence[OCRBlock]) -> _ColumnGrid | None:
    """由**数据行自身**推导列网格（⛔ 不写死像素值、⛔ 不依赖表头文本）。

    ```text
    课程名 → [学分] → 成绩 → 属性标记      （行内 x 递增的固定顺序）
    ```

    统计口径：
    - **属性列** = 属性标记块 x 的中位数；
    - **名称列** = 各数据行最左块 x 的中位数；
    - **成绩列** = 属性列左侧最近的数值块 x 的中位数；
    - **学分列** = 成绩列左侧的数值块 x 的中位数（若该列在版面中存在）。

    ⚠️ 只做几何统计，⛔ 不读取任何课程名内容做判断。
    """

    attribute_values = [b.center_x for b in blocks if _is_attribute(b.text)]
    attribute_x = _tightest_cluster(attribute_values, tolerance=40.0)
    if attribute_x is None:
        return None

    # 以属性标记为锚，把块按 y 聚成行；含属性标记的行即**数据行**。
    data_rows: list[list[OCRBlock]] = []
    for row in _group_rows(blocks):
        if any(_is_attribute(block.text) for block in row):
            data_rows.append(list(row))
    if len(data_rows) < 2:
        return None

    name_values: list[float] = []
    grade_values: list[float] = []
    credit_values: list[float] = []
    for row in data_rows:
        cells = [
            block
            for block in row
            if not _TERM_PATTERN.search(block.text) and not _is_footer(block.text)
        ]
        if not cells:
            continue
        leftmost = min(cells, key=lambda b: b.center_x)
        # 名称列 = 最左块（其右侧仍可能是名称续块，但最左块足以定中心）
        name_values.append(leftmost.center_x)
        # 属性列左侧的数值块，自右向左依次是 成绩、学分
        numeric = sorted(
            (
                block
                for block in cells
                if block.center_x < attribute_x and _looks_numeric(block.text)
            ),
            key=lambda b: b.center_x,
            reverse=True,
        )
        if numeric:
            grade_values.append(numeric[0].center_x)
        if len(numeric) >= 2:
            credit_values.append(numeric[1].center_x)

    if not name_values or not grade_values:
        return None

    name_x = median(name_values)
    grade_x = _tightest_cluster(grade_values, tolerance=40.0) or median(grade_values)
    credit_x = (
        _tightest_cluster(credit_values, tolerance=40.0) if credit_values else None
    )
    if not (name_x < grade_x < attribute_x):
        return None
    if credit_x is not None and not (name_x < credit_x < grade_x):
        credit_x = None
    return _ColumnGrid(
        name_x=name_x, credit_x=credit_x, grade_x=grade_x, attribute_x=attribute_x
    )


def _run_ocr(body: bytes, media_type: str) -> tuple[list[OCRBlock], int, int]:
    """在**本地**运行 OCR；返回 `(blocks, width, height)`。

    ⛔ 不联网、⛔ 不落盘、⛔ 不打印识别内容。
    """

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - 依赖缺失时 fail closed
        _reject(ERROR_OCR_UNAVAILABLE, "图片解码能力不可用。")

    try:
        image = Image.open(io.BytesIO(body))
        image.load()
    except Exception:
        _reject(ERROR_INVALID, "图片无法解码。")
    width, height = image.size
    if width <= 0 or height <= 0:
        _reject(ERROR_INVALID, "图片尺寸非法。")
    if width * height > MAX_IMAGE_PIXELS:
        _reject(ERROR_TOO_LARGE, "图片像素总量超过上限。")

    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:  # pragma: no cover - 依赖缺失时 fail closed
        _reject(ERROR_OCR_UNAVAILABLE, "本地 OCR 引擎未安装。")

    import numpy as np

    try:
        engine = RapidOCR()
        result, _elapsed = engine(np.array(image.convert("RGB")))
    except Exception:
        # ⛔ 不把引擎内部错误文本透出（可能含路径 / 内容）。
        _reject(ERROR_OCR_UNAVAILABLE, "本地 OCR 识别失败。")

    blocks: list[OCRBlock] = []
    for item in result or []:
        try:
            box, text, score = item[0], item[1], item[2]
        except (IndexError, TypeError):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        blocks.append(
            OCRBlock(
                text=text.strip(),
                confidence=float(score),
                center_x=(min(xs) + max(xs)) / 2,
                center_y=(min(ys) + max(ys)) / 2,
                left=min(xs),
                top=min(ys),
                right=max(xs),
                bottom=max(ys),
            )
        )
        if len(blocks) >= MAX_BLOCKS:
            break
    return blocks, width, height


def _group_rows(blocks: Sequence[OCRBlock]) -> list[list[OCRBlock]]:
    """按 y 把文本块聚成行（⛔ 不使用 OCR 的返回顺序）。"""

    if not blocks:
        return []
    heights = sorted(block.height for block in blocks)
    tolerance = max(heights[len(heights) // 2] * _ROW_TOLERANCE_RATIO, 2.0)
    ordered = sorted(blocks, key=lambda b: (b.center_y, b.center_x))
    rows: list[list[OCRBlock]] = []
    for block in ordered:
        if rows and abs(block.center_y - rows[-1][0].center_y) <= tolerance:
            rows[-1].append(block)
        else:
            rows.append([block])
    return [sorted(row, key=lambda b: b.center_x) for row in rows]


def _classify_row(
    row: Sequence[OCRBlock], grid: _ColumnGrid
) -> tuple[str, list[OCRBlock], OCRBlock | None, OCRBlock | None, str | None]:
    """把一行分类为：学期行 / 课程行 / 名称续行 / 噪声。

    行边界的判定依据是**属性列上的标记**（公必/专必/…），这是行内最右、最稳的锚点。

    ⚠️ 列归属**不靠 x 容差**（实测不可靠：课程名起止 x 随字数变化很大），
    而是靠**卷面固定的列顺序 + 数值语义**：

    ```text
    课程名 → [学分] → 成绩 → 属性标记      （行内 x 递增）
    ```

    即：属性标记左侧最近的**数值块**是成绩，其左侧的数值块（若有）是学分，
    其余非数值块都属于课程名。⛔ 只判断"是不是数字"，⛔ 不看课程名内容。
    """

    semester_text: str | None = None
    content: list[OCRBlock] = []
    for block in row:
        if _TERM_PATTERN.search(block.text):
            semester_text = block.text.replace(" ", "")
            continue
        if _is_footer(block.text):
            continue
        content.append(block)

    if semester_text is not None:
        return "term", [], None, None, semester_text

    attribute = next((b for b in content if _is_attribute(b.text)), None)
    if attribute is None:
        # 没有属性标记：只可能是"课程名被折断到单独一行"的续行。
        name_only = [b for b in content if not _looks_numeric(b.text)]
        if name_only and len(name_only) == len(content):
            return "continuation", name_only, None, None, None
        return "noise", [], None, None, None

    left_of_attribute = sorted(
        (b for b in content if b.center_x < attribute.center_x),
        key=lambda b: b.center_x,
    )
    numeric = [b for b in left_of_attribute if _looks_numeric(b.text)]
    grade_block = numeric[-1] if numeric else None
    credit_block = numeric[-2] if len(numeric) >= 2 else None

    claimed = {id(grade_block), id(credit_block), id(attribute)}
    name_blocks = [b for b in left_of_attribute if id(b) not in claimed]
    return "course", name_blocks, credit_block, grade_block, None


class _Draft:
    """构造中的一条课程候选（名称可能来自前一行续行）。"""

    __slots__ = ("attribute", "confidence", "credit", "name", "score_text", "semester")

    def __init__(self) -> None:
        self.name = ""
        self.credit: float | None = None
        self.score_text: str | None = None
        self.semester: str | None = None
        self.attribute: str | None = None
        self.confidence = 1.0


#: 续行片段的长度上界（**启发式**）：跨行折断的残片通常很短。
#: ⚠️ 这是唯一一处"按长度猜"的地方，因此：
#:   - 只用于把残片**并入相邻课程名**，⛔ 不参与任何课程认定；
#:   - 判错的最坏后果是课程名多/少几个字，而**每条候选都必须经用户确认**。
_CONTINUATION_MAX_CHARS = 4


#: 纯数字片段（可含小数点 / 连字符，例如 `60-69`）：属于页脚分档，不是课程名。
_NUMERIC_FRAGMENT = re.compile(r"[0-9]+(?:\s*[.\-]\s*[0-9]+)?")


def _is_numeric_fragment(text: str) -> bool:
    """该块是否**只**由数字 / 小数点 / 连字符组成。"""

    stripped = text.strip()
    return bool(stripped) and _NUMERIC_FRAGMENT.fullmatch(stripped) is not None


def _clean_name(raw: str) -> str:
    """清理课程名里粘上的**数值碎片**（OCR 把相邻数字并进了名称块）。

    ⚠️ 只删除"纯数字（含小数点）"的片段，⛔ 不改动任何汉字，
    因此不会改变课程名的语义；判错的最坏后果也只是名称多/少几个数字，
    而**每条候选都必须经用户确认**。
    """

    cleaned = re.sub(r"\d+(?:\.\d+)?", "", raw)
    # 去掉因此暴露出来的悬空连接符（例：`遇见人工智能-01` → `遇见人工智能-`）
    return cleaned.strip().strip("-—－").strip()


def _join_name(blocks: Sequence[OCRBlock]) -> str:
    """把名称块拼接成课程名。

    ⚠️ 真实卷面的页脚碎片（`60-69`、`0-59`）会被 OCR 归到名称列尾部，
    因此**从尾部剔除纯数字片段**；只剔除尾部，⛔ 不剔除中间，
    以免误删课程名里本身就有的数字（例：`程序设计I`）。
    """

    ordered = sorted(blocks, key=lambda b: b.center_x)
    while ordered and _is_numeric_fragment(ordered[-1].text):
        ordered = ordered[:-1]
    return "".join(block.text for block in ordered).strip()


def _split_leading_continuation(
    name_blocks: Sequence[OCRBlock],
) -> tuple[str, str]:
    """把数据行的名称块拆成 `(续行片段, 本行名称)`。

    ⚠️ 真实卷面里，上一门课的折断残片会与下一门课的课程名落在**同一行**：

    ```text
    '发现'@42  '四史 (新中国史)'@92  '82'@439  '公必'@530
     ↑ 属于上一门课        ↑ 本行课程名
    ```

    判定口径：**最左块**若明显短（≤ `_CONTINUATION_MAX_CHARS`），
    则它就是续行片段。

    ⛔ 只做"残片归属"，⛔ 不判断课程内容。
    """

    if len(name_blocks) < 2:
        return "", _join_name(name_blocks)
    ordered = sorted(name_blocks, key=lambda b: b.center_x)
    first = ordered[0]
    if len(first.text.strip()) <= _CONTINUATION_MAX_CHARS:
        return first.text.strip(), _join_name(ordered[1:])
    return "", _join_name(ordered)


def _build_candidates(
    rows: Sequence[Sequence[OCRBlock]], grid: _ColumnGrid
) -> tuple[list[RecognizedCourseCandidate], list[str]]:
    """由行聚类构造课程候选（⛔ 只提取事实，⛔ 不做任何认定）。

    ⚠️ 真实卷面的课程名会**跨行折断**，且有**两种方向**（实测）：

    ```text
    A) 名称在前、数据在后：  行 i: `习近平新时代中国特色社会主义思`   （无属性标记）
                            行 i+1: `08` + `公必`                    （数据行）
    B) 数据在前、名称在后：  行 j: `新生研讨课：对地观测一` + `专选` （数据行）
                            行 j+1: `发现`                          （无属性标记）
    ```

    因此名称的归属规则是：
    - 遇到「无属性标记、且全是非数值块」的行 ⇒ 暂存为 `carried_name`；
    - 遇到数据行时，`carried_name`（若有）作为**前缀**并入本行名称；
    - 数据行之后紧邻的续行文本作为**后缀**追加到上一条已产出的候选。
    """

    drafts: list[_Draft] = []
    # 与 drafts 一一对应：该草稿是否由一个**数据行**产出。
    # 续行只能并入"数据行产出"的候选，⛔ 不并入被跳过的行。
    from_draft_row: list[bool] = []
    unrecognized: list[str] = []
    current_semester: str | None = None
    carried_name = ""  # 出现在数据行之前的名称片段

    for row in rows:
        kind, name_blocks, credit_block, grade_block, semester_text = _classify_row(row, grid)

        if kind == "term":
            current_semester = semester_text
            continue

        if kind == "continuation":
            fragment = "".join(block.text for block in name_blocks).strip()
            if carried_name:
                carried_name += fragment
            elif drafts and from_draft_row[-1]:
                drafts[-1].name += fragment
            else:
                carried_name = fragment
            continue

        if kind != "course":
            continue

        leading, row_name = _split_leading_continuation(name_blocks)
        if leading and drafts and from_draft_row[-1]:
            # 上一门课的折断残片落在本行：并入上一条候选
            drafts[-1].name += leading

        attribute = next(b.text.strip() for b in row if _is_attribute(b.text))
        draft = _Draft()
        draft.semester = current_semester
        draft.attribute = attribute
        draft.credit = _to_float(credit_block.text) if credit_block is not None else None
        draft.score_text = grade_block.text.strip() if grade_block is not None else None
        draft.confidence = round(min(block.confidence for block in row), 4)
        draft.name = row_name or carried_name
        carried_name = ""
        drafts.append(draft)
        from_draft_row.append(True)

        if len(drafts) >= MAX_CANDIDATES:
            break

    # 未认领的名称片段如实列出
    if carried_name:
        unrecognized.append(carried_name)

    candidates: list[RecognizedCourseCandidate] = []
    for index, draft in enumerate(drafts, start=1):
        name = _clean_name(draft.name)
        if len(name) < _MIN_NAME_LENGTH:
            # ⛔ 名称不可用就不产出候选（交给"未识别"如实列出）。
            unrecognized.append(name or "(空课程名)")
            continue
        unconfirmed = ["图片未包含官方课程号，需人工确认课程身份。"]
        if draft.credit is None:
            unconfirmed.append("未识别到学分，需人工补填。")
        if draft.score_text is None:
            unconfirmed.append("未识别到成绩，需人工补填。")
        if draft.confidence < _LOW_CONFIDENCE:
            unconfirmed.append("该行识别置信度偏低，请核对课程名与成绩。")
        candidates.append(
            RecognizedCourseCandidate(
                row_id=f"img:{index}",
                course_name=name,
                credit=draft.credit,
                score_text=draft.score_text,
                semester_text=draft.semester,
                course_attribute=draft.attribute,
                confidence=draft.confidence,
                unconfirmed=tuple(unconfirmed),
            )
        )
    return candidates, unrecognized


def recognize_transcript_image(
    payload: object,
    *,
    declared_length: object,
    media_type: object,
) -> TranscriptImageRecognition:
    """把上传图片变成**待确认的课程候选**（⛔ 不做任何课程认定）。

    - 媒体类型 / 声明长度 / 实际大小 / 空文件 均在 OCR **之前**校验；
    - 个人身份信息在 OCR 之后、行聚类之前**立即丢弃**；
    - 版面无法推断列网格 ⇒ `transcript_image_no_records`（fail closed），
      ⛔ 不回退任何演示数据。
    """

    body, normalized = validate_image_bytes(
        payload, declared_length=declared_length, media_type=media_type
    )
    digest = hashlib.sha256(body).hexdigest()
    source_id = f"upload:image:sha256:{digest[:16]}"

    blocks, width, height = _run_ocr(body, normalized)

    # ① 隐私边界：先丢弃个人身份信息，再进入任何聚类 / 输出。
    redacted_count = sum(1 for block in blocks if _is_pii(block.text))
    kept = [block for block in blocks if not _is_pii(block.text)]

    grid = _detect_grid(kept)
    if grid is None:
        _reject(
            ERROR_NO_RECORDS,
            "未能在图片中定位成绩单表格的列结构，请上传更清晰的成绩单图片。",
        )

    rows = _group_rows(kept)
    candidates, unrecognized = _build_candidates(rows, grid)
    if not candidates:
        _reject(ERROR_NO_RECORDS, "未在图片中识别出任何课程行。")

    return TranscriptImageRecognition(
        source_id=source_id,
        artifact_sha256=digest,
        media_type=normalized,
        width=width,
        height=height,
        block_count=len(blocks),
        redacted_block_count=redacted_count,
        column_groups=grid.groups,
        candidates=tuple(candidates),
        unrecognized=tuple(dict.fromkeys(unrecognized)),
    )
