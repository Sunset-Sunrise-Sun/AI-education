/**
 * 学航·转衔 —— SYSU 开课数据「显式触发」浏览器端采集器（Phase 2B-2C1A）
 * ================================================================
 *
 * 定位
 * ----
 * 本文件是 **SYSU-specific Transport 的浏览器侧实现**。
 * 它提供三件事：
 *   1. `collect()` —— 串行取页 → 最小化字段 + 脱敏 → 产出本地 Capture Bundle；
 *   2. `diagnoseSchedulePresence()` —— **只取第 1 页一次**的**结构诊断**（只统计，不产出数据）；
 *   3. `diagnoseMissingScheduleCorrelation()` —— 同样**只取第 1 页一次**的
 *      **相关性诊断**：比较"缺 `teachingTimePlaceStr`"与"该字段非空"两组 row
 *      的**字段聚合结构**，用来看前者是否表现出一致的结构特征。
 *
 * ⛔ 本文件**不实现**任何后端直连学校的认证 HTTP 客户端。
 * 认证完全交给浏览器既有的登录状态（`credentials: "same-origin"`），
 * 本采集器**不读取、不保存、不打印、不导出**任何浏览器端认证状态。
 *
 * ⛔ 加载脚本 ≠ 开始采集
 * ---------------------
 * 加载本文件**不会**发送任何请求：没有顶层调用、没有定时轮询、没有页面加载钩子。
 * 用户必须在控制台**显式调用**：
 *
 *     await window.XuehangSysuCollector.collect({ semester: "2026-1" })
 *     await window.XuehangSysuCollector.diagnoseSchedulePresence({ semester: "2026-1" })
 *     await window.XuehangSysuCollector.diagnoseMissingScheduleCorrelation({ semester: "2026-1" })
 *
 * 默认只跑 2 页 smoke test；要跑更多页必须显式提高 `maxPages`，并会弹出确认框。
 *
 * 取出结果：
 *
 *     const result = await window.XuehangSysuCollector.collect({ semester: "2026-1" });
 *     const text = window.XuehangSysuCollector.toJson(result);   // 裸 Capture Bundle
 *
 * `toJson()` 输出的**顶层就是** `format` / `semester` / `first_page_no` / `page_size` / `pages`，
 * 可直接交给 Python 的 `load_capture_bundle(...)`。
 *
 * ⛔ 参数归属
 * ----------
 * `pageSize = 200` 与 `firstPageNo = 1` 是 **SYSU 已验证的专有取值**，只属于本 Transport，
 * **不会**反向写进通用 `backend/app/course_data/pagination.py`。
 * `firstPageNo` 被**锁定为 1**：传入其它起始页会在发请求之前直接失败
 * （通用多起始页能力留在 backend 分页核心，不在这里放开）。
 *
 * ⛔ 结构诊断的定位
 * ----------------
 * `diagnoseSchedulePresence()` 是**取证**，**不是** workaround：
 * 它只统计 `teachingTimePlaceStr` 的存在形态，**不**改造数据、
 * **不**放宽 `collect()` 的 fail-closed 行为、**不**产出 Capture Bundle。
 *
 * ⛔ 完整性归属
 * ------------
 * 本采集器**不判断** completeness。它只负责安全地取回并脱敏，
 * 最终 `complete` / `partial` 由 Python Pagination Core 依据证据链判定。
 *
 * ⛔ 产物归属
 * ----------
 * 采集结果仍是 **Real Sanitized Capture**：不得提交 Git、不得放入 `mock_data/`、
 * 不得作为测试 fixture、不得复制进 docs / worklog。
 */

