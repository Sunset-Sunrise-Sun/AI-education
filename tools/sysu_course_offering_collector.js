/**
 * 学航·转衔 —— SYSU 开课数据「显式触发」浏览器端采集器（Phase 2B-2C1A）
 * ================================================================
 *
 * 定位
 * ----
 * 本文件是 **SYSU-specific Transport 的浏览器侧实现**。
 * 它提供四件事：
 *   1. `collect()` —— 串行取页 → 最小化字段 + 脱敏 → 产出**一个**本地 Capture Bundle；
 *   2. `collectSharded()` —— **五校区 shard 编排**：
 *      `baseline_before → 五校区串行 collect → baseline_after → 外层 diagnostics`，
 *      产出**五个独立裸 Capture Bundle** + **一个外层 diagnostics 对象**；
 *   3. `diagnoseSchedulePresence()` —— **只取第 1 页一次**的**结构诊断**（只统计，不产出数据）；
 *   4. `diagnoseMissingScheduleCorrelation()` —— 同样**只取第 1 页一次**的
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
 *     await window.XuehangSysuCollector.collectSharded({ semester: "2026-1", maxPages: 20 })
 *     await window.XuehangSysuCollector.diagnoseSchedulePresence({ semester: "2026-1" })
 *     await window.XuehangSysuCollector.diagnoseMissingScheduleCorrelation({ semester: "2026-1" })
 *
 * 默认只跑 2 页 smoke test；要跑更多页必须显式提高 `maxPages`，并会弹出确认框。
 * **全局 batch pacing**：同一 endpoint 的相邻请求至少间隔 30 秒，
 * 且每累计 5 个**成功**请求先冷却 5 分钟（计数是整个采集 run 的全局计数）。
 *
 * 取出结果：
 *
 *     const result = await window.XuehangSysuCollector.collect({ semester: "2026-1" });
 *     const text = window.XuehangSysuCollector.toJson(result);   // 裸 Capture Bundle
 *
 * `toJson()` 输出的**顶层就是** `format` / `semester` / `first_page_no` / `page_size` / `pages`，
 * 可直接交给 Python 的 `load_capture_bundle(...)`。
 *
 * 五校区结果取出方式（⛔ diagnostics **不**进入裸 bundle）：
 *
 *     const sharded = await window.XuehangSysuCollector.collectSharded({ semester: "2026-1", maxPages: 20 });
 *     for (const shard of sharded.shards) { console.log(shard.shard_id, shard.bundle); }
 *     window.XuehangSysuCollector.toShardJson(sharded, "东校园");      // 某个 shard 的裸 bundle
 *     window.XuehangSysuCollector.toDiagnosticsJson(sharded);        // 外层 diagnostics
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

  /**
   * 串行请求间隔（**同一 endpoint 的所有连续请求**都必须满足）。
   *
   * ⚠️ **30 秒是当前的 conservative operational minimum**，来源是**人工实测**：
   * 同一 endpoint 短间隔连续请求会稳定出现
   * `HTTP 600 / code=50015000 / 系统异常`。
   * ⛔ **不声称**这是学校官方公布的阈值，也不据此推断任何服务端限流实现。
   *
   * ⛔ 调用方**只能把它调大**（更慢、更保守），不能调小。
   */
  var DEFAULT_DELAY_MS = 30000;
  var MIN_DELAY_MS = 30000;

  /**
   * **全局 batch pacing**（Architecture Review 裁定）。
   *
   * ⚠️ 人工 sustained pacing 实测：`pageSize=50` + 30 秒间隔，
   * **连续 7 次成功（200）后第 8 次**出现 `HTTP 600 / code=50015000`。
   * ⇒ 单纯继续加大单一 `delayMs` 不足以规避，因此改为
   * "**每 5 个成功请求 → 冷却 5 分钟**"的批次节奏。
   *
   * ⚠️ 因此 **5-request batch + 5-minute cooldown 是当前保守运营策略**，
   * 来自上述人工实测，⛔ **不是学校公开阈值**。
   *
   * ⛔ 计数是**整个 sharded collection 的全局请求数**
   * （`baseline_before` + 所有 shard 的页 + `baseline_after`）：
   * ⛔ **不是 per-shard**，⛔ 不会在 shard 边界重置。
   *
   * ⛔ `BATCH_COOLDOWN_MS` 本身已大于普通间隔，所以批次边界**只等冷却**，
   * ⛔ 不再叠加一次 `delayMs`；若调用方把 `delayMs` 调得更大则取较大者。
   */
  var MAX_REQUESTS_PER_BATCH = 5;
  var BATCH_COOLDOWN_MS = 300000;

  /** 默认只做 2 页 smoke test；50 是**客户端安全上限**，不是学校系统限制。 */
  var DEFAULT_MAX_PAGES = 2;
  var ABSOLUTE_MAX_PAGES = 50;

  /**
   * 五校区 shard 分页固定使用的单页大小（= 已验证的 `DEFAULT_PAGE_SIZE`）。
   *
   * ⛔ `collectSharded()` **不接受**调用方传入 `pageSize`（严格白名单拒绝）。
   */
  var SHARD_PAGE_SIZE = DEFAULT_PAGE_SIZE;

  /** 校区维度请求参数名（与已取证的 UI 参数一致）。 */
  var SHARD_PARAM_NAME = "openingSchoolNumber";

  /**
   * 已批准的五个校区 shard —— **顺序即请求顺序**（稳定、可复现）。
   *
   * ⚠️ `openingSchoolNumber` 由负责人在官方 UI 中**人工取证**；
   * ⛔ 不猜其它校区、⛔ 不自动读取下拉框、⛔ 不从任何接口发现 shard 列表、
   * ⛔ 不接受调用方传入自定义 shard。
   *
   * ⛔ 这些是**请求参数**（校区维度），不是 row 字段：它们**不会**进入 Capture Bundle。
   */
  var APPROVED_SHARDS = [
    { shard_id: "东校园", openingSchoolNumber: "5063559" },
    { shard_id: "北校园", openingSchoolNumber: "5062202" },
    { shard_id: "南校园", openingSchoolNumber: "5062201" },
    { shard_id: "深圳校区", openingSchoolNumber: "333291143" },
    { shard_id: "珠海校区", openingSchoolNumber: "5062203" }
  ];

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
    throw new Error(ERROR_PREFIX + message);
  }

  /** 错误信息前缀（包装下层错误时用它去重，避免出现两个前缀）。 */
  var ERROR_PREFIX = "[学航采集器] ";

  /** 去掉已经带上的前缀（只用于**包装**下层错误信息时）。 */
  function unwrapErrorMessage(error) {
    var message = error && error.message ? error.message : String(error);

    return message.indexOf(ERROR_PREFIX) === 0 ? message.slice(ERROR_PREFIX.length) : message;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  /**
   * **全局 request pacing controller**（每个采集 run **恰好一个**）。
   *
   * 它是本文件**唯一**决定"下一次请求什么时候可以发"的地方：
   * - ⛔ `baseline_before` / `collectPages()` / shard 循环 / `baseline_after`
   *   **都不再各自 sleep、也不各自计数** —— 它们只是把同一个 controller
   *   交给 `requestPage()`，由后者在**发请求之前**调用 `beforeRequest()`；
   * - 计数是**全局**的（整个 run 的所有请求：baseline + 所有 shard 的页 + baseline_after），
   *   ⛔ 不是 per-shard，也⛔ 不会在 shard 边界重置；
   * - 规则：
   *
   * ```text
   * 第 1 个请求                → 立即发送（不等待）
   * 其它请求                   → 先等 delayMs（>= MIN_DELAY_MS）
   * 已累计 5 个**成功**请求时  → 改为先等 max(BATCH_COOLDOWN_MS, delayMs)
   *                              （冷却本身已 > 普通间隔，⛔ 不叠加）
   * ```
   *
   * ⛔ 失败（HTTP 非 200 / code 非 200 / 网络错误）**不计入**成功数，
   * 而且会直接 fail closed 终止整个 run：⛔ 不重试、⛔ 不 backoff 重试、
   * ⛔ 不续采（no resume）、⛔ 不跳页。
   */
  function createRequestPacer(delayMs) {
    var isFirstRequest = true;
    var successfulInBatch = 0;

    return {
      /** 发请求**之前**调用：保证与上一个请求的间隔（含批次冷却）。 */
      beforeRequest: async function () {
        if (isFirstRequest) {
          isFirstRequest = false;
          return;
        }

        if (successfulInBatch >= MAX_REQUESTS_PER_BATCH) {
          successfulInBatch = 0;
          // 冷却本身已超过普通间隔；若调用方把 delayMs 调得更大则取较大者。
          await sleep(Math.max(BATCH_COOLDOWN_MS, delayMs));
          return;
        }

        await sleep(delayMs);
      },

      /** 请求**成功后**调用（HTTP 200 且 code 200）：只在这里推进批次计数。 */
      noteSuccess: function () {
        successfulInBatch += 1;
      }
    };
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
      // non-concrete（无 teacher）两种已确认形态：
      //   plain     ：`<weeks token>` / activity            例如 1-17周/实验实践环节
      //   qualified ：`<weeks token><已确认 qualifier>` / activity
      //                                                    例如 12-19周校外/实验实践环节
      if (
        PLAIN_WEEK_RANGE.test(fields[0].trim()) ||
        NON_CONCRETE_FIRST_FIELD.test(fields[0].trim())
      ) {
        // ⛔ activity 必须非空（与 Python parser 一致，不把空 activity 当合法）。
        if (fields[1].trim() === "") {
          fail(
            "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
              "中 activity 字段为空。已整体停止。"
          );
        }
        // 没有 weekday / sections / 具体地点 / teacher → ⛔ 不做任何脱敏。
        // ⛔ 也不得把 row 级 teachingName 注入本 segment。
        return segment;
      }
      // ⛔ 2 字段**只接受已验证 grammar**；其余一律 fail closed（不回显取值）。
      fail(
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
          "是 2 字段，但既不是已确认的 plain 形态（`<weeks token>` / activity），" +
          "也不是已确认的 qualified 形态（`<weeks token>` + 已确认 qualifier " +
          KNOWN_SCHEDULE_QUALIFIERS.join("/") +
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
   * 构造请求 body 的 `param`。
   *
   * - `openingSchoolNumber === undefined` → **只有** `yearTerm`（baseline 请求形态）；
   * - 传入已批准校区号 → 追加 `openingSchoolNumber`（shard 请求形态）。
   *
   * ⛔ 不传时**不写** `openingSchoolNumber: undefined`：不依赖 JSON 序列化的副作用，
   * 直接把键省掉（否则"键存在但值为 undefined"与"不带该维度"在语义上会混淆）。
   */
  function buildRequestParam(semester, openingSchoolNumber) {
    if (openingSchoolNumber === undefined) {
      return { yearTerm: semester };
    }

    var param = { yearTerm: semester };
    param[SHARD_PARAM_NAME] = openingSchoolNumber;
    return param;
  }

  /**
   * 取一页：same-origin POST，认证状态由浏览器自己带上。
   *
   * `openingSchoolNumber` 为 `undefined` 时是 **baseline（全量）** 请求；
   * 传入已批准校区号时是 **该 shard** 的请求。
   *
   * `pacer` 为本次 run 的**全局 pacing controller**：
   * - 发请求**之前**调用 `beforeRequest()`（⛔ 这是唯一的等待入口）；
   * - 响应校验**成功**后调用 `noteSuccess()`（推进全局批次计数）。
   *
   * ⚠️ 一次性诊断入口（2C1B / 2C1C）只发 1 次请求、不传 `pacer`：
   * 它们不受批次影响，也⛔ 不改动任何计数。
   *
   * `?_t=` 只是**复现已观察到的请求形态**（已观察请求带时间戳参数），
   * 不代表任何业务语义。
   */
  async function requestPage(semester, pageNo, pageSize, openingSchoolNumber, pacer) {
    if (pacer) {
      await pacer.beforeRequest();
    }

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
          param: buildRequestParam(semester, openingSchoolNumber)
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

    var data = validatePagePayload(payload, pageNo);

    // ⛔ 只有"HTTP 200 且 code 200 且结构合法"才算成功：全局批次计数只在这里推进。
    if (pacer) {
      pacer.noteSuccess();
    }

    return data;
  }

  // ---------------------------------------------------------------------
  // 主流程：必须由用户显式调用
  // ---------------------------------------------------------------------

  /**
   * 校验并解析 `collect()` / `collectSharded()` **共用**的分页选项。
   *
   * ⛔ 只接受 SYSU 已验证的取值；⛔ 校验全部发生在**任何取页调用之前**。
   */
  function resolvePagingOptions(opts) {
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
      fail(
        "delayMs 不得小于 " + MIN_DELAY_MS + " 毫秒" +
          "（同一 endpoint 的 conservative operational minimum，来自人工实测；" +
          "只能调大，不能调小）。"
      );
    }

    return {
      semester: semester,
      pageSize: pageSize,
      firstPageNo: firstPageNo,
      maxPages: maxPages,
      delayMs: delayMs
    };
  }

  /**
   * **唯一**的分页循环（`collect()` 与每个 shard 都走这里）。
   *
   * - 严格串行：一页一页取；⛔ 不并发、⛔ 不预取、⛔ 不重试、⛔ 不跳页；
   * - `firstPageNo` 恒为 `FIRST_PAGE_NO`（1）：调用方**无法**改变起始页；
   * - `expectedTotal` 取**本次第一页**的 `data.total`；中途变化 → 整体失败；
   * - `accumulatedRows === expectedTotal` → `reached_total` 并停止；
   * - **pacing**：本循环**不自己 sleep、也不自己计数**；每一对相邻请求的间隔
   *   （含批次冷却）全部由传入的**全局 pacing controller** 在 `requestPage()`
   *   里统一保证 —— 见 `createRequestPacer()`。
   *
   * ⚠️ `openingSchoolNumber === undefined` 时为 **baseline（全量）** 请求形态；
   * 传入已批准校区号时为**该 shard** 的请求形态。
   *
   * 返回值只有结构性计数与**已脱敏**的 pages（不判断完整性、不产出 bundle）。
   */
  async function collectPages(semester, pageSize, maxPages, pacer, openingSchoolNumber) {
    var pages = [];
    var expectedTotal = null;
    var accumulatedRows = 0;
    var requests = 0;
    var stoppedReason = "max_pages";

    for (var index = 0; index < maxPages; index += 1) {
      var currentPageNo = FIRST_PAGE_NO + index;

      var data = await requestPage(semester, currentPageNo, pageSize, openingSchoolNumber, pacer);
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
      pages: pages,
      expectedTotal: expectedTotal,
      accumulatedRows: accumulatedRows,
      requests: requests,
      stoppedReason: stoppedReason
    };
  }

  /**
   * 只读**一页**并返回其 `data.total`（baseline 探针）。
   *
   * ⛔ 请求体**只有** `yearTerm`（不带 `openingSchoolNumber`）；
   * ⛔ 不做字段最小化、⛔ 不做脱敏、⛔ 不产出 bundle —— 它只读一个整数。
   * ⛔ 只发**一次**请求（不循环、不重试）。
   *
   * ⚠️ 它**也走同一个全局 pacing controller**：`baseline_before` 与
   * `baseline_after` 都计入全局请求数（⛔ 不是"免费请求"）。
   */
  async function requestReportedTotal(semester, pacer) {
    var data = await requestPage(semester, FIRST_PAGE_NO, SHARD_PAGE_SIZE, undefined, pacer);
    return data.total;
  }

  async function collect(options) {
    requireAllowedHost();

    var opts = options || {};
    var resolved = resolvePagingOptions(opts);

    // 超过默认 smoke 页数时，必须由用户明确确认。
    if (resolved.maxPages > DEFAULT_MAX_PAGES) {
      var confirmed = window.confirm(
        "即将对本人已授权可见的 " + resolved.semester + " 开课数据执行串行采集。\n" +
          "pageSize=" + resolved.pageSize + "\n" +
          "最多请求 " + resolved.maxPages + " 页\n" +
          "请求间隔至少 " + resolved.delayMs / 1000 + " 秒\n" +
          "批次策略：每 " + MAX_REQUESTS_PER_BATCH + " 个成功请求后冷却 " +
          BATCH_COOLDOWN_MS / 60000 + " 分钟\n" +
          "是否继续？"
      );
      if (!confirmed) {
        return { cancelled: true, requests: 0, bundle: null };
      }
    }

    // 本次 run 的**唯一** pacing controller（分页循环不再自己 sleep / 计数）。
    var pacer = createRequestPacer(resolved.delayMs);

    // ⛔ 不带 openingSchoolNumber：`collect()` 仍是**全量**（baseline）入口。
    var core = await collectPages(
      resolved.semester,
      resolved.pageSize,
      resolved.maxPages,
      pacer,
      undefined
    );

    return {
      cancelled: false,
      requests: core.requests,
      stoppedReason: core.stoppedReason,
      accumulatedRows: core.accumulatedRows,
      expectedTotal: core.expectedTotal,
      // 明确：本采集器**不判断**完整性，complete / partial 交给 Python Pagination Core。
      claimedComplete: false,
      bundle: {
        format: CAPTURE_FORMAT,
        semester: resolved.semester,
        first_page_no: resolved.firstPageNo,
        page_size: resolved.pageSize,
        pages: core.pages
      }
    };
  }

  // ---------------------------------------------------------------------
  // 五校区 shard 编排（Architecture Review 已批准）
  //
  //   baseline_before → 五个完整 shard → baseline_after
  //     → baseline 稳定性（snapshot window unstable？）
  //     → shard 覆盖性（shard coverage mismatch？）
  //
  // ⛔ 不改 Capture Bundle format：每个 shard 产出仍是**同一格式**的裸 bundle；
  // ⛔ diagnostics **不进入**任何裸 bundle；
  // ⛔ 不绕过深分页（offset >= 6500 的 HTTP 600 由**校区维度分片**规避，
  //    而不是靠跳页 / 重编号 / 重试）。
  // ---------------------------------------------------------------------

  /** `collectSharded()` 严格白名单允许的 options 键（其余一律在发请求前拒绝）。 */
  var SHARDED_ALLOWED_OPTIONS = ["semester", "maxPages", "delayMs"];

  /**
   * 抛出一个**带 diagnostics 的错误**。
   *
   * ⛔ 整体失败时**不产出任何 bundle**；但把已经采集到的结构化计数附在
   * `error.diagnostics` 上，方便操作者在控制台查看：
   *
   *     try { await collectSharded(...) } catch (e) { console.log(e.diagnostics) }
   */
  function failWithDiagnostics(message, diagnostics) {
    var error = new Error(ERROR_PREFIX + message);
    error.diagnostics = diagnostics;
    throw error;
  }

  /**
   * 五校区 shard 采集编排。
   *
   * ```text
   * ① baseline_before（{yearTerm} 单次探针，只读 total）
   *        ↓
   * ② 五个 shard 依次串行采集（每个 shard 从 pageNo=1 开始、pageSize=200、
   *   expectedTotal 取**本 shard 第一页**真实 total、accumulatedRows == expectedTotal
   *   时以 reached_total 停止；保留既有 delay / guard / fail-closed）
   *        ↓
   * ③ baseline_after（五个 shard 全部完整成功后**无条件**请求；同 baseline_before）
   *        ↓
   * ④ baseline 稳定性：baseline_before == baseline_after？
   *        ↓（稳定才继续）
   * ⑤ shard 覆盖性：Σ shard expectedTotal == baseline_before？
   * ```
   *
   * 整体失败（`fail()` 抛出，⛔ **不产出任何 bundle**）的情形：
   *
   * 1. 任一 shard 未取满（`stoppedReason !== "reached_total"`）→ **立即**停止，
   *    ⛔ 不再请求 baseline_after，也⛔ 不再请求后面的校区（fail fast）；
   * 2. `baseline_before !== baseline_after` → **snapshot window unstable**；
   * 3. Σ shard `expectedTotal` != baseline_before → **shard coverage mismatch**
   *    （与 Python 侧已 Review 的编排同一口径；这里只是**提前**失败，
   *    完整性判定的**权威仍在 Python**）。
   *
   * ⛔ **判定顺序是硬要求**：五个 shard 都完整成功后，必须**无条件**先取
   * baseline_after 并判稳定性；**只有** baseline 稳定之后才允许判覆盖性。
   * 否则会拿一个未确认的 snapshot window 去解释覆盖差异。
   *
   * ⛔ **pacing（全局 batch pacing）**：本函数创建**一个**全局 pacing controller，
   * 它同时管 `baseline_before`、所有 shard 的每一页、以及 `baseline_after`：
   *
   * ```text
   * 第 1 个请求（= baseline_before）立即发送
   * 其它相邻请求                  ：先等 delayMs（默认 = 下限 = 30000ms）
   * 全局已累计 5 个成功请求时     ：改为先等 max(BATCH_COOLDOWN_MS, delayMs)
   *                                = 300000ms（冷却本身 > 普通间隔，⛔ 不叠加）
   * ```
   *
   * ⛔ 计数是**整个 sharded collection 的全局计数**，
   * ⛔ **不是 per-shard**、⛔ 不会在 shard 边界重置（跨 shard / 跨 baseline 连续计数）。
   * 例如全局第 5、10 个请求之后都会先冷却 5 分钟，再发第 6、11 个请求。
   *
   * ⛔ 因此 "5-request batch + 5-minute cooldown" 是**当前保守运营策略**
   * （人工实测：`pageSize=50` + 30 秒间隔连续 7 次成功后第 8 次即 `HTTP 600`），
   * ⛔ **不是学校公开阈值**。
   * ⛔ `HTTP 600` 仍然只是 **fail closed**：⛔ 不重试、⛔ 不做 backoff 重试、
   * ⛔ 不跳页、⛔ 不续采、⛔ 不做任何认证绕行。
   *
   * ⛔ 严格白名单：只接受 `semester` / `maxPages` / `delayMs`。
   * ⛔ 不接受调用方传入 `pageSize` / `firstPageNo` / 自定义 shard 列表，
   * 也⛔ 不接受调用方覆盖 batch 大小 / 冷却时长。
   */
  async function collectSharded(options) {
    requireAllowedHost();

    var opts = options || {};

    var optionNames = Object.keys(opts);
    var unexpected = optionNames.filter(function (name) {
      return SHARDED_ALLOWED_OPTIONS.indexOf(name) === -1;
    });
    if (unexpected.length > 0) {
      fail(
        "五校区采集只接受 " + SHARDED_ALLOWED_OPTIONS.join(" / ") +
          "（收到 " + unexpected.length + " 个其它参数）。已停止；参数名不予回显。"
      );
    }

    var resolved = resolvePagingOptions(opts);

    // ⛔ pageSize 不在白名单里：下面的取值恒为已人工验证的 SHARD_PAGE_SIZE。
    var pageSize = SHARD_PAGE_SIZE;

    if (resolved.maxPages > DEFAULT_MAX_PAGES) {
      var confirmed = window.confirm(
        "即将对本人已授权可见的 " + resolved.semester + " 开课数据执行**五校区串行采集**。\n" +
          "请求顺序：baseline → " + APPROVED_SHARDS.length + " 个校区 shard → baseline\n" +
          "pageSize=" + pageSize + "\n" +
          "每个 shard 最多请求 " + resolved.maxPages + " 页\n" +
          "请求间隔至少 " + resolved.delayMs / 1000 + " 秒\n" +
          "批次策略：**全局**每 " + MAX_REQUESTS_PER_BATCH + " 个成功请求后冷却 " +
          BATCH_COOLDOWN_MS / 60000 + " 分钟（跨 shard / 跨 baseline 连续计数）\n" +
          "是否继续？"
      );
      if (!confirmed) {
        return { cancelled: true, requests: 0, shards: [], diagnostics: null };
      }
    }

    // 本次 run 的**唯一** pacing controller：
    // ⛔ 全局一个实例，计数覆盖 baseline_before + 所有 shard 的页 + baseline_after。
    var pacer = createRequestPacer(resolved.delayMs);

    var requests = 0;
    var baselineBefore = null;
    var baselineAfter = null;
    var shardResults = [];
    var shardDiagnostics = [];

    /**
     * 当前已采集到的**外层 diagnostics**（失败时也用它，所以是"增量快照"）。
     *
     * 字段名照 Architecture Review 给定的清单。
     */
    function makeDiagnostics() {
      var totalSum = 0;
      var pageSum = 0;
      for (var index = 0; index < shardDiagnostics.length; index += 1) {
        totalSum += shardDiagnostics[index].expectedTotal;
        pageSum += shardDiagnostics[index].expected_pages;
      }

      return {
        semester: resolved.semester,
        page_size: pageSize,
        shard_count: shardDiagnostics.length,
        approved_shard_count: APPROVED_SHARDS.length,
        baseline_before: baselineBefore,
        baseline_after: baselineAfter,
        shard_total_sum: totalSum,
        // ⛔ 只作 diagnostics：不得参与任何完整性 / complete 判定。
        expected_pages_total: pageSum,
        shards: shardDiagnostics.slice()
      };
    }

    // ---- baseline_before（也是全局请求计数的第 1 个请求） ------------------
    baselineBefore = await requestReportedTotal(resolved.semester, pacer);
    requests += 1;

    // ---- 五个 shard：**串行**，顺序即已批准顺序 --------------------------
    for (var shardIndex = 0; shardIndex < APPROVED_SHARDS.length; shardIndex += 1) {
      var shard = APPROVED_SHARDS[shardIndex];

      // ⛔ 这里**不再 sleep**：跨 shard / 跨页 / 跨批次的间隔全部由全局 pacer
      // 在 requestPage() 里统一保证。
      var core;
      try {
        core = await collectPages(
          resolved.semester,
          pageSize,
          resolved.maxPages,
          pacer,
          shard.openingSchoolNumber
        );
      } catch (error) {
        // ⛔ 不回显任何 row 取值：下层错误信息本身只含页码 / 字段名 / 计数。
        // 带上本次已经采集到的 diagnostics，失败原因与进度都能在控制台看到。
        failWithDiagnostics(
          "shard " + shard.shard_id + " 采集失败：" + unwrapErrorMessage(error) +
            "（已整体停止，不产出任何 bundle）",
          makeDiagnostics()
        );
      }
      requests += core.requests;

      shardDiagnostics.push({
        shard_id: shard.shard_id,
        openingSchoolNumber: shard.openingSchoolNumber,
        expectedTotal: core.expectedTotal,
        accumulatedRows: core.accumulatedRows,
        stoppedReason: core.stoppedReason,
        page_count: core.pages.length,
        // ⛔ 只作 diagnostics（ceil(expectedTotal / pageSize)）：
        //    不得参与任何完整性判定；页码数不是证据。
        expected_pages: Math.ceil(core.expectedTotal / pageSize)
      });

      // ② 任一 shard 未取满 → 立即整体停止（不再继续打学校接口）。
      if (core.stoppedReason !== "reached_total" || core.accumulatedRows !== core.expectedTotal) {
        failWithDiagnostics(
          "shard " + shard.shard_id + " 未取满：累计 " + core.accumulatedRows +
            " / total " + core.expectedTotal + "（停止原因 " + core.stoppedReason +
            "）。已整体停止，不产出任何 bundle；请提高 maxPages 后重跑。",
          makeDiagnostics()
        );
      }

      shardResults.push({
        shard_id: shard.shard_id,
        openingSchoolNumber: shard.openingSchoolNumber,
        expectedTotal: core.expectedTotal,
        accumulatedRows: core.accumulatedRows,
        stoppedReason: core.stoppedReason,
        // 裸 Capture Bundle：顶层只有 format / semester / first_page_no / page_size / pages。
        bundle: {
          format: CAPTURE_FORMAT,
          semester: resolved.semester,
          first_page_no: resolved.firstPageNo,
          page_size: pageSize,
          pages: core.pages
        }
      });
    }

    // ---- baseline_after（③ 五个 shard **全部完整成功后无条件请求**） --------
    // ⛔ 顺序是 Review 裁定的：先 baseline 稳定性，再 shard 覆盖性。
    //    覆盖性**不得**抢在 baseline_after 之前判定（那会拿一个未确认的
    //    snapshot window 去解释覆盖差异）。
    // pacing：baseline_after **也走同一个全局 pacer**（计入全局请求数与批次）。
    baselineAfter = await requestReportedTotal(resolved.semester, pacer);
    requests += 1;

    // ④ baseline 稳定性：不等价 → snapshot window unstable，整体失败。
    if (baselineBefore !== baselineAfter) {
      failWithDiagnostics(
        "baseline_before(" + baselineBefore + ") != baseline_after(" + baselineAfter +
          ")：snapshot window unstable —— 该学期数据集合在采集窗口内发生变化" +
          "（历史 6892 → 现 6880 属已知漂移）。已整体停止，不产出任何 bundle。",
        makeDiagnostics()
      );
    }

    // ⑤ shard 覆盖性：**只有** baseline 稳定后才判定。
    var coveredTotal = 0;
    for (var coverIndex = 0; coverIndex < shardDiagnostics.length; coverIndex += 1) {
      coveredTotal += shardDiagnostics[coverIndex].expectedTotal;
    }
    if (coveredTotal !== baselineBefore) {
      failWithDiagnostics(
        "五个 shard 的 total 之和(" + coveredTotal + ") != baseline_before(" + baselineBefore +
          ")：shard coverage mismatch —— 分片未覆盖全体或与基线不一致。" +
          "已整体停止，不产出任何 bundle。",
        makeDiagnostics()
      );
    }

    return {
      cancelled: false,
      requests: requests,
      semester: resolved.semester,
      page_size: pageSize,
      shards: shardResults,
      diagnostics: makeDiagnostics()
    };
  }

  /**
   * 取某个 shard 的**裸** Capture Bundle（对象，可直接交给 Python `load_capture_bundle`）。
   *
   * ⛔ 只接受**成功完成**的五校区采集结果；⛔ **不把 diagnostics 塞进 bundle**；
   * ⛔ 找不到该 shard 时失败，且**不回显**调用方给出的名字。
   */
  function shardBundle(result, shardId) {
    if (!result || result.cancelled === true || !Array.isArray(result.shards)) {
      fail(
        "没有可用的五校区采集结果（采集被取消或未完成）。本采集器不会生成伪 bundle。"
      );
    }

    for (var index = 0; index < result.shards.length; index += 1) {
      if (result.shards[index].shard_id === shardId) {
        return result.shards[index].bundle;
      }
    }

    fail("五校区采集结果里没有该 shard（只接受五个已批准校区名）。");
  }

  /** 某个 shard 裸 Capture Bundle 的 JSON 文本（⛔ 不含 diagnostics）。 */
  function toShardJson(result, shardId) {
    return JSON.stringify(shardBundle(result, shardId), null, 2);
  }

  /** 外层 diagnostics 的 JSON 文本（⛔ diagnostics **不**进入任何裸 bundle）。 */
  function toDiagnosticsJson(result) {
    if (!result || result.cancelled === true || !result.diagnostics) {
      fail("没有可序列化的 diagnostics（采集被取消或未完成）。");
    }
    return JSON.stringify(result.diagnostics, null, 2);
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
    // ⛔ **不传第 4 个参数** = baseline（全量）形态：请求体只有 `yearTerm`，不做任何分片。
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
  // 一次性 Layout B 诊断（**零留存**；Architecture Review 裁定）
  //
  // ⛔ 只在内存中比较 **minimize 之前的 raw row**，且只返回**聚合计数**：
  //    不回显 teachingName / f3 / f4 / 课程号 / 教学班号 / 原文；
  //    不产出 bundle、不落盘、不写日志文件、不保存 raw response。
  // ⛔ 不参与生产链路：`collect()` / `collectSharded()` 都不调用它。
  // ---------------------------------------------------------------------

  /** Layout B 候选的字段数（已确认 4 字段）。 */
  var LAYOUT_B_FIELD_COUNT = 4;

  /**
   * Layout B 诊断允许的 options（**严格白名单**）。
   *
   * ⛔ 不开放 `pageSize` / `firstPageNo` / `delayMs`：诊断恒用已验证的默认口径
   * （`pageSize=200`、`firstPageNo=1`、`delayMs>=30000`）。
   */
  var LAYOUT_B_ALLOWED_OPTIONS = ["semester", "openingSchoolNumber", "maxPages"];

  /**
   * 已批准 **weeks** 形状（与 Python `expand_weeks()` 的已批准 grammar **同规则**）。
   *
   * ⛔ 整段锚定、⛔ 无 `.*`、⛔ 不做 `startswith` / 去前缀 / 大小写折叠。
   */
  var LAYOUT_B_WEEKS_PATTERNS = [
    /^[0-9]+-[0-9]+周$/,
    /^[0-9]+-[0-9]+(单周|双周)$/,
    /^[0-9]+-[0-9]+周(校外|校内\(户外\))$/
  ];

  /**
   * 已批准 **sections** 形状（与 Python `parse_sections()` 的已批准 grammar **同规则**）。
   *
   * ⚠️ 本诊断只用它**排除**「f3 是 sections」的情形（Layout B 定义要求没有 sections）。
   */
  var LAYOUT_B_SECTIONS_PATTERN = /^第[0-9]+-[0-9]+节(校内\(户外\)|校外|线上)?$/;

  /** `f1` 是否是已批准的 weeks token（仅结构判定，**不返回取值**）。 */
  function isApprovedWeeksToken(token) {
    for (var index = 0; index < LAYOUT_B_WEEKS_PATTERNS.length; index += 1) {
      if (LAYOUT_B_WEEKS_PATTERNS[index].test(token)) {
        return true;
      }
    }
    return false;
  }

  /**
   * 判断一个**已脱敏前**的 segment 是否属于 Layout B 候选。
   *
   * ```text
   * 4 fields
   * f1 = 已确认 weeks
   * f2 = 已确认 location（复用现有判别器：>= 3 个非空 "-" 分段）
   *      ⇒ 同时排除 weekday（weekday token 不含 "-"）
   * f3 ≠ 已确认 sections
   * ```
   *
   * ⛔ 只做**结构**判定：不比对课程名 / 教师名 / 学院，不做模糊匹配；
   * ⛔ 返回值只有 true / false（**不返回任何字段取值**）。
   */
  function isLayoutBCandidate(segment) {
    var fields = segment.split(FIELD_SEPARATOR);

    if (fields.length !== LAYOUT_B_FIELD_COUNT) {
      return false;
    }

    if (!isApprovedWeeksToken(fields[0].trim())) {
      return false;
    }

    if (countNonEmptyDashSegments(fields[1].trim()) < MIN_LOCATION_SEGMENTS) {
      return false;
    }

    if (LAYOUT_B_SECTIONS_PATTERN.test(fields[2].trim())) {
      return false;
    }

    return true;
  }

  /** activity 的**现有**规则：非空字符串（与 Python `_require_non_empty_token` 同规则）。 */
  function isNonEmptyActivityToken(token) {
    return typeof token === "string" && token.trim() !== "";
  }

  // ---------------------------------------------------------------------
  // 已确认 layout 的 **activity 固定槽位**（Architecture Review 裁定 2026-10-05）
  //
  // ⛔ 字段**角色**只由 layout 结构确定（字段数 + 各槽位是否命中已批准 grammar）；
  // ⛔ **不**用"非空字符串 = activity"当角色证据；
  // ⛔ 不比对课程名 / 教师名 / 学院，⛔ 无姓名启发式，⛔ 无 CJK 长度猜测。
  // ---------------------------------------------------------------------

  /** 已确认 weekday 白名单（与 Python `_WEEKDAY_BY_TOKEN` **同集合**；⛔ 无通配）。 */
  var CONFIRMED_WEEKDAY_TOKENS = [
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日"
  ];

  /** 已确认 **non-concrete** 2 / 3 字段的 f1 形状（⛔ **不含** parity：Python 那两条路径只认 `N-M周`）。 */
  var CONFIRMED_NON_CONCRETE_WEEKS_PATTERNS = [
    /^[0-9]+-[0-9]+周$/,
    /^[0-9]+-[0-9]+周(校外|校内\(户外\))$/
  ];

  /** 已确认 weeks 的三种形状（含 parity；用于 layout A 的 f1）。 */
  var CONFIRMED_PLAIN_WEEKS_PATTERN = /^([0-9]+)-([0-9]+)周$/;
  var CONFIRMED_PARITY_WEEKS_PATTERN = /^([0-9]+)-([0-9]+)(单周|双周)$/;
  var CONFIRMED_QUALIFIED_WEEKS_PATTERN = /^([0-9]+)-([0-9]+)周(校外|校内\(户外\))$/;

  /** 已确认 sections：`第N-M节` + 已批准 suffix（与 Python `_SECTION_PATTERN` 同规则）。 */
  var CONFIRMED_SECTIONS_PATTERN = /^第([0-9]+)-([0-9]+)节(校内\(户外\)|校外|线上)?$/;

  function isConfirmedWeekdayToken(token) {
    return CONFIRMED_WEEKDAY_TOKENS.indexOf(token) !== -1;
  }

  /**
   * 已确认 weeks token？与 Python `expand_weeks()` 的**接受集合**同规则：
   *
   * ```text
   * N-M周 / N-M单周 / N-M双周 / N-M周校外 / N-M周校内(户外)
   * 且 N >= 1、M >= N；单/双周在区间内必须至少有一个对应 parity 的周
   * ```
   *
   * ⛔ 整段锚定；⛔ 无 `.*` / `startswith` / 无条件 strip。
   */
  function isConfirmedWeeksToken(token) {
    var match = CONFIRMED_PLAIN_WEEKS_PATTERN.exec(token);
    var parity = null;

    if (match === null) {
      match = CONFIRMED_PARITY_WEEKS_PATTERN.exec(token);
      if (match !== null) {
        parity = match[3];
      }
    }
    if (match === null) {
      match = CONFIRMED_QUALIFIED_WEEKS_PATTERN.exec(token);
    }
    if (match === null) {
      return false;
    }

    var start = Number(match[1]);
    var end = Number(match[2]);
    if (start < 1 || end < start) {
      return false;
    }

    if (parity !== null) {
      for (var week = start; week <= end; week += 1) {
        if (parity === "单周" ? week % 2 === 1 : week % 2 === 0) {
          return true;
        }
      }
      return false;
    }

    return true;
  }

  /** `f1` 是否是已确认 non-concrete（2 / 3 字段）的 weeks token（形状 + 数值，⛔ 不含 parity）。 */
  function isConfirmedNonConcreteWeeksToken(token) {
    for (var index = 0; index < CONFIRMED_NON_CONCRETE_WEEKS_PATTERNS.length; index += 1) {
      if (!CONFIRMED_NON_CONCRETE_WEEKS_PATTERNS[index].test(token)) {
        continue;
      }
      return isConfirmedWeeksToken(token);
    }
    return false;
  }

  /** 已确认 sections token（形状 + `N >= 1`、`M >= N`）？ */
  function isConfirmedSectionsToken(token) {
    var match = CONFIRMED_SECTIONS_PATTERN.exec(token);
    if (match === null) {
      return false;
    }
    var start = Number(match[1]);
    var end = Number(match[2]);
    return start >= 1 && end >= start;
  }

  /** 通用 location grammar（与 Python `_is_location_token` 同规则：非空园区 + `-` + 非空教室）。 */
  function isGeneralLocationToken(token) {
    if (typeof token !== "string") {
      return false;
    }
    var separatorIndex = token.indexOf("-");
    if (separatorIndex === -1) {
      return false;
    }
    return (
      token.slice(0, separatorIndex).trim() !== "" &&
      token.slice(separatorIndex + 1).trim() !== ""
    );
  }

  /**
   * 返回**已确认 layout** 的 activity **固定槽位下标**；不是已确认 layout → `-1`。
   *
   * 已确认 layout（与 production parser 的已确认 grammar **同规则**）：
   *
   * ```text
   * 2 字段：weeks(plain|+已确认 qualifier) / activity                       → 槽位 1
   * 3 字段：weeks(plain|+已确认 qualifier) / teacher / activity             → 槽位 2
   * 4 字段：weeks / weekday / sections / activity                           → 槽位 3
   * 5 字段 layout A：weeks / weekday / location / REDACTED / activity       → 槽位 4
   * 5 字段 concrete：weeks / weekday / sections / location-or-teacher / activity → 槽位 4
   * 6 字段：weeks / weekday / sections / location / teacher / activity      → 槽位 5
   * ```
   *
   * ⛔ 5 字段 f4 若**二义**（既非明确 location 也非明确 teacher）→ 不算已确认（返回 `-1`）；
   * ⛔ layout A 的 f4 必须**精确等于** `REDACTED`（⛔ 无前缀 / 包含 / 通配 / 空白容忍）；
   * ⛔ 返回的只是**下标**（⛔ 不返回任何取值）。
   */
  function confirmedActivitySlotIndex(segment) {
    var fields = segment.split(FIELD_SEPARATOR);
    var fieldCount = fields.length;
    var third;
    var classification;

    if (fieldCount === 2) {
      if (!isConfirmedNonConcreteWeeksToken(fields[0].trim())) {
        return -1;
      }
      if (!isNonEmptyActivityToken(fields[1])) {
        return -1;
      }
      return 1;
    }

    if (fieldCount === 3) {
      if (!isConfirmedNonConcreteWeeksToken(fields[0].trim())) {
        return -1;
      }
      if (!isNonEmptyActivityToken(fields[1])) {
        return -1;
      }
      if (!isNonEmptyActivityToken(fields[2])) {
        return -1;
      }
      return 2;
    }

    if (fieldCount === 4) {
      if (!isConfirmedWeekdayToken(fields[1].trim())) {
        return -1;
      }
      if (!isConfirmedSectionsToken(fields[2].trim())) {
        return -1;
      }
      if (!isNonEmptyActivityToken(fields[3])) {
        return -1;
      }
      return 3;
    }

    if (fieldCount === 5) {
      // layout A（已批准；必须**先**判定：它的第 3 个字段是 location，不是 sections）
      if (
        isConfirmedWeeksToken(fields[0].trim()) &&
        isConfirmedWeekdayToken(fields[1].trim()) &&
        countNonEmptyDashSegments(fields[2].trim()) >= MIN_LOCATION_SEGMENTS &&
        fields[3] === REDACTED_TEACHER &&
        isNonEmptyActivityToken(fields[4])
      ) {
        return 4;
      }

      // concrete 5 字段：weeks / weekday / sections / location-or-teacher / activity
      if (!isConfirmedWeekdayToken(fields[1].trim())) {
        return -1;
      }
      if (!isConfirmedSectionsToken(fields[2].trim())) {
        return -1;
      }
      third = fields[3].trim();
      classification = classifyFiveFieldToken(third);
      if (classification === "ambiguous") {
        return -1;
      }
      if (!isNonEmptyActivityToken(fields[4])) {
        return -1;
      }
      return 4;
    }

    if (fieldCount === 6) {
      if (!isConfirmedWeekdayToken(fields[1].trim())) {
        return -1;
      }
      if (!isConfirmedSectionsToken(fields[2].trim())) {
        return -1;
      }
      if (!isGeneralLocationToken(fields[3])) {
        return -1;
      }
      if (!isNonEmptyActivityToken(fields[4])) {
        return -1;
      }
      if (!isNonEmptyActivityToken(fields[5])) {
        return -1;
      }
      return 5;
    }

    return -1;
  }

  /** 多重集自增（token → 出现次数）；⛔ 只在内存中使用，⛔ 不返回、⛔ 不落盘。 */
  function addTokenOccurrence(multiset, token) {
    var current = multiset.get(token);
    multiset.set(token, current === undefined ? 1 : current + 1);
  }

  // ---------------------------------------------------------------------
  // Layout B 候选 `f3` 的**原始字段名命中**统计（Architecture Review 裁定 2026-10-05）
  //
  // 目的：`f3 == teachingName` 与 `f3 ∈ 已确认 activity 集合` 都是 0，
  //       因此用**严格字符串相等**在 raw row 的**字符串字段**里找出 f3 命中哪些字段。
  //
  // ⛔ 只输出**字段名**与命中次数（⛔ 不输出 raw value / f3 原文 / teacher name / 任何 id）；
  // ⛔ 只做**严格相等**（⛔ 无模糊匹配 / ⛔ 无 substring / ⛔ 无分词 / ⛔ 无大小写折叠）；
  // ⛔ 多个字段同时命中 → **全部保留**（⛔ 不自行裁定哪一个才是答案）。
  // ---------------------------------------------------------------------

  /**
   * 明确排除的字段名（Architecture Review 清单 + collector 既有字段）。
   *
   * ⛔ 这些是**精确**字段名，不参与 f3 命中统计。
   */
  var LAYOUT_B_F3_MATCH_EXCLUDED_FIELDS = [
    // 非 ID 但同样不参与（体积大 / 无诊断价值 / 属排课原文）
    "courseNum",
    "classNumber",
    "teachingTimePlaceStr",
    // Architecture Review 明确列出的内部 ID 字段
    "courseId",
    "class_ID",
    "sumClassesID",
    "outLineId",
    "timePlaceId"
  ];

  /**
   * 内部 ID 字段名的**词法边界**判定（**机械**规则，⛔ 不猜业务语义）。
   *
   * ```text
   * id     / ID / Id / iD  （整个字段名就是 id，忽略大小写）
   * xxxId  （驼峰）
   * xxxID  （全大写后缀）
   * xxx_id / xxx_ID / xxx_Id …（下划线 + id，忽略大小写）
   * ```
   *
   * ⛔ **不再**使用"任意以 `id` 两个字符结尾"的规则：
   * `valid` / `invalid` / `hybrid` 这类**普通单词**必须**参与**统计
   * （过度排除会造成 false negative，降低诊断证明力）。
   *
   * ⚠️ 按裁定的**词法边界**要求，全小写且无分隔符的 `xxxid`（如 `courseid`）
   * **没有** ID 边界 ⇒ **不**排除；若要覆盖该形态，需要 Review 给出明确规则。
   */
  var LAYOUT_B_F3_MATCH_ID_SUFFIXES = ["Id", "ID"];

  /** `_id` / `_ID` / `_Id` …（下划线 + id，忽略大小写）。 */
  var LAYOUT_B_F3_MATCH_ID_UNDERSCORE_PATTERN = /_id$/i;

  /** 字段名是否具有内部 ID 的**词法形状**（⛔ 必须有边界）。 */
  function hasInternalIdShape(fieldName) {
    if (fieldName.toLowerCase() === "id") {
      return true;
    }

    for (var index = 0; index < LAYOUT_B_F3_MATCH_ID_SUFFIXES.length; index += 1) {
      if (fieldName.endsWith(LAYOUT_B_F3_MATCH_ID_SUFFIXES[index])) {
        return true;
      }
    }

    return LAYOUT_B_F3_MATCH_ID_UNDERSCORE_PATTERN.test(fieldName);
  }

  /** 该字段名是否被排除在 f3 命中统计之外（精确清单 + ID 词法形状）。 */
  function isExcludedMatchFieldName(fieldName) {
    if (LAYOUT_B_F3_MATCH_EXCLUDED_FIELDS.indexOf(fieldName) !== -1) {
      return true;
    }
    return hasInternalIdShape(fieldName);
  }

  /** 多重集中命中集合的出现次数合计。 */
  function countMultisetTokensInSet(multiset, tokenSet) {
    var total = 0;
    multiset.forEach(function (occurrences, token) {
      if (tokenSet.has(token)) {
        total += occurrences;
      }
    });
    return total;
  }

  /**
   * **一次性、零留存** Layout B 诊断：串行拉取若干页，在**minimize 之前**对 raw rows
   * 做内存比较，最终**只**返回**七个聚合计数**。
   *
   * ```text
   * candidate_count                     Layout B 候选 segment 数
   * comparable_teaching_name_count      其中 raw row **带** teachingName 属性者
   * f3_equals_teaching_name_count       其中 f3 === row.teachingName 者
   * f4_equals_teaching_name_count       其中 f4 === row.teachingName 者
   * f4_activity_count                   其中 f4 满足现有 activity 非空规则者（⛔ 仅语法检查）
   * f3_in_confirmed_activity_set_count  其中 f3 ∈ 已确认 activity 集合者
   * f4_in_confirmed_activity_set_count  其中 f4 ∈ 已确认 activity 集合者
   * f3_matching_raw_fields              字段名 → "f3 严格等于该字段的候选数"（只含 **>= 1** 命中）
   * ```
   *
   * `f3_matching_raw_fields` 只遍历 raw row 的**字符串类型字段**，只做**严格相等**
   * （⛔ 无模糊匹配 / substring / 分词），并排除 `courseNum` / `classNumber` /
   * `teachingTimePlaceStr` 与**内部 ID 字段**（见 `isExcludedMatchFieldName()`）；
   * 多个字段同时命中时**全部保留**（⛔ 不自行裁定）。⛔ 只输出**字段名**与计数，
   * ⛔ 不输出任何 raw value / f3 原文 / teacher name / 课程与教学班标识。
   *
   * **已确认 activity 集合**只来自**已确认 layout 的 activity 固定槽位**
   * （见 `confirmedActivitySlotIndex()`），**只在内存中构造**，⛔ 不返回、⛔ 不落盘、
   * ⛔ 不写 bundle、⛔ 不写日志；集合里**没有任何取值被输出**。
   *
   * ⚠️ **顺序无关**：候选的 f3 / f4 先计入两个**极小的内存多重集**，等**全部页**扫完后
   * 才与集合求交 ⇒ 候选出现在"提供该 activity token 的那一行**之前**"也不会被误判成
   * 不在集合中（否则会得出错误的字段角色结论）。两个多重集同样 ⛔ 不返回、⛔ 不落盘。
   *
   * ⛔ "非空字符串 = activity" **只作为语法检查**保留（`f4_activity_count`），
   * **本轮不作为字段角色证据**（角色只由 layout 结构确定）。
   *
   * - ⛔ **不输出** teachingName / f3 / f4 / activity token / 课程号 / 教学班号 / 原文；
   * - ⛔ **不把** teachingName 写入任何 bundle（本函数**不产出 bundle**）；
   * - ⛔ 不保存 raw response、不写日志文件（rows 只在本次循环内使用，不留引用）；
   * - ⛔ raw row **没有** `teachingName` 属性 → 只计入 `candidate_count`，
   *   `comparable_teaching_name_count` / `f3_equals_*` / `f4_equals_*` **不增加**
   *   （**不猜**、不用其它字段代替）；
   * - ⛔ 无姓名启发式、⛔ 无 CJK 长度猜测、⛔ 不比对课程名 / 教师名 / 学院；
   * - ⚠️ 扫完仍然**没有任何**已确认 activity 槽位 → **fail closed**（成员判定会退化为
   *   恒假，返回 0 会被误读为"不是 activity"）；
   * - ⛔ 不修改 `collect()` / `collectSharded()` 的任何行为；
   * - 复用既有 hostname guard / **同一**取页函数 / **同一**全局 pacing controller
   *   （⛔ 不复制认证与请求逻辑，⛔ 不自己 sleep）。
   */
  async function diagnoseLayoutBCandidates(options) {
    requireAllowedHost();

    var opts = options || {};

    var optionNames = Object.keys(opts);
    var unexpected = optionNames.filter(function (name) {
      return LAYOUT_B_ALLOWED_OPTIONS.indexOf(name) === -1;
    });
    if (unexpected.length > 0) {
      fail(
        "Layout B 诊断只接受 " + LAYOUT_B_ALLOWED_OPTIONS.join(" / ") +
          "（收到 " + unexpected.length + " 个其它参数）。已停止；参数名不予回显。"
      );
    }

    var resolved = resolvePagingOptions(opts);

    var campus = opts.openingSchoolNumber;
    if (campus !== undefined && (typeof campus !== "string" || campus.trim() === "")) {
      fail("openingSchoolNumber 必须是非空字符串（或省略）。");
    }

    if (resolved.maxPages > DEFAULT_MAX_PAGES) {
      var confirmed = window.confirm(
        "即将执行**一次性 Layout B 诊断**（只取聚合计数，不产出任何数据、不落盘）。\n" +
          "最多请求 " + resolved.maxPages + " 页；请求间隔至少 " +
          resolved.delayMs / 1000 + " 秒（含全局批次冷却）。\n" +
          "是否继续？"
      );
      if (!confirmed) {
        fail("用户取消了 Layout B 诊断：本次不产生任何计数（不返回伪造的 0）。");
      }
    }

    var pacer = createRequestPacer(resolved.delayMs);

    var candidateCount = 0;
    var comparableTeachingNameCount = 0;
    var equalThirdCount = 0;
    var equalFourthCount = 0;
    var activityCount = 0;
    var expectedTotal = null;
    var accumulatedRows = 0;

    // ---- 只在内存中的结构（⛔ 不返回（除 f3 命中字段名外）/ ⛔ 不落盘 / ⛔ 不写 bundle） ----
    // 1) 已确认 activity 集合：只来自已确认 layout 的 activity 固定槽位；
    // 2) / 3) 候选 f3、f4 的**内存多重集**：只为"顺序无关"求交，扫完即弃；
    // 4) f3 命中的**字段名 → 候选数**（唯一的对外输出，只有字段名，⛔ 无任何取值）。
    var confirmedActivityTokens = new Set();
    var candidateThirdTokens = new Map();
    var candidateFourthTokens = new Map();
    var f3FieldMatchCounts = new Map();

    for (var index = 0; index < resolved.maxPages; index += 1) {
      var currentPageNo = FIRST_PAGE_NO + index;
      var data = await requestPage(
        resolved.semester,
        currentPageNo,
        resolved.pageSize,
        campus,
        pacer
      );

      if (expectedTotal === null) {
        expectedTotal = data.total;
      } else if (data.total !== expectedTotal) {
        fail(
          "第 " + currentPageNo + " 页的 data.total 与首页不一致：" +
            "诊断期间数据集合发生变化。已整体停止（不回显任何取值）。"
        );
      }

      for (var rowIndex = 0; rowIndex < data.rows.length; rowIndex += 1) {
        var row = data.rows[rowIndex];

        if (!row || typeof row !== "object" || Array.isArray(row)) {
          fail(
            "第 " + currentPageNo + " 页第 " + (rowIndex + 1) +
              " 条记录不是对象。诊断已停止（不回显任何取值）。"
          );
        }

        var text = row[SCHEDULE_FIELD];
        if (typeof text !== "string" || text === "") {
          continue;
        }

        var segments = text.split(SEGMENT_SEPARATOR);
        if (segments.length > 1 && segments[segments.length - 1].trim() === "") {
          segments.pop();
        }

        // ⚠️ 属性**存在性**判定（不是"非空"）：缺失即不可比较 → 不猜。
        var hasTeachingName = Object.prototype.hasOwnProperty.call(row, "teachingName");

        for (var segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 1) {
          var segment = segments[segmentIndex];
          if (segment.trim() === "") {
            continue;
          }

          // ① 已确认 layout 的 **activity 固定槽位** → 只在内存中累积集合。
          //    ⛔ 不输出任何 token；⛔ 不落盘；⛔ 不写 bundle。
          var activitySlot = confirmedActivitySlotIndex(segment);
          if (activitySlot !== -1) {
            confirmedActivityTokens.add(
              segment.split(FIELD_SEPARATOR)[activitySlot].trim()
            );
          }

          // ② Layout B 候选
          if (!isLayoutBCandidate(segment)) {
            continue;
          }

          candidateCount += 1;

          var fields = segment.split(FIELD_SEPARATOR);
          var thirdField = fields[2].trim();
          var fourthField = fields[3].trim();

          if (hasTeachingName) {
            comparableTeachingNameCount += 1;
            if (thirdField === row.teachingName) {
              equalThirdCount += 1;
            }
            if (fourthField === row.teachingName) {
              equalFourthCount += 1;
            }
          }

          // ⚠️ 仅**语法**检查（⛔ 不作为字段角色证据）
          if (isNonEmptyActivityToken(fields[3])) {
            activityCount += 1;
          }

          // ⚠️ 只记入**内存多重集**：等全部页扫完后才与集合求交（顺序无关）。
          addTokenOccurrence(candidateThirdTokens, thirdField);
          addTokenOccurrence(candidateFourthTokens, fourthField);

          // ③ f3 在本行**字符串字段**里的**严格相等**命中（⛔ 只记录字段名 + 计数）
          var rowFieldNames = Object.keys(row);
          for (
            var fieldIndex = 0;
            fieldIndex < rowFieldNames.length;
            fieldIndex += 1
          ) {
            var fieldName = rowFieldNames[fieldIndex];

            if (isExcludedMatchFieldName(fieldName)) {
              continue;
            }
            if (typeof row[fieldName] !== "string") {
              continue;
            }
            if (thirdField === row[fieldName]) {
              var matchedSoFar = f3FieldMatchCounts.get(fieldName);
              f3FieldMatchCounts.set(
                fieldName,
                matchedSoFar === undefined ? 1 : matchedSoFar + 1
              );
            }
          }
        }
      }

      accumulatedRows += data.rows.length;
      if (accumulatedRows >= expectedTotal) {
        break;
      }
    }

    // ⚠️ 集合为空 ⇒ 成员判定恒假（返回 0 会被误读为"不是 activity"）→ fail closed。
    if (confirmedActivityTokens.size === 0) {
      fail(
        "本次扫描没有得到任何来自已确认 layout 的 activity 固定槽位取值：" +
          "成员判定会退化为恒假。已整体停止（不回显任何取值），" +
          "并**不返回**可能被误读的计数。"
      );
    }

    var thirdInSetCount = countMultisetTokensInSet(
      candidateThirdTokens,
      confirmedActivityTokens
    );
    var fourthInSetCount = countMultisetTokensInSet(
      candidateFourthTokens,
      confirmedActivityTokens
    );

    // ⚠️ 只输出**字段名 → 命中候选数**（只含 >= 1 次命中的字段名）；
    //    ⛔ 映射里没有任何 raw value / f3 原文 / id；字段名按码点排序，输出稳定。
    var f3MatchingRawFields = Object.fromEntries(
      Array.from(f3FieldMatchCounts.keys())
        .sort()
        .map(function (fieldName) {
          return [fieldName, f3FieldMatchCounts.get(fieldName)];
        })
    );

    return {
      candidate_count: candidateCount,
      comparable_teaching_name_count: comparableTeachingNameCount,
      f3_equals_teaching_name_count: equalThirdCount,
      f4_equals_teaching_name_count: equalFourthCount,
      f4_activity_count: activityCount,
      f3_in_confirmed_activity_set_count: thirdInSetCount,
      f4_in_confirmed_activity_set_count: fourthInSetCount,
      f3_matching_raw_fields: f3MatchingRawFields
    };
  }

  // ---------------------------------------------------------------------
  // 分段式 f3 字段来源诊断（Architecture Review 方案 D；**仅** f3 raw-field 来源确认）
  //
  // ⛔ 与完整 `diagnoseLayoutBCandidates()` **并存、互不引用**；
  //    本接口**不提供** activity-membership 计数：既不计算、也⛔ 不用 0 / null 占位，
  //    它们**不存在**于本接口的契约里（真实 one-shot 的历史结果继续作为历史证据）。
  // ⛔ 生产链路（`collect()` / `collectSharded()` / 分页核心）完全不引用本接口。
  // ⛔ checkpoint **零敏感**：只有数值计数 + 字段名 → 计数；⛔ 不落盘、⛔ 不写 bundle、
  //    ⛔ 无任何 raw value / 原文 / 标识 / 认证材料。
  // ⛔ 请求行为**完全复用**既有路径：hostname guard / `requestPage()` / 全局 pacer /
  //    页校验 / total 一致性；⛔ 不改 pacing 常量、⛔ 不 retry。
  // ⛔ 覆盖不完整 / 重复 / 重叠 / 绑定不一致 → **fail closed**（⛔ 不返回近似结果）。
  // ---------------------------------------------------------------------

  /** 分段 state 的格式版本（⛔ 不一致即 fail closed）。 */
  var LAYOUT_B_FIELD_SOURCE_STATE_VERSION = 1;

  /** 分段接口允许的 options（**严格白名单**；⛔ 不开放 pageSize / delayMs / firstPageNo）。 */
  var LAYOUT_B_FIELD_SOURCE_ALLOWED_OPTIONS = [
    "semester",
    "openingSchoolNumber",
    "startPage",
    "endPage",
    "previousState"
  ];

  /** state 顶层键（**精确**集合；多一个 / 少一个都视为被篡改 → fail closed）。 */
  var LAYOUT_B_FIELD_SOURCE_STATE_KEYS = [
    "version",
    "semester",
    "openingSchoolNumber",
    "page_size",
    "expected_total",
    "processed_pages",
    "candidate_count",
    "comparable_teaching_name_count",
    "f3_equals_teaching_name_count",
    "f4_equals_teaching_name_count",
    "f4_activity_count",
    "f3_matching_raw_fields"
  ];

  /** 最终结果的键（**恰好六个**；⛔ 不含任何 activity-membership 计数）。 */
  var LAYOUT_B_FIELD_SOURCE_RESULT_KEYS = [
    "candidate_count",
    "comparable_teaching_name_count",
    "f3_equals_teaching_name_count",
    "f4_equals_teaching_name_count",
    "f4_activity_count",
    "f3_matching_raw_fields"
  ];

  /** `processed_pages` 元素只允许这两个键（page number / count：安全数字）。 */
  var LAYOUT_B_FIELD_SOURCE_PAGE_KEYS = ["page_no", "row_count"];

  /** 非负整数校验（⛔ 不回显取值，只回显字段语义名）。 */
  function requireFieldSourceCount(value, label) {
    if (!Number.isInteger(value) || value < 0) {
      fail("分段诊断的 " + label + " 必须是非负整数；已整体停止（不回显取值）。");
    }
    return value;
  }

  /** 校验 `f3_matching_raw_fields`：字段名 → **>= 1** 的整数计数；⛔ 不接受任何取值。 */
  function readFieldMatchCounts(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      fail("f3_matching_raw_fields 必须是「字段名 → 计数」的对象；已整体停止（不回显取值）。");
    }

    var fieldNames = Object.keys(value);
    var counts = new Map();

    for (var index = 0; index < fieldNames.length; index += 1) {
      var fieldName = fieldNames[index];
      if (typeof fieldName !== "string" || fieldName === "") {
        fail("f3_matching_raw_fields 含空字段名；已整体停止（不回显取值）。");
      }
      var count = value[fieldName];
      if (!Number.isInteger(count) || count < 1) {
        fail("f3_matching_raw_fields 的计数必须是 >= 1 的整数；已整体停止（不回显取值）。");
      }
      counts.set(fieldName, count);
    }

    return counts;
  }

  /** 把字段名 → 计数 写回普通对象（字段名按码点排序；⛔ 无任何取值）。 */
  function writeFieldMatchCounts(counts) {
    return Object.fromEntries(
      Array.from(counts.keys())
        .sort()
        .map(function (fieldName) {
          return [fieldName, counts.get(fieldName)];
        })
    );
  }

  /**
   * 校验（并规整）一个分段 state。
   *
   * ⛔ 不信任外部传入的 state：键集合、版本、绑定元数据、页码唯一性、计数类型全部校验；
   * 任何不符合 → **fail closed**（⛔ 不回显被篡改的内容）。
   */
  function validateLayoutBFieldSourceState(state) {
    if (!state || typeof state !== "object" || Array.isArray(state)) {
      fail("分段 state 必须是对象；已整体停止（不回显取值）。");
    }

    var actualKeys = Object.keys(state).sort();
    var expectedKeys = LAYOUT_B_FIELD_SOURCE_STATE_KEYS.slice().sort();
    for (var keyIndex = 0; keyIndex < expectedKeys.length; keyIndex += 1) {
      if (actualKeys[keyIndex] !== expectedKeys[keyIndex]) {
        fail(
          "分段 state 的键集合与契约不一致（版本不符或被篡改）；" +
            "已整体停止（不回显键名）。"
        );
      }
    }

    if (state.version !== LAYOUT_B_FIELD_SOURCE_STATE_VERSION) {
      fail("分段 state 的 version 不受支持；已整体停止（不回显取值）。");
    }
    if (typeof state.semester !== "string" || state.semester.trim() === "") {
      fail("分段 state 的 semester 非法；已整体停止（不回显取值）。");
    }
    if (
      state.openingSchoolNumber !== null &&
      (typeof state.openingSchoolNumber !== "string" ||
        state.openingSchoolNumber.trim() === "")
    ) {
      fail("分段 state 的 openingSchoolNumber 非法；已整体停止（不回显取值）。");
    }
    if (state.page_size !== DEFAULT_PAGE_SIZE) {
      fail("分段 state 的 page_size 与已验证口径不一致；已整体停止（不回显取值）。");
    }

    var expectedTotal = requireFieldSourceCount(state.expected_total, "expected_total");
    if (expectedTotal < 1) {
      fail("分段 state 的 expected_total 必须 >= 1；已整体停止（不回显取值）。");
    }

    if (!Array.isArray(state.processed_pages)) {
      fail("分段 state 的 processed_pages 必须是数组；已整体停止（不回显取值）。");
    }

    var pages = [];
    var seenPages = {};
    for (var pageIndex = 0; pageIndex < state.processed_pages.length; pageIndex += 1) {
      var entry = state.processed_pages[pageIndex];
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        fail("processed_pages 的元素必须是对象；已整体停止（不回显取值）。");
      }

      var entryKeys = Object.keys(entry).sort();
      for (var entryKeyIndex = 0; entryKeyIndex < entryKeys.length; entryKeyIndex += 1) {
        if (entryKeys[entryKeyIndex] !== LAYOUT_B_FIELD_SOURCE_PAGE_KEYS[entryKeyIndex]) {
          fail(
            "processed_pages 的元素只允许 page_no / row_count；" +
              "已整体停止（不回显取值）。"
          );
        }
      }

      var pageNo = requireFieldSourceCount(entry.page_no, "page_no");
      if (pageNo < FIRST_PAGE_NO) {
        fail("processed_pages 的 page_no 必须 >= " + FIRST_PAGE_NO + "；已整体停止。");
      }
      if (seenPages[pageNo] === true) {
        fail("分段 state 出现重复页；已整体停止（不回显页码）。");
      }
      seenPages[pageNo] = true;

      pages.push({
        page_no: pageNo,
        row_count: requireFieldSourceCount(entry.row_count, "row_count")
      });
    }

    pages.sort(function (left, right) {
      return left.page_no - right.page_no;
    });

    return {
      semester: state.semester,
      openingSchoolNumber: state.openingSchoolNumber,
      expectedTotal: expectedTotal,
      pages: pages,
      seenPages: seenPages,
      counters: {
        candidateCount: requireFieldSourceCount(state.candidate_count, "candidate_count"),
        comparableTeachingName: requireFieldSourceCount(
          state.comparable_teaching_name_count,
          "comparable_teaching_name_count"
        ),
        f3EqualsTeachingName: requireFieldSourceCount(
          state.f3_equals_teaching_name_count,
          "f3_equals_teaching_name_count"
        ),
        f4EqualsTeachingName: requireFieldSourceCount(
          state.f4_equals_teaching_name_count,
          "f4_equals_teaching_name_count"
        ),
        f4Activity: requireFieldSourceCount(state.f4_activity_count, "f4_activity_count")
      },
      fieldMatches: readFieldMatchCounts(state.f3_matching_raw_fields)
    };
  }

  /** 组装一个 state（只有数值计数 + 字段名 → 计数 + 安全分页元数据）。 */
  function buildLayoutBFieldSourceState(binding, pages, counters, fieldMatches) {
    return {
      version: LAYOUT_B_FIELD_SOURCE_STATE_VERSION,
      semester: binding.semester,
      openingSchoolNumber: binding.openingSchoolNumber,
      page_size: binding.pageSize,
      expected_total: binding.expectedTotal,
      processed_pages: pages,
      candidate_count: counters.candidateCount,
      comparable_teaching_name_count: counters.comparableTeachingName,
      f3_equals_teaching_name_count: counters.f3EqualsTeachingName,
      f4_equals_teaching_name_count: counters.f4EqualsTeachingName,
      f4_activity_count: counters.f4Activity,
      f3_matching_raw_fields: writeFieldMatchCounts(fieldMatches)
    };
  }

  /**
   * 逐行累计**六个**输出（⛔ 完全不触碰 activity-membership）。
   *
   * ⚠️ 与完整诊断对同样六个字段使用**同一批**判别函数
   * （`isLayoutBCandidate()` / `isExcludedMatchFieldName()` / `isNonEmptyActivityToken()`），
   * 因此两者在同一份数据上必然给出相同的这六个值。
   */
  function accumulateLayoutBFieldSourceRows(rows, counters, fieldMatches) {
    for (var rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
      var row = rows[rowIndex];

      if (!row || typeof row !== "object" || Array.isArray(row)) {
        fail("分段诊断读到非对象记录；已整体停止（不回显取值）。");
      }

      var text = row[SCHEDULE_FIELD];
      if (typeof text !== "string" || text === "") {
        continue;
      }

      var segments = text.split(SEGMENT_SEPARATOR);
      if (segments.length > 1 && segments[segments.length - 1].trim() === "") {
        segments.pop();
      }

      var hasTeachingName = Object.prototype.hasOwnProperty.call(row, "teachingName");

      for (var segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 1) {
        var segment = segments[segmentIndex];
        if (segment.trim() === "" || !isLayoutBCandidate(segment)) {
          continue;
        }

        counters.candidateCount += 1;

        var fields = segment.split(FIELD_SEPARATOR);
        var thirdField = fields[2].trim();
        var fourthField = fields[3].trim();

        if (hasTeachingName) {
          counters.comparableTeachingName += 1;
          if (thirdField === row.teachingName) {
            counters.f3EqualsTeachingName += 1;
          }
          if (fourthField === row.teachingName) {
            counters.f4EqualsTeachingName += 1;
          }
        }

        if (isNonEmptyActivityToken(fields[3])) {
          counters.f4Activity += 1;
        }

        var rowFieldNames = Object.keys(row);
        for (
          var fieldIndex = 0;
          fieldIndex < rowFieldNames.length;
          fieldIndex += 1
        ) {
          var fieldName = rowFieldNames[fieldIndex];

          if (isExcludedMatchFieldName(fieldName)) {
            continue;
          }
          if (typeof row[fieldName] !== "string") {
            continue;
          }
          if (thirdField === row[fieldName]) {
            var matchedSoFar = fieldMatches.get(fieldName);
            fieldMatches.set(fieldName, matchedSoFar === undefined ? 1 : matchedSoFar + 1);
          }
        }
      }
    }
  }

  /**
   * 扫描 `startPage..endPage` 并返回**合并后的** state。
   *
   * ```text
   * part1 = await diagnoseLayoutBFieldSourcePart({ semester, openingSchoolNumber,
   *                                               startPage: 1, endPage: 5 })
   * // 用户把 part1 复制保存；重新登录后：
   * part2 = await diagnoseLayoutBFieldSourcePart({ semester, openingSchoolNumber,
   *                                               startPage: 6, endPage: 6,
   *                                               previousState: part1 })
   * final = finalizeLayoutBFieldSource(part2)
   * ```
   *
   * ⚠️ `startPage > 1` **允许**（无序合并也被支持）：绑定与覆盖率在 finalize 校验，
   * 因此 `6 + 1..5` 与 `4..6 + 1..3` 同样成立。
   * ⛔ 重复 / 重叠页、semester / shard / page_size / expected_total 不一致 → fail closed。
   */
  async function diagnoseLayoutBFieldSourcePart(options) {
    requireAllowedHost();

    var opts = options || {};

    var optionNames = Object.keys(opts);
    var unexpected = optionNames.filter(function (name) {
      return LAYOUT_B_FIELD_SOURCE_ALLOWED_OPTIONS.indexOf(name) === -1;
    });
    if (unexpected.length > 0) {
      fail(
        "分段诊断只接受 " + LAYOUT_B_FIELD_SOURCE_ALLOWED_OPTIONS.join(" / ") +
          "（收到 " + unexpected.length + " 个其它参数）。已停止；参数名不予回显。"
      );
    }

    var semester = opts.semester;
    if (typeof semester !== "string" || semester.trim() === "") {
      fail('分段诊断必须显式提供非空 semester（例如 "2026-1"）。');
    }
    semester = semester.trim();

    var campus = opts.openingSchoolNumber;
    if (campus !== undefined && (typeof campus !== "string" || campus.trim() === "")) {
      fail("openingSchoolNumber 必须是非空字符串（或省略）。");
    }
    if (campus === undefined) {
      campus = null;
    }

    var startPage = requireFieldSourceCount(opts.startPage, "startPage");
    var endPage = requireFieldSourceCount(opts.endPage, "endPage");
    if (startPage < FIRST_PAGE_NO || endPage < startPage) {
      fail(
        "startPage / endPage 必须是 " + FIRST_PAGE_NO + " <= startPage <= endPage 的整数；" +
          "已整体停止（不回显取值）。"
      );
    }
    if (endPage > ABSOLUTE_MAX_PAGES) {
      fail("endPage 不得超过 " + ABSOLUTE_MAX_PAGES + "；已整体停止（不回显取值）。");
    }

    // ⛔ pageSize / delayMs 恒为已验证默认值：诊断不接受调用方覆盖。
    var pageSize = DEFAULT_PAGE_SIZE;

    var pages = [];
    var seenPages = {};
    var counters = {
      candidateCount: 0,
      comparableTeachingName: 0,
      f3EqualsTeachingName: 0,
      f4EqualsTeachingName: 0,
      f4Activity: 0
    };
    var fieldMatches = new Map();
    var expectedTotal = null;
    var accumulatedRows = 0;

    if (opts.previousState !== undefined) {
      var previous = validateLayoutBFieldSourceState(opts.previousState);

      if (previous.semester !== semester) {
        fail("previousState 的 semester 与本次 semester 不一致；已整体停止（不回显取值）。");
      }
      if (previous.openingSchoolNumber !== campus) {
        fail(
          "previousState 的 shard 与本次 openingSchoolNumber 不一致；" +
            "已整体停止（不回显取值）。"
        );
      }

      pages = previous.pages;
      seenPages = previous.seenPages;
      counters = previous.counters;
      fieldMatches = previous.fieldMatches;
      expectedTotal = previous.expectedTotal;
      for (var previousIndex = 0; previousIndex < pages.length; previousIndex += 1) {
        accumulatedRows += pages[previousIndex].row_count;
      }
    }

    if (endPage - startPage + 1 > DEFAULT_MAX_PAGES) {
      var confirmed = window.confirm(
        "即将执行**分段式 f3 字段来源诊断**（只取聚合计数，不产出任何数据、不落盘）。\n" +
          "本次最多请求 " + (endPage - startPage + 1) + " 页；请求间隔至少 " +
          DEFAULT_DELAY_MS / 1000 + " 秒（含全局批次冷却）。\n" +
          "是否继续？"
      );
      if (!confirmed) {
        fail("用户取消了分段诊断：本次不产生任何 state（不返回伪造计数）。");
      }
    }

    var pacer = createRequestPacer(DEFAULT_DELAY_MS);

    for (var pageNo = startPage; pageNo <= endPage; pageNo += 1) {
      if (seenPages[pageNo] === true) {
        fail(
          "第 " + pageNo + " 页在 previousState 中已处理过（重复 / 重叠页）；" +
            "已整体停止（⛔ 不静默覆盖）。"
        );
      }

      var data = await requestPage(semester, pageNo, pageSize, campus, pacer);

      if (expectedTotal === null) {
        expectedTotal = data.total;
      } else if (data.total !== expectedTotal) {
        fail(
          "第 " + pageNo + " 页的 data.total 与已记录的 expected_total 不一致：" +
            "数据集合发生变化。已整体停止（不回显任何取值，⛔ 不合并）。"
        );
      }

      accumulateLayoutBFieldSourceRows(data.rows, counters, fieldMatches);

      pages.push({ page_no: pageNo, row_count: data.rows.length });
      seenPages[pageNo] = true;
      accumulatedRows += data.rows.length;

      if (accumulatedRows >= expectedTotal) {
        break;
      }
    }

    pages.sort(function (left, right) {
      return left.page_no - right.page_no;
    });

    return buildLayoutBFieldSourceState(
      {
        semester: semester,
        openingSchoolNumber: campus,
        pageSize: pageSize,
        expectedTotal: expectedTotal
      },
      pages,
      counters,
      fieldMatches
    );
  }

  /**
   * 校验覆盖完整性并返回**恰好六个**最终计数。
   *
   * ⛔ 页码必须恰好覆盖 `1..N`（无洞）、⛔ `Σ row_count >= expected_total`（取满）；
   * 否则 **fail closed**（⛔ 不返回近似结果）。
   * ⛔ 返回值**不含** activity-membership 计数（不存在、也不用 0 / null 占位）。
   */
  function finalizeLayoutBFieldSource(state) {
    var parsed = validateLayoutBFieldSourceState(state);

    var maxPage = 0;
    var totalRows = 0;
    for (var index = 0; index < parsed.pages.length; index += 1) {
      if (parsed.pages[index].page_no > maxPage) {
        maxPage = parsed.pages[index].page_no;
      }
      totalRows += parsed.pages[index].row_count;
    }

    for (var pageNo = FIRST_PAGE_NO; pageNo <= maxPage; pageNo += 1) {
      if (parsed.seenPages[pageNo] !== true) {
        fail(
          "分段 state 缺少第 " + pageNo + " 页（覆盖不连续）；" +
            "已整体停止（⛔ 不返回近似结果）。"
        );
      }
    }

    if (totalRows < parsed.expectedTotal) {
      fail(
        "分段 state 只覆盖 " + totalRows + " / " + parsed.expectedTotal + " 行；" +
          "已整体停止（⛔ 不返回近似结果）。"
      );
    }

    // ⚠️ 页数与 expected_total 必须自洽（防止把 expected_total 改小来伪造"已完成"）。
    var requiredPages = Math.ceil(parsed.expectedTotal / DEFAULT_PAGE_SIZE);
    if (maxPage !== requiredPages) {
      fail(
        "分段 state 的页数与 expected_total 不自洽；" +
          "已整体停止（⛔ 不返回近似结果）。"
      );
    }

    return {
      candidate_count: parsed.counters.candidateCount,
      comparable_teaching_name_count: parsed.counters.comparableTeachingName,
      f3_equals_teaching_name_count: parsed.counters.f3EqualsTeachingName,
      f4_equals_teaching_name_count: parsed.counters.f4EqualsTeachingName,
      f4_activity_count: parsed.counters.f4Activity,
      f3_matching_raw_fields: writeFieldMatchCounts(parsed.fieldMatches)
    };
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
    // ⛔ **不传第 4 个参数** = baseline（全量）形态：请求体只有 `yearTerm`，不做任何分片。
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
    collectSharded: collectSharded,
    diagnoseSchedulePresence: diagnoseSchedulePresence,
    summarizeSchedulePresence: summarizeSchedulePresence,
    diagnoseMissingScheduleCorrelation: diagnoseMissingScheduleCorrelation,
    diagnoseLayoutBCandidates: diagnoseLayoutBCandidates,
    diagnoseLayoutBFieldSourcePart: diagnoseLayoutBFieldSourcePart,
    finalizeLayoutBFieldSource: finalizeLayoutBFieldSource,
    toJson: toJson,
    shardBundle: shardBundle,
    toShardJson: toShardJson,
    toDiagnosticsJson: toDiagnosticsJson,
    APPROVED_SHARDS: APPROVED_SHARDS,
    SHARD_PAGE_SIZE: SHARD_PAGE_SIZE,
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
    MAX_REQUESTS_PER_BATCH: MAX_REQUESTS_PER_BATCH,
    BATCH_COOLDOWN_MS: BATCH_COOLDOWN_MS,
    REDACTED_TEACHER: REDACTED_TEACHER
  };
})();