(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // 常量
  // ---------------------------------------------------------------------

  /** 只允许在本人已登录的教务页面上运行。 */
  var ALLOWED_HOSTNAME = "jwxt.sysu.edu.cn";

  /** 已确认的请求路径（same-origin relative URL）。 */
  var ENDPOINT_PATH =
    "/jwxt/schedule/agg/schoolOpeningCoursesSchedule/querySchoolOpeningCourses";

  /** SYSU 已验证：起始页码为 1。 */
  var FIRST_PAGE_NO = 1;

  /** SYSU 已验证：单页最大支持 200（负责人人工确认）。 */
  var MAX_PAGE_SIZE = 200;

  /** SYSU 已验证：pageSize=200 请求成功。 */
  var DEFAULT_PAGE_SIZE = 200;

  /** 串行请求间隔：默认 1500ms，下限 1000ms。 */
  var DEFAULT_DELAY_MS = 1500;
  var MIN_DELAY_MS = 1000;

  /** 默认只做 2 页 smoke test；50 是**客户端安全上限**，不是学校系统限制。 */
  var DEFAULT_MAX_PAGES = 2;
  var ABSOLUTE_MAX_PAGES = 50;

  /** Capture Bundle 格式标识（Course Data **内部**交换格式，不是公共 Schema）。 */
  var CAPTURE_FORMAT = "sysu-opening-courses-capture-v1";

  /**
   * 输出前**只保留** Python importer 真正需要的字段 ——
   * 这是 Capture row **允许出现**的全部字段（文档口径 + 守卫测试锚点）。
   *
   * ⚠️ 其中 `teachingTimePlaceStr` 是**条件字段**（DG-07B）：只有原属性存在时才出现，
   * 因此实际最小化循环用的是下面的 `REQUIRED_ROW_FIELDS`。
   */
  var KEPT_ROW_FIELDS = [
    "courseNum",
    "courseName",
    "classNumber",
    "yearTerm",
    "score",
    "limitNumber",
    "selectedNumber",
    "teachingTimePlaceStr"
  ];

  /**
   * 其中**必须存在**的 7 个基础字段：缺任意一个 → 整体 FAIL。
   *
   * ⚠️ **DG-07B 起，`teachingTimePlaceStr` 不再属于"必须存在"集合**：
   * 真实证据（C1B / C1C / C1D）表明该属性**可能真的不存在**（来源快照没有可用排课信息）。
   * 该字段改为"**仅当属性存在时才写入**"，规则见 `minimizeRow()`。
   */
  var REQUIRED_ROW_FIELDS = [
    "courseNum",
    "courseName",
    "classNumber",
    "yearTerm",
    "score",
    "limitNumber",
    "selectedNumber"
  ];

  /** 已确认的 segment / field 分隔符。 */
  var SEGMENT_SEPARATOR = ",";
  var FIELD_SEPARATOR = "/";

  /** segment 内 teacher 的脱敏占位符。 */
  var REDACTED_TEACHER = "REDACTED";

  /**
   * 明确判定为 location 所需的**最少非空 `-` 分段数**。
   *
   * ⚠️ 只用于 **5 字段的二义判别**；6 字段的语义已由字段数确定，不受此门槛约束。
   */
  var MIN_LOCATION_SEGMENTS = 3;

  /**
   * 目前**经真实证据确认**的 schedule qualifier 白名单。
   *
   * ⛔ **白名单而非通配**：`12-19周XXX` / `16-16周线上` 等一律拒绝。
   */
  var SCHEDULE_QUALIFIER_OFF_CAMPUS = "校外";
  var SCHEDULE_QUALIFIER_ON_CAMPUS_OUTDOOR = "校内(户外)";
  var KNOWN_SCHEDULE_QUALIFIERS = [
    SCHEDULE_QUALIFIER_OFF_CAMPUS,
    SCHEDULE_QUALIFIER_ON_CAMPUS_OUTDOOR
  ];

  /**
   * **non-concrete** 2 字段段第 1 个字段的形状：`<weeks token><已确认 qualifier>`。
   *
   * 与 Python `schedule_parser._QUALIFIED_WEEKS_ONLY` **同规则**，
   * 且必须**整段**匹配（`^...$`），因此不会出现"周次后面接任意字符"。
   */
  var NON_CONCRETE_FIRST_FIELD = /^([0-9]+-[0-9]+周)(校外|校内\(户外\))$/;

  /**
   * **non-concrete 带 teacher** 的 3 字段段第 1 个字段：
   * `<weeks token>` 或 `<weeks token><已确认 qualifier>`。
   *
   * ⚠️ 与 Python `_WEEKS_WITH_OPTIONAL_QUALIFIER` 同规则：
   * 先把 weeks 与 qualifier **拆开**，再各自校验；
   * ⛔ qualifier 的具体取值由白名单把关（`KNOWN_SCHEDULE_QUALIFIERS`）。
   */
  var PLAIN_WEEK_RANGE = /^([0-9]+)-([0-9]+)周$/;
  var WEEKS_WITH_OPTIONAL_QUALIFIER = /^([0-9]+-[0-9]+周)(.+)?$/;

  /** 已确认 qualifier 的精确匹配。 */
  var KNOWN_QUALIFIER_EXACT = /^(校外|校内\(户外\))$/;

  // ---------------------------------------------------------------------
  // 基础工具
  // ---------------------------------------------------------------------

  function fail(message) {
    throw new Error("[学航采集器] " + message);
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function requireAllowedHost() {
    if (
      typeof window === "undefined" ||
      !window.location ||
      window.location.hostname !== ALLOWED_HOSTNAME
    ) {
      fail(
        "当前页面不是 " + ALLOWED_HOSTNAME + "，拒绝执行。" +
          "本采集器只允许在本人已登录、已有权限的教务页面内运行。"
      );
    }
  }

  // ---------------------------------------------------------------------
  // 脱敏：teachingTimePlaceStr 内 segment 的 teacher
  // ---------------------------------------------------------------------

  /**
   * 统计按 `-` 切分后**非空**（去空白后）的分段数量。
   */
  function countNonEmptyDashSegments(token) {
    var parts = token.split("-");
    var count = 0;
    for (var index = 0; index < parts.length; index += 1) {
      if (parts[index].trim() !== "") {
        count += 1;
      }
    }
    return count;
  }

  /**
   * 判别 **5 字段** `fields[3]` 的语义（**严格三态**）。
   *
   * ```text
   * 无 "-"                → "teacher"
   * >= 3 个非空 "-" 分段   → "location"
   * 其余二义形态           → "ambiguous" → 调用方 fail closed
   * ```
   *
   * ⚠️ **为什么不复用 `isLocationToken()`**：后者只要"非空园区 + `-` + 非空教室"成立，
   * 会把 `A-B` 这种**只有两段**的 token 判成 location —— 而它同样可能是一个
   * **含 `-` 的 teacher**。5 字段本身二义，必须用更严格的门槛，
   * 否则会重现"teacher / location 互相静默错读"。
   *
   * ⛔ 无法明确归类时**不猜**；⛔ 不比对课程名 / 学院 / 教师名，不做模糊匹配。
   */
  function classifyFiveFieldToken(token) {
    if (typeof token !== "string") {
      return "ambiguous";
    }

    if (token.indexOf("-") === -1) {
      return "teacher";
    }

    if (countNonEmptyDashSegments(token) >= MIN_LOCATION_SEGMENTS) {
      return "location";
    }

    return "ambiguous";
  }

  /**
   * 对一个 segment 脱敏：**只**把真实存在的 teacher 字段替换为 REDACTED。
   *
   * 已确认结构（2026-1 真实证据）：
   *
   * ```text
   * 4 fields: weeks / weekday / sections / activity                  → 无 teacher，原样保留
   * 5 fields: 需**严格三态**判别：
   *            无 "-"              → teacher  → fields[3] = REDACTED
   *            >= 3 个非空 "-" 分段 → location → 原样保留
   *            其余二义形态         → fail closed
   * 6 fields: weeks / weekday / sections / location / teacher / activity → fields[4] = REDACTED
   * ```
   *
   * ⚠️ 5 字段必须**结构判别**：⛔ 不得再把第 4 字段无条件当成 teacher
   * （那会把 location 脱敏掉，破坏地点信息）。
   *
   * 其余字段（weeks / weekday / sections / location / activity）**原样保留**。
   *
   * `humanRowNo` 为**从 1 开始**的人类行号，只用于错误信息（见 `minimizeRow`）。
   */
  function redactSegmentTeacher(segment, pageNo, humanRowNo) {
    var fields = segment.split(FIELD_SEPARATOR);
    var fieldCount = fields.length;

    if (fieldCount === 3) {
      // non-concrete 带 teacher：`<weeks token>[<已确认 qualifier>]` / teacher / activity
      // （2026-1 真实证据：`1-17周/龙霞/实验实践环节` 与
      //   `16-16周校内(户外)/龙霞/实验实践环节`，同行 teachingName 亦为教师姓名）。
      var firstField3 = fields[0].trim();
      var qualifiedMatch = WEEKS_WITH_OPTIONAL_QUALIFIER.exec(firstField3);

      if (qualifiedMatch === null) {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "是 3 字段（weeks / teacher / activity），但其第 1 个字段既不是合法的 " +
            "`N-M周` 周次 token，也不符合已确认的 qualifier 形态。" +
            "本采集器不猜格式，已整体停止（不回显该字段取值）。"
        );
      }

      var weeksToken3 = qualifiedMatch[1];
      var qualifier3 = qualifiedMatch[2];

      // ⛔ qualifier 是**白名单**：`16-16周未知文本` 一律拒绝。
      if (qualifier3 !== undefined && !KNOWN_QUALIFIER_EXACT.test(qualifier3)) {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "中的 qualifier 尚未被真实证据确认（已确认：" +
            KNOWN_SCHEDULE_QUALIFIERS.join("/") +
            "）。本采集器不猜格式，已整体停止（不回显该字段取值）。"
        );
      }

      // ⛔ 只按 **weeks token 自身** 校验区间，绝不把 qualifier 一起送进去。
      var weekMatch3 = PLAIN_WEEK_RANGE.exec(weeksToken3);
      if (weekMatch3 === null) {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "3 字段段的周次 token 不是合法的 `N-M周`。本采集器不猜格式，已整体停止。"
        );
      }

      var startWeek3 = parseInt(weekMatch3[1], 10);
      var endWeek3 = parseInt(weekMatch3[2], 10);
      if (startWeek3 < 1 || endWeek3 < startWeek3) {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "3 字段段的周次区间非法（要求 N >= 1 且 M >= N）。本采集器不猜格式，已整体停止。"
        );
      }

      var teacher3 = fields[1];
      if (typeof teacher3 !== "string" || teacher3.trim() === "") {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "中 teacher 字段为空或不是字符串。本采集器不写入脱敏占位符来掩盖该问题，已整体停止。"
        );
      }

      if (fields[2].trim() === "") {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "中 activity 字段为空。已整体停止。"
        );
      }

      // teacher 在 fields[1]：替换为 REDACTED；
      // ⛔ 不能因为第一个字段带 qualifier 就跳过脱敏。
      // weeks（含 qualifier）与 activity 原样保留。
      fields[1] = REDACTED_TEACHER;
      return fields.join(FIELD_SEPARATOR);
    }

    if (fieldCount === 2) {
      // non-concrete 段：`<weeks token><已确认 qualifier>` / activity。
      if (NON_CONCRETE_FIRST_FIELD.test(fields[0].trim())) {
        // 没有 weekday / sections / 具体地点 / teacher → ⛔ 不做任何脱敏。
        return segment;
      }
      // ⛔ 2 字段**只接受已验证 grammar**；其余一律 fail closed（不回显取值）。
      fail(
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
          "是 2 字段，但不符合已确认的 non-concrete grammar" +
          "（`<weeks token>` + 已确认 qualifier " + SCHEDULE_QUALIFIER_OFF_CAMPUS +
          " / activity）。本采集器不猜格式，已整体停止（不回显该字段取值）。"
      );
    }

    if (
      fieldCount !== 4 &&
      fieldCount !== 5 &&
      fieldCount !== 6
    ) {
      fail(
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
          "出现不支持的字段数（" + fieldCount + "）。" +
          "只接受 2 / 3（non-concrete）/ 4 / 5 / 6，本采集器不猜格式，已整体停止。"
      );
    }

    if (fieldCount === 4) {
      // 4 字段：weeks / weekday / sections / activity —— 没有 teacher，不做替换。
      return segment;
    }

    if (fieldCount === 5) {
      var classification = classifyFiveFieldToken(fields[3]);

      if (classification === "ambiguous") {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "第 4 个字段既不能明确判定为 location（需 >= " + MIN_LOCATION_SEGMENTS +
            " 个非空 '-' 分段），也不能明确判定为 teacher（需完全不含 '-'）。" +
            "本采集器不猜语义，已整体停止（不回显该字段取值）。"
        );
      }

      if (classification === "location") {
        // 5 字段 A：有地点、无 teacher → 原样保留。
        return segment;
      }

      // 5 字段 B：无地点、有 teacher。
      // ⛔ 替换前必须确认原 teacher 确实存在：
      // 空 teacher 若也被写成 REDACTED，等于**静默修复**了原始数据问题，
      // 会让下游 Python parser 误以为这条记录合法。
      // 错误信息不回显 teacher 取值。
      var teacher5 = fields[3];
      if (typeof teacher5 !== "string" || teacher5.trim() === "") {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "中 teacher 字段为空或不是字符串。本采集器不写入脱敏占位符来掩盖该问题，已整体停止。"
        );
      }
      fields[3] = REDACTED_TEACHER;
      return fields.join(FIELD_SEPARATOR);
    }

    // 6 字段：weeks / weekday / sections / location / teacher / activity
    var teacher6 = fields[4];
    if (typeof teacher6 !== "string" || teacher6.trim() === "") {
      fail(
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
          "中 teacher 字段为空或不是字符串。本采集器不写入脱敏占位符来掩盖该问题，已整体停止。"
      );
    }

    fields[4] = REDACTED_TEACHER;

    return fields.join(FIELD_SEPARATOR);
  }

  /**
   * 对整条 teachingTimePlaceStr 脱敏，并保持全部已确认结构：
   * segment 顺序、`/`、`,`、**最多一个** trailing comma、
   * location 原文、weeks / weekday / sections / activity 原文。
   *
   * `humanRowNo` 为**从 1 开始**的人类行号，只用于错误信息（见 `minimizeRow`）。
   */
  function redactTeachingTimePlace(text, pageNo, humanRowNo) {
    if (typeof text !== "string" || text === "") {
      fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录缺少可用的 teachingTimePlaceStr。");
    }

    var segments = text.split(SEGMENT_SEPARATOR);

    // 只允许**最多一个**末尾逗号：单个末尾空段可忽略，多个整体失败。
    var trailingEmpty = 0;
    for (var i = segments.length - 1; i >= 0; i -= 1) {
      if (segments[i].trim() !== "") {
        break;
      }
      trailingEmpty += 1;
    }

    if (trailingEmpty > 1) {
      fail(
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
          "出现多个末尾逗号。已整体停止。"
      );
    }

    var hadTrailingComma = trailingEmpty === 1;
    if (hadTrailingComma) {
      segments.pop();
    }

    if (segments.length === 0) {
      fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr 没有有效 segment。");
    }

    var redacted = segments.map(function (segment) {
      if (segment.trim() === "") {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "出现中间空 segment。已整体停止。"
        );
      }
      return redactSegmentTeacher(segment, pageNo, humanRowNo);
    });

    return redacted.join(SEGMENT_SEPARATOR) + (hadTrailingComma ? SEGMENT_SEPARATOR : "");
  }

  // ---------------------------------------------------------------------
  // 数据最小化
  // ---------------------------------------------------------------------

  /**
   * 取一条 row 的最小化副本：保留 7 个**基础必需字段**，
   * 并在 `teachingTimePlaceStr` **属性存在时**写入脱敏后的文本。
   *
   * ⛔ **DG-07B：`teachingTimePlaceStr` 是唯一允许"属性不存在"的字段。**
   *
   *   - 属性**不存在** → 最小化对象中**也不创建该 key**（`hasOwnProperty` 仍为 false）；
   *     ⛔ 不得写成 `null` / `""` / `placeholder` / `UNKNOWN` / `N/A` / `[]`；
   *   - 属性**存在** → 仍必须走 `redactTeachingTimePlace(...)`：
   *     `null` / 空串 / 其它类型 / 畸形字符串**一律 FAIL**（与 2C1B 之前一致）。
   *
   * 其余 7 个基础字段缺任意一个仍然**整体 FAIL**（不跳过、不补空）。
   *
   * ⚠️ **`humanRowNo` 是从 1 开始的人类行号，只用于错误信息**。
   * 调用方在第 1 页对第 1 条记录报告"第 1 条"，
   * 因此 `collect()` 传入的是 `Array.prototype.map` 的 **0-based** 下标 **加 1**。
   * 这样错误信息可以直接和浏览器里看到的行号对齐；**报告的是行数，不是数组下标**。
   */
  function minimizeRow(row, pageNo, humanRowNo) {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录不是对象。");
    }

    var minimized = {};

    // 7 个基础字段：必须全部存在。
    for (var i = 0; i < REQUIRED_ROW_FIELDS.length; i += 1) {
      var field = REQUIRED_ROW_FIELDS[i];
      if (!Object.prototype.hasOwnProperty.call(row, field)) {
        fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录缺少字段：" + field);
      }
      minimized[field] = row[field];
    }

    // ⛔ 只有**真正的属性不存在**才放行；不放行 null / 空串 / 其它类型 / 畸形。
    if (!Object.prototype.hasOwnProperty.call(row, SCHEDULE_FIELD)) {
      // 不写任何占位值：key 保持不存在，交给下游按"排课信息不可用"处理。
      return minimized;
    }

    // 属性存在 → 覆盖为脱敏后的文本（教师姓名不写入 Capture Bundle）。
    minimized[SCHEDULE_FIELD] = redactTeachingTimePlace(
      row[SCHEDULE_FIELD],
      pageNo,
      humanRowNo
    );

    return minimized;
  }

  // ---------------------------------------------------------------------
  // 单页请求
  // ---------------------------------------------------------------------

  function validatePagePayload(payload, pageNo) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      fail("第 " + pageNo + " 页响应不是对象。");
    }
    if (payload.code !== 200) {
      fail("第 " + pageNo + " 页 code 不是 200（实际 " + payload.code + "）。已整体停止。");
    }

    var data = payload.data;
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      fail("第 " + pageNo + " 页 data 不是对象。已整体停止。");
    }
    if (!Number.isInteger(data.total) || data.total < 0) {
      fail("第 " + pageNo + " 页 data.total 不是非负整数。已整体停止。");
    }
    if (!Array.isArray(data.rows)) {
      fail("第 " + pageNo + " 页 data.rows 不是数组。已整体停止。");
    }

    return data;
  }

  /**
   * 取一页：same-origin POST，认证状态由浏览器自己带上。
   *
   * `?_t=` 只是**复现已观察到的请求形态**（已观察请求带时间戳参数），
   * 不代表任何业务语义。
   */
  async function requestPage(semester, pageNo, pageSize) {
    var url = ENDPOINT_PATH + "?_t=" + Date.now();

    var response;
    try {
      response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pageNo: pageNo,
          pageSize: pageSize,
          total: true,
          param: { yearTerm: semester }
        })
      });
    } catch (error) {
      fail("第 " + pageNo + " 页请求失败：" + error.message + "。已整体停止。");
    }

    if (response.status === 401 || response.status === 403) {
      fail(
        "第 " + pageNo + " 页返回 " + response.status + "（认证或权限不足）。" +
          "已整体停止；本采集器不会尝试寻找或提取任何认证信息。【BLOCKED】"
      );
    }
    if (!response.ok) {
      fail("第 " + pageNo + " 页 HTTP 状态异常：" + response.status + "。已整体停止。");
    }

    var contentType = response.headers.get("content-type") || "";
    if (contentType.indexOf("application/json") === -1) {
      fail(
        "第 " + pageNo + " 页返回的不是 JSON（可能被重定向到登录页）。已整体停止。"
      );
    }

    var payload;
    try {
      payload = await response.json();
    } catch (error) {
      fail("第 " + pageNo + " 页 JSON 解析失败。已整体停止。");
    }

    return validatePagePayload(payload, pageNo);
  }

  // ---------------------------------------------------------------------
  // 主流程：必须由用户显式调用
  // ---------------------------------------------------------------------

  async function collect(options) {
    requireAllowedHost();

    var opts = options || {};

    var semester = opts.semester;
    if (typeof semester !== "string" || semester.trim() === "") {
      fail('必须显式提供非空 semester（例如 "2026-1"）。');
    }
    semester = semester.trim();

    var pageSize = opts.pageSize === undefined ? DEFAULT_PAGE_SIZE : opts.pageSize;
    if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
      fail(
        "pageSize 必须是 1.." + MAX_PAGE_SIZE + " 之间的整数" +
          "（SYSU 单页上限已人工验证为 " + MAX_PAGE_SIZE + "）。"
      );
    }

    // ⛔ SYSU 只验证过 firstPageNo=1：
    // 不允许调用方传入其它起始页（那会对学校发起**未经验证**的页码请求）。
    // 通用多起始页能力属于 backend 分页核心，不在这里放开。
    if (opts.firstPageNo !== undefined && opts.firstPageNo !== FIRST_PAGE_NO) {
      fail(
        "SYSU 只验证过 firstPageNo=" + FIRST_PAGE_NO + "，不接受其它起始页。已整体停止。"
      );
    }
    var firstPageNo = FIRST_PAGE_NO;

    var maxPages = opts.maxPages === undefined ? DEFAULT_MAX_PAGES : opts.maxPages;
    if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > ABSOLUTE_MAX_PAGES) {
      fail("maxPages 必须是 1.." + ABSOLUTE_MAX_PAGES + " 之间的整数。");
    }

    var delayMs = opts.delayMs === undefined ? DEFAULT_DELAY_MS : opts.delayMs;
    if (!Number.isInteger(delayMs) || delayMs < MIN_DELAY_MS) {
      fail("delayMs 不得小于 " + MIN_DELAY_MS + " 毫秒（串行、低频）。");
    }

    // 超过默认 smoke 页数时，必须由用户明确确认。
    if (maxPages > DEFAULT_MAX_PAGES) {
      var confirmed = window.confirm(
        "即将对本人已授权可见的 " + semester + " 开课数据执行串行采集。\n" +
          "pageSize=" + pageSize + "\n" +
          "最多请求 " + maxPages + " 页\n" +
          "请求间隔至少 " + delayMs / 1000 + " 秒\n" +
          "是否继续？"
      );
      if (!confirmed) {
        return { cancelled: true, requests: 0, bundle: null };
      }
    }

    var pages = [];
    var expectedTotal = null;
    var accumulatedRows = 0;
    var requests = 0;
    var stoppedReason = "max_pages";

    // 严格串行：一页一页取，中间 sleep；不并发、不预取。
    for (var index = 0; index < maxPages; index += 1) {
      var currentPageNo = firstPageNo + index;

      if (index > 0) {
        await sleep(delayMs);
      }

      var data = await requestPage(semester, currentPageNo, pageSize);
      requests += 1;

      if (expectedTotal === null) {
        expectedTotal = data.total;
      } else if (data.total !== expectedTotal) {
        fail(
          "第 " + currentPageNo + " 页的 data.total(" + data.total + ")与首页(" +
            expectedTotal + ")不一致；采集期间数据集合发生变化，已整体停止。"
        );
      }

      if (data.rows.length === 0 && accumulatedRows < expectedTotal) {
        fail(
          "第 " + currentPageNo + " 页为空，但累计(" + accumulatedRows +
            ")仍未达到 total(" + expectedTotal + ")。已整体停止。"
        );
      }

      accumulatedRows += data.rows.length;
      if (accumulatedRows > expectedTotal) {
        fail(
          "累计行数(" + accumulatedRows + ")超过 total(" + expectedTotal + ")。已整体停止。"
        );
      }

      // 报告给用户的行号从 1 开始：map 的下标是 0-based，因此显式 + 1。
      // 不改变顺序、不跳过任何 row、不做任何字段修补。
      var minimizedRows = data.rows.map(function (row, rowIndex) {
        return minimizeRow(row, currentPageNo, rowIndex + 1);
      });

      pages.push({
        page_no: currentPageNo,
        response: {
          code: 200,
          data: { total: data.total, rows: minimizedRows }
        }
      });

      if (accumulatedRows === expectedTotal) {
        stoppedReason = "reached_total";
        break;
      }
    }

    return {
      cancelled: false,
      requests: requests,
      stoppedReason: stoppedReason,
      accumulatedRows: accumulatedRows,
      expectedTotal: expectedTotal,
      // 明确：本采集器**不判断**完整性，complete / partial 交给 Python Pagination Core。
      claimedComplete: false,
      bundle: {
        format: CAPTURE_FORMAT,
        semester: semester,
        first_page_no: firstPageNo,
        page_size: pageSize,
        pages: pages
      }
    };
  }

  // ---------------------------------------------------------------------
  // 结构诊断（Phase 2B-2C1B）：只取证，不是 workaround
  // ---------------------------------------------------------------------

  /** 诊断统计的目标字段名。 */
  var SCHEDULE_FIELD = "teachingTimePlaceStr";

  /** 诊断固定只取第 1 页（不对外开放、不循环、不重试）。 */
  var DIAGNOSTIC_PAGE_NO = 1;

  /** 诊断固定使用已验证的单页上限。 */
  var DIAGNOSTIC_PAGE_SIZE = 200;

  /**
   * 纯函数：统计 `rows` 中 `teachingTimePlaceStr` 的存在形态。
   *
   * 分类（互斥且穷尽）：
   *   missing          —— 字段不存在
   *   null             —— 字段存在且值为 null
   *   empty_string     —— 值是字符串但 trim 后为空
   *   non_empty_string —— 值是字符串且 trim 后非空
   *   other_type       —— 字段存在，但既不是 null 也不是字符串
   *
   * 保证：missing + null + empty_string + non_empty_string + other_type === rows.length
   *
   * ⛔ 只统计数量，**不返回也不打印**任何 row 内容、课程号、教师、教室或原文。
   */
  function summarizeSchedulePresence(rows) {
    if (!Array.isArray(rows)) {
      fail("诊断需要 data.rows 是数组。已停止。");
    }

    var bucket = {
      missing: 0,
      null: 0,
      empty_string: 0,
      non_empty_string: 0,
      other_type: 0
    };

    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];

      if (!row || typeof row !== "object" || Array.isArray(row)) {
        // 只报结构性问题与下标，不回显 row 内容。
        fail("诊断遇到非对象 row（下标 " + index + "）。已停止。");
      }

      if (!Object.prototype.hasOwnProperty.call(row, SCHEDULE_FIELD)) {
        bucket.missing += 1;
        continue;
      }

      var value = row[SCHEDULE_FIELD];

      if (value === null) {
        bucket.null += 1;
      } else if (typeof value === "string") {
        if (value.trim() === "") {
          bucket.empty_string += 1;
        } else {
          bucket.non_empty_string += 1;
        }
      } else {
        bucket.other_type += 1;
      }
    }

    return {
      total_rows: rows.length,
      teachingTimePlaceStr: bucket
    };
  }

  /**
   * 结构诊断：**只请求第 1 页一次**，统计 `teachingTimePlaceStr` 的存在形态。
   *
   * - 复用现有 hostname guard / same-origin 请求 / 既有取页函数的
   *   HTTP / JSON / code / total / rows 校验（**不复制认证逻辑**）；
   * - 固定 `pageNo = DIAGNOSTIC_PAGE_NO`（1）、`pageSize = DIAGNOSTIC_PAGE_SIZE`（200）；
   * - ⛔ 不接受任何分页选项（没有 maxPages / firstPageNo / 循环 / 重试 / 并发）；
   * - ⛔ **不生成 Capture Bundle**、不做字段最小化、不做教师脱敏、不调用 `toJson`；
   * - ⛔ 不修改 `collect()` 的 fail-closed 行为 —— 本函数只是取证，不是 workaround。
   *
   * 返回值只有聚合统计，**不含**任何 Raw row / 课程号 / 教师 / 教室 / 原文。
   */
  async function diagnoseSchedulePresence(options) {
    requireAllowedHost();

    var opts = options || {};

    var semester = opts.semester;
    if (typeof semester !== "string" || semester.trim() === "") {
      fail('诊断必须显式提供非空 semester（例如 "2026-1"）。');
    }
    semester = semester.trim();

    // 只取第 1 页、只取一次。
    var data = await requestPage(semester, DIAGNOSTIC_PAGE_NO, DIAGNOSTIC_PAGE_SIZE);

    var summary = summarizeSchedulePresence(data.rows);

    return {
      semester: semester,
      page_no: DIAGNOSTIC_PAGE_NO,
      page_size: DIAGNOSTIC_PAGE_SIZE,
      reported_total: data.total,
      total_rows: summary.total_rows,
      teachingTimePlaceStr: summary.teachingTimePlaceStr
    };
  }

  /**
   * 把采集结果序列化成**裸 Capture Bundle**（可直接交给 Python `load_capture_bundle`）。
   *
   * 顶层就是 `format` / `semester` / `first_page_no` / `page_size` / `pages`，
   * 不含 wrapper 字段 —— 这样自然用法是：
   *
   *     const result = await window.XuehangSysuCollector.collect({ semester: "2026-1" });
   *     const text = window.XuehangSysuCollector.toJson(result);
   *
   * ⛔ 采集被取消或没有 bundle 时**直接失败**，不生成伪 bundle。
   * ⛔ 写文件由用户自行决定，本文件不落盘。
   */
  function toJson(result) {
    if (!result || result.cancelled === true || !result.bundle) {
      fail(
        "没有可序列化的 Capture Bundle（采集被取消或未产生 bundle）。" +
          "本采集器不会生成伪 bundle。"
      );
    }
    return JSON.stringify(result.bundle, null, 2);
  }

  // ---------------------------------------------------------------------
  // 相关性诊断（Phase 2B-2C1C）：missing 组 vs non_empty_string 组的字段聚合
  // ---------------------------------------------------------------------

  /**
   * C1C 与 2C1B 使用**同一固定取页口径**：只取第 1 页一次。
   * 常量直接引用已人工验证的取值，避免两处口径漂移。
   */
  var CORRELATION_PAGE_NO = DIAGNOSTIC_PAGE_NO;
  var CORRELATION_PAGE_SIZE = DIAGNOSTIC_PAGE_SIZE;

  /**
   * 分类值统计的**诊断输出安全阀**（**不是** SYSU 参数）。
   * 某字段某组的 distinct 取值数超过它 → **整体 suppression**，不返回任何取值列表。
   */
  var MAX_DISTINCT_VALUES = 20;

  /** C1C 允许比较的两组（其余形态计入 ungrouped_rows，**不**被塞进任何一组）。 */
  var CORRELATION_GROUP_MISSING = "missing";
  var CORRELATION_GROUP_PRESENT = "non_empty_string";

  /** A. 只做**存在性 / 类型**统计的字段：⛔ 绝不输出具体取值。 */
  var STRUCTURAL_ONLY_FIELDS = ["timePlaceId", "limitNumber", "selectedNumber"];

  /** B. 允许做**有限分类值计数**的字段（高基数会整体 suppression）。 */
  var CATEGORICAL_FIELDS = [
    "weekDay",
    "openClass",
    "teachProgressSubmitState",
    "courseCategoryName",
    "examMode",
    "openingUnitName"
  ];

  /**
   * 分类值列表的**确定顺序**：先按类型（boolean → number → string），再按序列化文本。
   * ⛔ 不按出现次数排序 —— 那会变成"取最常见的 N 个"，本诊断不做这种选择。
   */
  var SCALAR_TYPE_ORDER = ["boolean", "number", "string"];

  /**
   * 纯函数：把一条 row 归入 `teachingTimePlaceStr` 的五种存在形态之一。
   *
   * 与 2B-2C1B 的 `summarizeSchedulePresence` **同一套分类规则**：
   *   missing / null / empty_string / non_empty_string / other_type
   *
   * ⛔ 只读该字段自身的存在性与类型，不读、不返回任何业务字段取值。
   */
  function classifySchedulePresence(row) {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      fail("相关性诊断遇到非对象 row。已停止。");
    }

    if (!Object.prototype.hasOwnProperty.call(row, SCHEDULE_FIELD)) {
      return "missing";
    }

    var value = row[SCHEDULE_FIELD];

    if (value === null) {
      return "null";
    }
    if (typeof value === "string") {
      return value.trim() === "" ? "empty_string" : "non_empty_string";
    }
    return "other_type";
  }

  /**
   * 纯函数：五桶统计（互斥且穷尽）。
   *
   * 保证：missing + null + empty_string + non_empty_string + other_type === rows.length
   *
   * ⛔ 只计数，不返回任何 row 内容 / 课程信息 / 教师 / 原文。
   */
  function summarizePresenceBuckets(rows) {
    if (!Array.isArray(rows)) {
      fail("相关性诊断需要 data.rows 是数组。已停止。");
    }

    var buckets = {
      missing: 0,
      null: 0,
      empty_string: 0,
      non_empty_string: 0,
      other_type: 0
    };

    for (var index = 0; index < rows.length; index += 1) {
      var bucket = classifySchedulePresence(rows[index]);
      if (!Object.prototype.hasOwnProperty.call(buckets, bucket)) {
        fail("相关性诊断出现未知的分类桶。已停止。");
      }
      buckets[bucket] += 1;
    }

    return { total_rows: rows.length, buckets: buckets };
  }

  /**
   * 纯函数：把 rows 分成"只参与比较的两组" + "其余形态的计数"。
   *
   * ⛔ `null` / `empty_string` / `other_type` **不**被塞进任何一组，只计入 `other_rows`。
   * ⛔ 返回的两个数组只在本次调用栈内使用，**绝不**进入诊断返回值。
   */
  function splitRowsForCorrelation(rows) {
    var missingRows = [];
    var presentRows = [];
    var otherRows = 0;

    for (var index = 0; index < rows.length; index += 1) {
      var bucket = classifySchedulePresence(rows[index]);

      if (bucket === CORRELATION_GROUP_MISSING) {
        missingRows.push(rows[index]);
      } else if (bucket === CORRELATION_GROUP_PRESENT) {
        presentRows.push(rows[index]);
      } else {
        otherRows += 1;
      }
    }

    return {
      missing: missingRows,
      non_empty_string: presentRows,
      other_rows: otherRows
    };
  }

  /**
   * 纯函数（A 类）：某字段在**一组 row** 中的**存在性 / 类型**统计。
   *
   * 桶：missing（字段不存在）/ null / empty_string / non_empty_string /
   *     number / boolean / other_type。
   *
   * ⛔ **不返回任何取值列表**、不返回具体值、不返回 distinct 计数 ——
   *    需要"值"的字段属于 B 类，走另一个函数。
   */
  function summarizeFieldShape(rows, field) {
    var shape = {
      field: field,
      total: rows.length,
      missing: 0,
      null: 0,
      empty_string: 0,
      non_empty_string: 0,
      number: 0,
      boolean: 0,
      other_type: 0
    };

    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];

      if (!Object.prototype.hasOwnProperty.call(row, field)) {
        shape.missing += 1;
        continue;
      }

      var value = row[field];

      if (value === null) {
        shape.null += 1;
      } else if (typeof value === "string") {
        if (value.trim() === "") {
          shape.empty_string += 1;
        } else {
          shape.non_empty_string += 1;
        }
      } else if (typeof value === "number") {
        shape.number += 1;
      } else if (typeof value === "boolean") {
        shape.boolean += 1;
      } else {
        shape.other_type += 1;
      }
    }

    return shape;
  }

  /**
   * 在一个**数组**里累加标量取值计数（线性扫描）。
   *
   * ⛔ 故意**不用**真实取值作为 object / Map 的 key：
   * 真实数据只作为比较对象存在，绝不会变成属性名。
   * 展示值统一序列化成字符串，`type` 保留原始类型。
   */
  function accumulateScalarEntry(entries, type, value) {
    var serialized = String(value);

    for (var index = 0; index < entries.length; index += 1) {
      if (entries[index].type === type && entries[index].value === serialized) {
        entries[index].count += 1;
        return;
      }
    }

    entries.push({ type: type, value: serialized, count: 1 });
  }

  /** 确定顺序的比较器：先类型，再序列化文本（⛔ 与出现次数无关）。 */
  function compareScalarEntries(left, right) {
    var leftRank = SCALAR_TYPE_ORDER.indexOf(left.type);
    var rightRank = SCALAR_TYPE_ORDER.indexOf(right.type);

    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    if (left.value < right.value) {
      return -1;
    }
    if (left.value > right.value) {
      return 1;
    }
    return 0;
  }

  /**
   * 纯函数（B 类）：某字段在**一组 row** 中的"归类桶 + 有限分类值计数"。
   *
   * 归类桶（**不进入** value 列表）：missing / null / empty_string /
   * other_type（object、array、undefined、function 等）。
   * 正常 value 列表只包含三种标量：boolean / number / 非空 string，
   * 形如 `{ type: "number", value: "0", count: 32 }`。
   *
   * 保证：missing + null + empty_string + other_type + scalar_count === total；
   *       未 suppression 时 Σ values[].count === scalar_count。
   *
   * ⛔ distinct 数超过 `MAX_DISTINCT_VALUES` → **整体 suppression**
   *    （`values_suppressed: true`、`values: []`），
   *    **不**返回前 N 个、**不**返回随机 N 个、**不**返回最常见的 N 个。
   */
  function summarizeCategoricalValues(rows, field) {
    var summary = {
      field: field,
      total: rows.length,
      missing: 0,
      null: 0,
      empty_string: 0,
      other_type: 0,
      scalar_count: 0,
      distinct_count: 0,
      values_suppressed: false,
      values: []
    };

    var entries = [];

    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];

      if (!Object.prototype.hasOwnProperty.call(row, field)) {
        summary.missing += 1;
        continue;
      }

      var value = row[field];

      if (value === null) {
        summary.null += 1;
        continue;
      }

      var valueType = typeof value;

      if (valueType === "string") {
        if (value.trim() === "") {
          summary.empty_string += 1;
          continue;
        }
      } else if (valueType !== "number" && valueType !== "boolean") {
        summary.other_type += 1;
        continue;
      }

      summary.scalar_count += 1;
      accumulateScalarEntry(entries, valueType, value);
    }

    entries.sort(compareScalarEntries);

    summary.distinct_count = entries.length;
    if (entries.length > MAX_DISTINCT_VALUES) {
      summary.values_suppressed = true;
      summary.values = [];
    } else {
      summary.values = entries;
    }

    return summary;
  }

  /**
   * 纯函数：对**一组 row** 做字段聚合（A 类 + B 类）。
   *
   * ⛔ 返回值里**没有** Raw row、没有课程号 / 课程名 / 教学班号 / 教师 / 教室 /
   *    内部 ID 取值，也没有 `teachingTimePlaceStr` 原文。
   */
  function summarizeCorrelationGroup(rows) {
    var structuralFields = {};
    var categoricalFields = {};

    for (var index = 0; index < STRUCTURAL_ONLY_FIELDS.length; index += 1) {
      var structuralField = STRUCTURAL_ONLY_FIELDS[index];
      structuralFields[structuralField] = summarizeFieldShape(rows, structuralField);
    }

    for (var otherIndex = 0; otherIndex < CATEGORICAL_FIELDS.length; otherIndex += 1) {
      var categoricalField = CATEGORICAL_FIELDS[otherIndex];
      categoricalFields[categoricalField] = summarizeCategoricalValues(rows, categoricalField);
    }

    return {
      total: rows.length,
      structural_fields: structuralFields,
      categorical_fields: categoricalFields
    };
  }

  /** 已列出的分类值计数之和（用于 suppression 关闭时的加总校验）。 */
  function sumListedCounts(values) {
    var total = 0;
    for (var index = 0; index < values.length; index += 1) {
      total += values[index].count;
    }
    return total;
  }

  /**
   * 纯函数：一组内**每个字段自身的统计必须加总等于该组 total**。
   * ⛔ 不守恒即整体失败，绝不静默丢 row。
   */
  function assertFieldTotals(groupName, group) {
    var index;
    var field;
    var summary;

    for (index = 0; index < STRUCTURAL_ONLY_FIELDS.length; index += 1) {
      field = STRUCTURAL_ONLY_FIELDS[index];
      summary = group.structural_fields[field];

      if (
        summary.missing + summary.null + summary.empty_string +
        summary.non_empty_string + summary.number + summary.boolean +
        summary.other_type !== summary.total
      ) {
        fail("相关性诊断的结构字段统计不守恒（" + groupName + "）。已停止。");
      }
    }

    for (index = 0; index < CATEGORICAL_FIELDS.length; index += 1) {
      field = CATEGORICAL_FIELDS[index];
      summary = group.categorical_fields[field];

      if (
        summary.missing + summary.null + summary.empty_string +
        summary.other_type + summary.scalar_count !== summary.total
      ) {
        fail("相关性诊断的分类字段统计不守恒（" + groupName + "）。已停止。");
      }
      if (summary.values_suppressed === true && summary.values.length !== 0) {
        fail("相关性诊断在 suppression 时仍返回了取值列表（" + groupName + "）。已停止。");
      }
      if (
        summary.values_suppressed === false &&
        sumListedCounts(summary.values) !== summary.scalar_count
      ) {
        fail("相关性诊断的分类值计数不守恒（" + groupName + "）。已停止。");
      }
    }
  }

  /**
   * 纯函数：C1C 的**计数不变量**（任一不成立即整体失败，绝不静默丢 row）。
   *
   *   五桶之和                          === total_rows
   *   groups.missing.total              === 五桶.missing
   *   groups.non_empty_string.total     === 五桶.non_empty_string
   *   missing + non_empty_string        === compared_rows
   *   分组时的其它形态计数              === null + empty_string + other_type
   *   compared_rows + ungrouped_rows    === total_rows
   *   每个字段自身的统计加总            === 该组 total
   */
  function assertCorrelationInvariants(presence, split, groups) {
    var buckets = presence.buckets;
    var bucketTotal =
      buckets.missing + buckets.null + buckets.empty_string +
      buckets.non_empty_string + buckets.other_type;

    if (bucketTotal !== presence.total_rows) {
      fail("相关性诊断的形态统计不守恒。已停止。");
    }
    if (groups.missing.total !== buckets.missing) {
      fail("相关性诊断的 missing 组计数与形态统计不一致。已停止。");
    }
    if (groups.non_empty_string.total !== buckets.non_empty_string) {
      fail("相关性诊断的 non_empty_string 组计数与形态统计不一致。已停止。");
    }
    if (
      groups.missing.total + groups.non_empty_string.total !==
      buckets.missing + buckets.non_empty_string
    ) {
      fail("相关性诊断的 compared_rows 不守恒。已停止。");
    }
    if (split.other_rows !== buckets.null + buckets.empty_string + buckets.other_type) {
      fail("相关性诊断的 ungrouped_rows 不守恒。已停止。");
    }
    if (
      groups.missing.total + groups.non_empty_string.total + split.other_rows !==
      presence.total_rows
    ) {
      fail("相关性诊断的行数加总不守恒。已停止。");
    }

    assertFieldTotals(CORRELATION_GROUP_MISSING, groups.missing);
    assertFieldTotals(CORRELATION_GROUP_PRESENT, groups.non_empty_string);
  }

  /**
   * 相关性诊断：**只请求第 1 页一次**，比较两组 row 的字段聚合结构。
   *
   * 目的**只是**判断"缺 `teachingTimePlaceStr` 的 row 是否表现出一致的结构特征"，
   * ⛔ **不是**判断它们的业务含义，也**不是** workaround：
   * 不改造数据、不放宽 `collect()` 的 fail-closed 行为、不产出任何数据文件。
   *
   * - 复用现有 hostname guard / same-origin 请求 / 既有取页函数的全部校验；
   * - 固定 `pageNo = CORRELATION_PAGE_NO`（1）、`pageSize = CORRELATION_PAGE_SIZE`（200）；
   * - ⛔ 用户**只允许**提供 `semester`：其它任何 own key 一律在**发请求之前**拒绝；
   * - ⛔ 没有分页循环、没有重试、没有并发、没有第二次请求；
   * - ⛔ 只把聚合对象返回给**显式调用者**：不落盘、不写浏览器存储、不产出数据文件；
   * - ⛔ **不返回**：Raw row / 逐行数据 / 课程与教学班标识 / 教师 / 教室 /
   *   `teachingTimePlaceStr` 原文；
   * - ⛔ **A 类（structural-only）字段不返回具体值**，只有存在性 / 类型计数；
   * - ⚠️ **B 类（categorical）字段在 `distinct <= MAX_DISTINCT_VALUES` 时
   *   会返回"聚合后的原始标量分类值 + 出现次数"**（例如 `{type, value, count}`）——
   *   这是本诊断**有意**返回的信息，用于观察两组是否分群；
   *   在 `distinct > MAX_DISTINCT_VALUES` 时 **`values` 整体 suppression**（`values = []`）；
   * - ⛔ 这些原始值只以"原始值 X 出现 N 次"的形式出现，**不做任何业务语义解释**。
   */
  async function diagnoseMissingScheduleCorrelation(options) {
    requireAllowedHost();

    var opts = options || {};

    var semester = opts.semester;
    if (typeof semester !== "string" || semester.trim() === "") {
      fail('相关性诊断必须显式提供非空 semester（例如 "2026-1"）。');
    }
    semester = semester.trim();

    // ⛔ **严格白名单**：只接受 semester 一个 own key（不是"已知参数黑名单"）。
    // 任何额外字段都在**发请求之前** fail closed；不回显调用方提供的键名。
    var optionNames = Object.keys(opts);
    var unexpected = optionNames.filter(function (name) {
      return name !== "semester";
    });
    if (unexpected.length > 0) {
      fail(
        "相关性诊断只接受 semester 一个参数（收到 " + unexpected.length +
          " 个额外参数）。已停止；参数名不予回显。"
      );
    }

    // 只取第 1 页、只取一次。
    var data = await requestPage(semester, CORRELATION_PAGE_NO, CORRELATION_PAGE_SIZE);
    var rows = data.rows;

    var presence = summarizePresenceBuckets(rows);
    var split = splitRowsForCorrelation(rows);

    var groups = {
      missing: summarizeCorrelationGroup(split.missing),
      non_empty_string: summarizeCorrelationGroup(split.non_empty_string)
    };

    assertCorrelationInvariants(presence, split, groups);

    return {
      semester: semester,
      page_no: CORRELATION_PAGE_NO,
      page_size: CORRELATION_PAGE_SIZE,
      reported_total: data.total,
      total_rows: presence.total_rows,
      schedule_presence: presence.buckets,
      compared_rows: groups.missing.total + groups.non_empty_string.total,
      ungrouped_rows: split.other_rows,
      groups: groups
    };
  }

  // ---------------------------------------------------------------------
  // 显式暴露（加载本文件不触发任何请求）
  //
  // ⛔ C1C 的字段级 summarizer（`classifySchedulePresence` /
  //    `summarizeFieldShape` / `summarizeCategoricalValues`）是**内部实现**，
  //    **不暴露**：`summarizeCategoricalValues` 是**任意字段**的 generic
  //    summarizer，一旦公开就能绕过 C1C 的字段 allowlist。
  // ---------------------------------------------------------------------

  window.XuehangSysuCollector = {
    collect: collect,
    diagnoseSchedulePresence: diagnoseSchedulePresence,
    summarizeSchedulePresence: summarizeSchedulePresence,
    diagnoseMissingScheduleCorrelation: diagnoseMissingScheduleCorrelation,
    toJson: toJson,
    DIAGNOSTIC_PAGE_NO: DIAGNOSTIC_PAGE_NO,
    DIAGNOSTIC_PAGE_SIZE: DIAGNOSTIC_PAGE_SIZE,
    CORRELATION_PAGE_NO: CORRELATION_PAGE_NO,
    CORRELATION_PAGE_SIZE: CORRELATION_PAGE_SIZE,
    MAX_DISTINCT_VALUES: MAX_DISTINCT_VALUES,
    CAPTURE_FORMAT: CAPTURE_FORMAT,
    ALLOWED_HOSTNAME: ALLOWED_HOSTNAME,
    ENDPOINT_PATH: ENDPOINT_PATH,
    FIRST_PAGE_NO: FIRST_PAGE_NO,
    MAX_PAGE_SIZE: MAX_PAGE_SIZE,
    DEFAULT_PAGE_SIZE: DEFAULT_PAGE_SIZE,
    DEFAULT_MAX_PAGES: DEFAULT_MAX_PAGES,
    ABSOLUTE_MAX_PAGES: ABSOLUTE_MAX_PAGES,
    DEFAULT_DELAY_MS: DEFAULT_DELAY_MS,
    MIN_DELAY_MS: MIN_DELAY_MS,
    REDACTED_TEACHER: REDACTED_TEACHER
  };
})();
