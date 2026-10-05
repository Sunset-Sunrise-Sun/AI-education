/**
 * `tools/sysu_course_offering_collector.js` 的**可执行**脱敏行为测试。
 *
 * 为什么需要它：`backend/tests/test_sysu_collector_guard.py` 只做**源码级静态**检查
 * （它明确写着"不执行 JS"），因此**无法**证明"5 字段 location 不会被当成 teacher"
 * 这类**运行时**语义。本文件用 Node 内建 `node:test` + `node:vm` 真正执行采集器，
 * 用一个假的 `fetch` 喂入人工虚构的一页数据，再检查产出的 Capture Bundle。
 *
 * ⛔ 全程零网络：`fetch` 被替换为本地假实现，不会发出任何请求。
 * ⛔ 数据最小化：所有 row / 教师 / 校区 / 教室均为**人工虚构**。
 *
 * 运行：`node --test tools/sysu_course_offering_collector.test.mjs`
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const COLLECTOR_PATH = join(HERE, "sysu_course_offering_collector.js");
const SOURCE = readFileSync(COLLECTOR_PATH, "utf-8");

const SEMESTER = "2026-1";
const TEACHER = "示例教师A";
const ACTIVITY = "示例环节";
const CAMPUS = "示例校区";
const CLASSROOM = "示例教学楼-2108";
const LOCATION = `${CAMPUS}-${CLASSROOM}`;

/** 一条最小的合法 raw row（人工虚构）。 */
function rawRow(teachingTimePlaceStr) {
  const row = {
    courseNum: "00000000",
    courseName: "示例课程",
    classNumber: "SYN-01",
    yearTerm: SEMESTER,
    score: "3",
    limitNumber: 90,
    selectedNumber: 75,
  };
  if (teachingTimePlaceStr !== undefined) {
    row.teachingTimePlaceStr = teachingTimePlaceStr;
  }
  return row;
}

/**
 * 在隔离的 VM 里加载采集器，并把 `fetch` 换成返回给定 rows 的假实现。
 * 返回 `{ collector, calls }`。
 */
function loadCollector(rows) {
  const calls = [];
  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    Date,
    JSON,
    Promise,
    Error,
    Number,
    Array,
    String,
    Object,
    Math,
    // 假 fetch：不访问网络，直接回一页数据。
    fetch: async (url, init) => {
      calls.push({ url, init });
      return {
        status: 200,
        ok: true,
        headers: { get: () => "application/json;charset=UTF-8" },
        json: async () => ({ code: 200, data: { total: rows.length, rows } }),
      };
    },
  };
  sandbox.window = {
    location: { hostname: "jwxt.sysu.edu.cn" },
    confirm: () => true,
    XuehangSysuCollector: undefined,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox, { filename: "sysu_course_offering_collector.js" });
  return { collector: sandbox.window.XuehangSysuCollector, calls };
}

/** 跑一页采集并返回脱敏后的 teachingTimePlaceStr。 */
async function collectSingle(text) {
  const { collector, calls } = loadCollector([rawRow(text)]);
  const result = await collector.collect({ semester: SEMESTER });
  assert.equal(calls.length, 1, "应当只请求 1 页");
  const page = result.bundle.pages[0];
  return page.response.data.rows[0].teachingTimePlaceStr;
}

// ---------------------------------------------------------------------------
// 4 字段：weeks / weekday / sections / activity（无 teacher）
// ---------------------------------------------------------------------------

test("4 字段：不失败，且不插入 REDACTED", async () => {
  const text = `1-8周/星期五/第5-6节/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.equal(out, text, "4 字段必须原样保留（无 teacher 可脱敏）");
  assert.ok(!out.includes("REDACTED"), "⛔ 4 字段不得插入 REDACTED");
});

// ---------------------------------------------------------------------------
// 5 字段判别（收紧后：严格三态）
// ---------------------------------------------------------------------------

test("5 字段无 '-':明确是 teacher → fields[3] = REDACTED", async () => {
  const text = `1-8周/星期五/第5-6节/${TEACHER}/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.equal(out, `1-8周/星期五/第5-6节/REDACTED/${ACTIVITY}`);
  assert.ok(!out.includes(TEACHER), "⛔ 真实 teacher 不得出现在产物中");
});

test("5 字段 >=3 个非空 '-' 分段:明确是 location → 原样保留", async () => {
  const text = `1-8周/星期五/第5-6节/${LOCATION}/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.equal(out, text, "明确 location 必须原样保留");
  assert.ok(!out.includes("REDACTED"), "⛔ 无 teacher 时不得插入 REDACTED");
});

for (const [label, ambiguous] of [
  ["两段 A-B", "示例-教师A"],
  ["园区为空", "-示例教师A"],
  ["教室为空", "示例教师A-"],
  ["两侧为空", "  -  "],
  ["三段但末段为空", "示例校区-示例教学楼-"],
]) {
  test(`5 字段二义形态（${label}）：fail closed，不产出 bundle`, async () => {
    const { collector } = loadCollector([
      rawRow(`1-8周/星期五/第5-6节/${ambiguous}/${ACTIVITY}`),
    ]);

    await assert.rejects(
      () => collector.collect({ semester: SEMESTER }),
      (error) => {
        assert.ok(error instanceof Error);
        assert.ok(
          error.message.includes("不猜语义"),
          `错误信息应说明不猜语义，实际：${error.message}`,
        );
        // ⛔ 不回显该字段取值
        assert.ok(
          !error.message.includes(ambiguous),
          "⛔ 二义字段取值不得出现在错误信息中",
        );
        return true;
      },
    );
  });
}

// ---------------------------------------------------------------------------
// 回归：两段 token 不得再被当成 location（旧缺陷方向）
// ---------------------------------------------------------------------------

test("回归：两段 token 不得再被静默当成 location", async () => {
  const { collector } = loadCollector([
    rawRow(`1-8周/星期五/第5-6节/示例-教师A/${ACTIVITY}`),
  ]);

  await assert.rejects(
    () => collector.collect({ semester: SEMESTER }),
    /不猜语义/,
  );
});

// ---------------------------------------------------------------------------
// 6 字段：本轮**未**收紧（语义已由字段数确定），仍按通用 location grammar
// ---------------------------------------------------------------------------

test("6 字段 location/teacher/activity：teacher 被替换为 REDACTED，location 保留", async () => {
  const text = `1-8周/星期五/第5-6节/${LOCATION}/${TEACHER}/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.equal(out, `1-8周/星期五/第5-6节/${LOCATION}/REDACTED/${ACTIVITY}`);
  assert.ok(out.includes(LOCATION), "location 必须保留");
  assert.ok(!out.includes(TEACHER), "⛔ 真实 teacher 不得出现在产物中");
});

// ---------------------------------------------------------------------------
// 混合：一条真实证据形状的串（5 字段 / 4 字段 / 5 字段）
// ---------------------------------------------------------------------------

test("混合 segment：逐个 segment 正确脱敏", async () => {
  const text = [
    `1-8周/星期五/第5-6节/${LOCATION}/${ACTIVITY}`,
    `2-9周/星期三/第1-2节/${ACTIVITY}`,
    `3-10周/星期一/第3-4节/${LOCATION}/${ACTIVITY}`,
  ].join(",");

  const out = await collectSingle(text);

  assert.equal(out, text, "全部无 teacher → 整串原样保留");
  assert.ok(!out.includes("REDACTED"));
});

// ---------------------------------------------------------------------------
// 2 字段：non-concrete（`<weeks token><qualifier>` / activity）
// ---------------------------------------------------------------------------

test("2 字段 non-concrete：允许通过，且不做 teacher 脱敏", async () => {
  const text = "12-19周校外/实验实践环节";

  const out = await collectSingle(text);

  assert.equal(out, text, "non-concrete 段必须原样保留");
  assert.ok(!out.includes("REDACTED"), "⛔ 无 teacher 时不得插入 REDACTED");
});

for (const [label, text] of [
  ["未知 qualifier", "12-19周未知词/实验实践环节"],
  ["尚无证据的 qualifier", "12-19周线上/实验实践环节"],
  ["缺 weeks token", "校外/实验实践环节"],
  ["随机 2 字段", "foo/bar"],
]) {
  test(`2 字段但非已确认 grammar（${label}）：fail closed`, async () => {
    const { collector } = loadCollector([rawRow(text)]);

    await assert.rejects(
      () => collector.collect({ semester: SEMESTER }),
      (error) => {
        assert.ok(error instanceof Error);
        assert.ok(
          error.message.includes("plain") && error.message.includes("qualified"),
          `错误信息应说明已确认的 plain / qualified 形态，实际：${error.message}`,
        );
        // ⛔ 不回显该字段取值
        assert.ok(!error.message.includes("未知词"), "⛔ 不得回显取值");
        return true;
      },
    );
  });
}

test("混合：concrete + non-concrete 段同时存在时都能通过", async () => {
  const text = [
    `1-8周/星期五/第5-6节/${TEACHER}/${ACTIVITY}`,
    "12-19周校外/实验实践环节",
    `3-10周/星期一/第3-4节/${LOCATION}/${ACTIVITY}`,
  ].join(",");

  const out = await collectSingle(text);

  assert.equal(
    out,
    [
      `1-8周/星期五/第5-6节/REDACTED/${ACTIVITY}`,
      "12-19周校外/实验实践环节",
      `3-10周/星期一/第3-4节/${LOCATION}/${ACTIVITY}`,
    ].join(","),
    "各自按自己的规则处理：teacher 段脱敏、non-concrete 原样保留",
  );
  assert.ok(!out.includes(TEACHER), "⛔ 真实 teacher 不得出现在产物中");
});

// ---------------------------------------------------------------------------
// 3 字段：non-concrete 带 teacher（`weeks` / `teacher` / `activity`）
// ---------------------------------------------------------------------------

test("3 字段 weeks/teacher/activity：teacher 替换为 REDACTED，weeks 与 activity 保留", async () => {
  const text = "1-17周/示例教师/实验实践环节";

  const out = await collectSingle(text);

  assert.equal(out, "1-17周/REDACTED/实验实践环节");
  assert.ok(!out.includes("示例教师"), "⛔ 真实 teacher 不得出现在产物中");
  assert.ok(out.startsWith("1-17周/"), "weeks 必须原样保留");
  assert.ok(out.endsWith("/实验实践环节"), "activity 必须原样保留");
});

for (const [label, text] of [
  ["teacher 为空", "1-17周//实验实践环节"],
  ["teacher 全空白", "1-17周/   /实验实践环节"],
  ["weeks token 非法", "abc周/示例教师/实验实践环节"],
  ["weeks 区间非法", "5-1周/示例教师/实验实践环节"],
  ["缺 activity", "1-17周/示例教师/"],
  ["缺 weeks", "示例教师/实验实践环节/多余"],
]) {
  test(`3 字段非法（${label}）：fail closed`, async () => {
    const { collector } = loadCollector([rawRow(text)]);

    await assert.rejects(
      () => collector.collect({ semester: SEMESTER }),
      (error) => {
        assert.ok(error instanceof Error);
        // ⛔ 不回显 teacher 取值
        assert.ok(!error.message.includes("示例教师"), "⛔ 不得回显 teacher 取值");
        return true;
      },
    );
  });
}

test("混合：concrete + 2 字段 + 3 字段 non-concrete 各自正确处理", async () => {
  const text = [
    `1-8周/星期五/第5-6节/${TEACHER}/${ACTIVITY}`,
    "12-19周校外/实验实践环节",
    "1-17周/示例教师/实验实践环节",
  ].join(",");

  const out = await collectSingle(text);

  assert.equal(
    out,
    [
      `1-8周/星期五/第5-6节/REDACTED/${ACTIVITY}`,
      "12-19周校外/实验实践环节",
      "1-17周/REDACTED/实验实践环节",
    ].join(","),
  );
  assert.ok(!out.includes(TEACHER), "⛔ 真实 teacher 不得出现在产物中");
  assert.ok(!out.includes("示例教师"), "⛔ 3 字段的 teacher 也必须被脱敏");
});

// ---------------------------------------------------------------------------
// 2 字段 plain：`<weeks token>` / activity（无 teacher、无 qualifier）
// ---------------------------------------------------------------------------

test("2 字段 plain：原样通过，且不插入 REDACTED", async () => {
  const text = "1-17周/实验实践环节";

  const out = await collectSingle(text);

  assert.equal(out, text, "plain non-concrete 必须原样保留");
  assert.ok(!out.includes("REDACTED"), "⛔ 没有 teacher 时不得插入 REDACTED");
});

for (const [label, text] of [
  ["weeks token 非法", "abc周/实验实践环节"],
  ["未知 qualifier", "1-17周未知词/实验实践环节"],
  ["activity 为空", "1-17周/"],
  ["activity 全空白", "1-17周/   "],
  ["既非 weeks 也非 qualifier", "随便写的东西/实验实践环节"],
]) {
  test(`2 字段非法（${label}）：fail closed`, async () => {
    const { collector } = loadCollector([rawRow(text)]);

    await assert.rejects(() => collector.collect({ semester: SEMESTER }), Error);
  });
}

test("混合全部五种形态：各自正确，且没有多余脱敏", async () => {
  const text = [
    `1-8周/星期五/第5-6节/${TEACHER}/${ACTIVITY}`,
    "1-17周/实验实践环节",
    "12-19周校外/实验实践环节",
    "1-17周/示例教师/实验实践环节",
    "16-16周校内(户外)/示例教师/实验实践环节",
  ].join(",");

  const out = await collectSingle(text);

  assert.equal(
    out,
    [
      `1-8周/星期五/第5-6节/REDACTED/${ACTIVITY}`,
      "1-17周/实验实践环节",
      "12-19周校外/实验实践环节",
      "1-17周/REDACTED/实验实践环节",
      "16-16周校内(户外)/REDACTED/实验实践环节",
    ].join(","),
  );
  assert.ok(!out.includes(TEACHER), "⛔ 真实 teacher 不得出现在产物中");
  assert.ok(!out.includes("示例教师"), "⛔ 3 字段的 teacher 也必须被脱敏");
});

// ---------------------------------------------------------------------------
// 3 字段 qualified：`<weeks><qualifier>` / teacher / activity
// ---------------------------------------------------------------------------

const QUALIFIER_OUTDOOR = "校内(户外)";

test("3 字段 qualified：teacher 脱敏，qualifier / weeks / activity 全保留", async () => {
  const text = "16-16周校内(户外)/示例教师/实验实践环节";

  const out = await collectSingle(text);

  assert.equal(out, "16-16周校内(户外)/REDACTED/实验实践环节");
  assert.ok(out.includes("16-16周"), "weeks 必须保留");
  assert.ok(out.includes(QUALIFIER_OUTDOOR), "qualifier 必须保留");
  assert.ok(out.endsWith("/实验实践环节"), "activity 必须保留");
  assert.ok(!out.includes("示例教师"), "⛔ 真实 teacher 不得出现在产物中");
});

test("⛔ 不能因为第一个字段带 qualifier 就跳过 teacher 脱敏", async () => {
  const text = "16-16周校内(户外)/示例教师/实验实践环节";

  const out = await collectSingle(text);

  // 中间字段必须是 REDACTED，而不是原样的教师姓名
  assert.equal(out.split("/")[1], "REDACTED");
});

for (const [label, text] of [
  ["未知 qualifier", "16-16周未知文本/示例教师/实验实践环节"],
  ["尚无证据的 qualifier", "16-16周线上/示例教师/实验实践环节"],
  ["尚无证据的 qualifier 2", "16-16周医院/示例教师/实验实践环节"],
  ["qualified teacher 为空", "16-16周校内(户外)//实验实践环节"],
  ["qualified activity 为空", "16-16周校内(户外)/示例教师/"],
]) {
  test(`3 字段 qualified 非法（${label}）：fail closed`, async () => {
    const { collector } = loadCollector([rawRow(text)]);

    await assert.rejects(
      () => collector.collect({ semester: SEMESTER }),
      (error) => {
        assert.ok(error instanceof Error);
        // ⛔ 不回显 teacher 取值
        assert.ok(!error.message.includes("示例教师"), "⛔ 不得回显 teacher 取值");
        return true;
      },
    );
  });
}

test("混合：6 字段 concrete + plain 3 字段 + qualified 3 字段", async () => {
  const text = [
    `1-8周/星期五/第5-6节/${LOCATION}/${TEACHER}/${ACTIVITY}`,
    "1-17周/示例教师/实验实践环节",
    "16-16周校内(户外)/示例教师/实验实践环节",
  ].join(",");

  const out = await collectSingle(text);

  assert.equal(
    out,
    [
      `1-8周/星期五/第5-6节/${LOCATION}/REDACTED/${ACTIVITY}`,
      "1-17周/REDACTED/实验实践环节",
      "16-16周校内(户外)/REDACTED/实验实践环节",
    ].join(","),
  );
  assert.ok(!out.includes(TEACHER), "⛔ 真实 teacher 不得出现在产物中");
  assert.ok(!out.includes("示例教师"), "⛔ 3 字段的 teacher 也必须被脱敏");
});

// ---------------------------------------------------------------------------
// 未知字段数：继续 fail closed
// ---------------------------------------------------------------------------

for (const [label, text] of [
  ["7 字段", `1-8周/星期五/第5-6节/${LOCATION}/${TEACHER}/${ACTIVITY}/多出来`],
  ["8 字段", `1-8周/星期五/第5-6节/${LOCATION}/${TEACHER}/${ACTIVITY}/多出来/还更多`],
]) {
  test(`${label}：继续 fail closed（不产出 bundle）`, async () => {
    const { collector } = loadCollector([rawRow(text)]);

    await assert.rejects(
      () => collector.collect({ semester: SEMESTER }),
      (error) => {
        assert.ok(error instanceof Error);
        assert.ok(
          error.message.includes("字段数"),
          `错误信息应说明字段数问题，实际：${error.message}`,
        );
        return true;
      },
    );
  });
}

// ---------------------------------------------------------------------------
// 空 teacher：仍不得被静默修复
// ---------------------------------------------------------------------------

test("5 字段 teacher 为空：fail closed，不写入占位符掩盖", async () => {
  const { collector } = loadCollector([rawRow(`1-8周/星期五/第5-6节/   /${ACTIVITY}`)]);

  await assert.rejects(
    () => collector.collect({ semester: SEMESTER }),
    (error) => {
      assert.ok(error.message.includes("teacher"), `实际：${error.message}`);
      return true;
    },
  );
});

test("6 字段 teacher 为空：fail closed", async () => {
  const { collector } = loadCollector([
    rawRow(`1-8周/星期五/第5-6节/${LOCATION}/   /${ACTIVITY}`),
  ]);

  await assert.rejects(() => collector.collect({ semester: SEMESTER }), /teacher/);
});

// ---------------------------------------------------------------------------
// teacher 不存在的字段：仍按 DG-07B 处理（attribute 缺失 → 不建 key）
// ---------------------------------------------------------------------------

test("teachingTimePlaceStr 属性缺失：仍不创建该 key（DG-07B 不变）", async () => {
  const { collector } = loadCollector([rawRow(undefined)]);

  const result = await collector.collect({ semester: SEMESTER });
  const minimized = result.bundle.pages[0].response.data.rows[0];

  assert.ok(
    !Object.prototype.hasOwnProperty.call(minimized, "teachingTimePlaceStr"),
    "属性不存在时不得创建该 key",
  );
});

// ===========================================================================
// 五校区 shard 编排（baseline_before → 五校区串行 → baseline_after）
//
// ⛔ 全程零网络：`fetch` 被替换为**假的 same-origin 实现**，按请求体里的
//    `openingSchoolNumber` / `pageNo` 返回**人工虚构**的页。
// ⛔ 所有 row / 课程 / 教师 / 教室均为虚构；真实分片数字（1071/405/…）不进来。
// ⛔ `setTimeout` 也被替换：`sleep()` 立即 resolve，但**仍然记录请求的毫秒数**，
//    因此"串行 + 最小间隔"是被断言的，而不是被跳过的。
// ===========================================================================

/** 已批准的五个 shard（与源码常量同值；这里只用于断言"请求真的按这个顺序发"）。 */
const SHARDS = [
  { shard_id: "东校园", openingSchoolNumber: "5063559" },
  { shard_id: "北校园", openingSchoolNumber: "5062202" },
  { shard_id: "南校园", openingSchoolNumber: "5062201" },
  { shard_id: "深圳校区", openingSchoolNumber: "333291143" },
  { shard_id: "珠海校区", openingSchoolNumber: "5062203" },
];

/** 人工虚构的每个校区行数（合计 13）；全部 <= 200 ⇒ 每个 shard 只需 1 页。 */
const SHARD_ROW_COUNTS = [3, 1, 4, 2, 3];
const TOTAL_ROWS = SHARD_ROW_COUNTS.reduce((sum, count) => sum + count, 0);

const BUNDLE_KEYS = ["format", "semester", "first_page_no", "page_size", "pages"];

function fakeResponse(payload) {
  return {
    status: 200,
    ok: true,
    headers: { get: () => "application/json;charset=UTF-8" },
    json: async () => payload,
  };
}

/** 某个 shard 的若干条人工虚构 row（classNumber 唯一，便于断言不丢行）。 */
function shardRows(prefix, count) {
  return Array.from({ length: count }, (_, index) =>
    Object.assign(rawRow(`1-8周/星期五/第5-6节/${LOCATION}`), {
      classNumber: `${prefix}-${String(index + 1).padStart(4, "0")}`,
    }),
  );
}

/** 五个校区的默认行集合（按已批准顺序）。 */
function defaultCampuses(rowCounts = SHARD_ROW_COUNTS) {
  return SHARDS.map((shard, index) => ({
    openingSchoolNumber: shard.openingSchoolNumber,
    rows: shardRows(`SYN${index + 1}`, rowCounts[index]),
  }));
}

/**
 * 在隔离 VM 里加载采集器，注入：
 *   - 假 `fetch`：按 `openingSchoolNumber` / `pageNo` 返回人造页
 *     （可用 `http600: { campus, pageNo }` 复现真实证据的 HTTP 600）；
 *   - 假 `setTimeout`：立即 resolve，但记录请求的延迟（用于断言串行间隔）；
 *   - 可配置的 `window.confirm`。
 */
function loadShardedCollector(options = {}) {
  const campuses = options.campuses || defaultCampuses();
  const baselineTotals = options.baselineTotals || [TOTAL_ROWS, TOTAL_ROWS];
  const baselineRows = options.baselineRows || null;
  const http600 = options.http600;
  const pageRows =
    options.pageRows ||
    ((rows, pageNo, pageSize) => rows.slice((pageNo - 1) * pageSize, pageNo * pageSize));

  const calls = [];
  const timers = [];
  const confirms = [];
  const byNumber = new Map(campuses.map((campus) => [campus.openingSchoolNumber, campus.rows]));
  let baselineReads = 0;

  const sandbox = {
    console,
    Date,
    JSON,
    Promise,
    Error,
    Number,
    Array,
    String,
    Object,
    Math,
    clearTimeout: () => {},
    setTimeout: (callback, ms) => {
      timers.push(ms);
      queueMicrotask(callback);
      return timers.length;
    },
    fetch: async (url, init) => {
      const body = JSON.parse(init.body);
      const campus = body.param.openingSchoolNumber;

      calls.push({
        campus,
        pageNo: body.pageNo,
        pageSize: body.pageSize,
        paramKeys: Object.keys(body.param),
      });

      if (campus === undefined) {
        // `baselineRows`：让 `collect()`（全量入口）也能跑多页，用于验证它也走同一个 pacer。
        if (baselineRows) {
          const start = (body.pageNo - 1) * body.pageSize;
          return fakeResponse({
            code: 200,
            data: {
              total: baselineRows.length,
              rows: baselineRows.slice(start, start + body.pageSize),
            },
          });
        }

        const total = baselineTotals[Math.min(baselineReads, baselineTotals.length - 1)];
        baselineReads += 1;
        // baseline 只读 total：这里故意给空 rows，证明探针不看 rows。
        return fakeResponse({ code: 200, data: { total, rows: [] } });
      }

      // 真实证据形态：短间隔连续请求稳定返回 HTTP 600 / code=50015000 / 系统异常
      if (http600 && campus === http600.campus && body.pageNo === http600.pageNo) {
        return {
          status: 600,
          ok: false,
          headers: { get: () => "application/json;charset=UTF-8" },
          json: async () => ({ code: 50015000, message: "系统异常" }),
        };
      }

      const rows = byNumber.get(campus);
      assert.ok(rows !== undefined, `假 fetch 收到未批准的校区号：${campus}`);

      return fakeResponse({
        code: 200,
        data: { total: rows.length, rows: pageRows(rows, body.pageNo, body.pageSize) },
      });
    },
  };

  sandbox.window = {
    location: { hostname: "jwxt.sysu.edu.cn" },
    confirm: (message) => {
      confirms.push(message);
      return options.confirmResult === undefined ? true : options.confirmResult;
    },
    XuehangSysuCollector: undefined,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox, { filename: "sysu_course_offering_collector.js" });

  return { collector: sandbox.window.XuehangSysuCollector, calls, timers, confirms };
}

/** 捕获 `collectSharded()` 抛出的错误（整体失败时用于检查 message / diagnostics）。 */
async function captureRejection(run) {
  try {
    await run();
  } catch (error) {
    return error;
  }
  throw new Error("本应整体失败，但调用成功了");
}

/**
 * 全局 batch pacing 不变量：**整个 run 的每一对相邻请求**之间恰好有一次等待，
 * 且等待时长严格符合策略：
 *
 * ```text
 * 第 1 个请求            → 不等待
 * 其它请求（前一批未满）  → delayMs
 * 前一批已满 5 个成功请求 → max(BATCH_COOLDOWN_MS, delayMs)
 * ```
 *
 * ⚠️ 这是一条**全序列**断言：任何新增的请求路径若没有配套等待、
 * 或在 baseline / collectPages / shard 循环里另起一套计数，
 * 都会在这里立刻变红。
 */
function assertBatchPacingInvariant(
  calls,
  timers,
  { delayMs = 30000, batch = 5, cooldown = 300000 } = {},
) {
  assert.equal(
    timers.length,
    Math.max(calls.length - 1, 0),
    "每一对相邻请求之间必须恰好有一次等待（由全局 pacer 统一保证）",
  );

  for (let index = 0; index < timers.length; index += 1) {
    const requestIndex = index + 2; // 该等待之后要发的请求序号（1-based）
    const isBatchBoundary = (requestIndex - 1) % batch === 0;
    const expected = isBatchBoundary ? Math.max(cooldown, delayMs) : delayMs;

    assert.equal(
      timers[index],
      expected,
      `request ${requestIndex - 1} → request ${requestIndex} 的等待应为 ${expected}ms`,
    );
    assert.ok(
      timers[index] >= delayMs,
      `任何相邻请求间隔都必须 >= ${delayMs}ms，实际 ${timers[index]}`,
    );
  }
}

// ---------------------------------------------------------------------------
// 1. 正常链路
// ---------------------------------------------------------------------------

test("五校区：baseline → 5 shard → baseline，产出 5 个裸 bundle + 1 个 diagnostics", async () => {
  const { collector, calls, timers } = loadShardedCollector();

  const result = await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });

  // 请求顺序：baseline → 五个已批准校区（固定顺序）→ baseline
  assert.deepEqual(
    calls.map((call) => call.campus),
    [undefined, ...SHARDS.map((shard) => shard.openingSchoolNumber), undefined],
  );
  assert.equal(calls.length, 7);
  assert.equal(result.requests, 7);
  assert.equal(result.cancelled, false);

  // baseline 请求只有 yearTerm；shard 请求带已批准校区号
  assert.deepEqual(calls[0].paramKeys, ["yearTerm"]);
  assert.deepEqual(calls[6].paramKeys, ["yearTerm"]);
  for (const call of calls.slice(1, 6)) {
    assert.deepEqual(call.paramKeys, ["yearTerm", "openingSchoolNumber"]);
  }

  // 每个 shard 都从 pageNo=1 开始、pageSize 固定 200
  for (const call of calls.slice(1, 6)) {
    assert.equal(call.pageNo, 1);
    assert.equal(call.pageSize, 200);
  }

  // 五个独立裸 bundle（⛔ 顶层恰好 5 个键，⛔ 不含 diagnostics）
  assert.equal(result.shards.length, 5);
  result.shards.forEach((shard, index) => {
    assert.equal(shard.shard_id, SHARDS[index].shard_id);
  });

  let seen = 0;
  for (const shard of result.shards) {
    // ⚠️ `Object.keys` 返回的是 VM realm 的数组，不能和宿主数组做 deepStrictEqual
    assert.equal(
      Object.keys(shard.bundle).sort().join(","),
      [...BUNDLE_KEYS].sort().join(","),
    );
    assert.equal(shard.bundle.format, "sysu-opening-courses-capture-v1");
    assert.equal(shard.bundle.semester, SEMESTER);
    assert.equal(shard.bundle.first_page_no, 1);
    assert.equal(shard.bundle.page_size, 200);
    assert.equal(shard.bundle.pages.length, 1);
    assert.equal(shard.bundle.pages[0].page_no, 1);
    seen += shard.bundle.pages[0].response.data.rows.length;
  }
  assert.equal(seen, TOTAL_ROWS, "五个 shard 必须逐条产出，不丢行");
});

test("五校区：diagnostics 记录 baseline 与每个 shard 的结构计数", async () => {
  const { collector } = loadShardedCollector();

  const result = await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });
  const diagnostics = result.diagnostics;

  assert.equal(diagnostics.baseline_before, TOTAL_ROWS);
  assert.equal(diagnostics.baseline_after, TOTAL_ROWS);
  assert.equal(diagnostics.shard_count, 5);
  assert.equal(diagnostics.approved_shard_count, 5);
  assert.equal(diagnostics.shard_total_sum, TOTAL_ROWS);
  assert.equal(diagnostics.page_size, 200);

  assert.equal(diagnostics.shards.length, 5);

  diagnostics.shards.forEach((record, index) => {
    assert.equal(record.shard_id, SHARDS[index].shard_id);
    assert.equal(record.openingSchoolNumber, SHARDS[index].openingSchoolNumber);
    assert.equal(record.expectedTotal, SHARD_ROW_COUNTS[index]);
    assert.equal(record.accumulatedRows, SHARD_ROW_COUNTS[index]);
    assert.equal(record.stoppedReason, "reached_total");
    assert.equal(record.page_count, 1);
    assert.equal(record.expected_pages, 1);
  });
});

test("全局 batch pacing：默认策略下每个相邻请求的等待都符合 5+5min 规则", async () => {
  const { collector, calls, timers } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER });

  // 7 个请求（baseline + 5 shard + baseline_after）⇒ 6 次等待
  assert.equal(calls.length, 7);
  assert.equal(timers.length, 6);

  // request 1→5 之间是普通 30 秒；request 5→6 是批次冷却；
  // request 6→7（= baseline_after）回到普通 30 秒
  assert.deepEqual(timers, [30000, 30000, 30000, 30000, 300000, 30000]);

  assertBatchPacingInvariant(calls, timers);
});

test("全局 batch pacing：request 1～5 为普通 >=30s pacing", async () => {
  const { collector, calls, timers } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER });

  // 前 4 次等待对应 request 1→2 / 2→3 / 3→4 / 4→5
  for (let index = 0; index < 4; index += 1) {
    assert.equal(timers[index], 30000);
    assert.ok(timers[index] >= 30000, "普通相邻请求间隔必须 >= 30000ms");
  }
  assert.equal(calls.length >= 5, true);
});

test("全局 batch pacing：request5 → request6 先冷却 >=300000ms", async () => {
  const { collector, timers } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER });

  assert.ok(timers[4] >= 300000, `request5 → request6 必须 >= 300000ms，实际 ${timers[4]}`);
});

test("全局 batch pacing：request10 → request11 再次冷却 >=300000ms", async () => {
  // 每个校区 2 页 ⇒ 1 + 10 + 1 = 12 个请求
  const { collector, calls, timers } = loadShardedCollector({
    campuses: defaultCampuses([205, 205, 205, 205, 205]),
    baselineTotals: [1025, 1025],
  });

  await collector.collectSharded({ semester: SEMESTER, maxPages: 2 });

  assert.equal(calls.length, 12);
  assert.equal(timers.length, 11);

  assert.ok(timers[4] >= 300000, `request5 → request6 必须冷却，实际 ${timers[4]}`);
  assert.ok(timers[9] >= 300000, `request10 → request11 必须冷却，实际 ${timers[9]}`);

  // 两次冷却之间仍是普通 30 秒（不是每 5 个请求都冷却）
  assert.deepEqual(timers.slice(5, 9), [30000, 30000, 30000, 30000]);

  assertBatchPacingInvariant(calls, timers);
});

test("全局 batch pacing：shard 边界**不会**重置 batch counter", async () => {
  // 东校园 1200 行 = 6 页：全局第 5 个请求是东校园第 4 页，冷却因而发生在同一 shard 的页间
  const rowCounts = [1200, 1, 1, 1, 1];
  const { collector, calls, timers } = loadShardedCollector({
    campuses: defaultCampuses(rowCounts),
    baselineTotals: [1204, 1204],
  });

  await collector.collectSharded({ semester: SEMESTER, maxPages: 6 });

  // 请求序列：1 baseline, 2..7 东校园第 1..6 页, 8..11 其余四个校区, 12 baseline_after
  assert.equal(calls.length, 12);
  assert.equal(calls[5].campus, "5063559", "全局第 6 个请求仍是东校园（同一 shard 内）");
  assert.equal(calls[5].pageNo, 5);

  // 冷却必须落在东校园**内部**的页间（若 per-shard 计数会在 shard 边界重置，这里就不会冷却）
  assert.ok(timers[4] >= 300000, `同一 shard 内跨批次也必须冷却，实际 ${timers[4]}`);
  assert.deepEqual(timers.slice(0, 4), [30000, 30000, 30000, 30000]);

  assertBatchPacingInvariant(calls, timers);
});

test("全局 batch pacing：baseline_before 与 baseline_after 都算全局请求", async () => {
  const { collector, calls, timers } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER });

  // 请求 1..5 = baseline_before + 东/北/南/深圳；⇒ 冷却出现在第 6 个请求（珠海）之前
  assert.equal(calls[0].campus, undefined);
  assert.equal(calls[4].campus, "333291143", "全局第 5 个请求是深圳校区");
  assert.equal(calls[5].campus, "5062203", "冷却后发的是珠海校区（第 6 个请求）");
  assert.ok(timers[4] >= 300000, "第 6 个请求前必须冷却（证明 baseline_before 计入）");

  // baseline_after 是第 7 个请求：它前面是普通 30 秒，且它确实经过了 pacer
  assert.equal(calls[6].campus, undefined);
  assert.equal(timers[5], 30000, "baseline_after 也走同一个 pacer（先等普通间隔）");

  assertBatchPacingInvariant(calls, timers);
});

test("全局 batch pacing：batch 未满时**不**额外等待 5 分钟", async () => {
  // HTTP 600 出现在东校园第 1 页 ⇒ 整个 run 只有 2 个请求
  const { collector, calls, timers } = loadShardedCollector({
    campuses: defaultCampuses([205, 1, 4, 2, 3]),
    baselineTotals: [215, 215],
    http600: { campus: "5063559", pageNo: 1 },
  });

  await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, maxPages: 2 }),
  );

  assert.equal(calls.length, 2);
  assert.deepEqual(timers, [30000], "未满一个 batch 时只等普通间隔");
  assert.ok(!timers.includes(300000));
});

test("collect() 也走同一个全局 pacing controller（含批次冷却）", async () => {
  const { collector, calls, timers } = loadShardedCollector({
    baselineRows: shardRows("BASE", 6),
  });

  await collector.collect({ semester: SEMESTER, pageSize: 1, maxPages: 6 });

  assert.equal(calls.length, 6, "6 个请求全部经过 pacer");
  assert.deepEqual(timers, [30000, 30000, 30000, 30000, 300000]);
});

test("五校区：pacing 下限 = 默认 = 30000ms，batch 常量已暴露", async () => {
  const { collector } = loadShardedCollector();

  assert.equal(collector.MIN_DELAY_MS, 30000);
  assert.equal(collector.DEFAULT_DELAY_MS, 30000);
  assert.equal(collector.MAX_REQUESTS_PER_BATCH, 5);
  assert.equal(collector.BATCH_COOLDOWN_MS, 300000);

  // 未显式传 delayMs 时用的就是下限值
  const { collector: defaultCollector, calls, timers } = loadShardedCollector();
  await defaultCollector.collectSharded({ semester: SEMESTER });

  assertBatchPacingInvariant(calls, timers, { delayMs: defaultCollector.MIN_DELAY_MS });
});

test("五校区：只弹一次确认框（不是每个 shard 各弹一次）", async () => {
  const { collector, confirms } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER, maxPages: 3 });

  assert.equal(confirms.length, 1);
  assert.ok(confirms[0].includes("五校区串行采集"), `确认文案应说明五校区，实际：${confirms[0]}`);
  assert.ok(confirms[0].includes("5 个成功请求"), `确认文案应说明批次策略，实际：${confirms[0]}`);
});

test("五校区：默认 maxPages 下不弹确认框", async () => {
  const { collector, confirms } = loadShardedCollector();

  const result = await collector.collectSharded({ semester: SEMESTER });

  assert.equal(confirms.length, 0);
  assert.equal(result.shards.length, 5);
});

// ---------------------------------------------------------------------------
// 2. 多页 shard / expected_pages 只作 diagnostics
// ---------------------------------------------------------------------------

test("多页 shard：累加到 expectedTotal 后 reached_total 停止", async () => {
  const rowCounts = [205, 1, 4, 2, 3];
  const { collector, calls } = loadShardedCollector({
    campuses: defaultCampuses(rowCounts),
    baselineTotals: [215, 215],
  });

  const result = await collector.collectSharded({ semester: SEMESTER, maxPages: 2, delayMs: 30000 });

  const east = result.diagnostics.shards[0];
  assert.equal(east.expectedTotal, 205);
  assert.equal(east.accumulatedRows, 205);
  assert.equal(east.stoppedReason, "reached_total");
  assert.equal(east.page_count, 2);
  assert.equal(east.expected_pages, 2);

  const eastCalls = calls.filter((call) => call.campus === "5063559");
  assert.deepEqual(
    eastCalls.map((call) => call.pageNo),
    [1, 2],
    "同一 shard 内页码必须从 1 连续递增",
  );

  const first = result.shards[0].bundle.pages[0];
  const second = result.shards[0].bundle.pages[1];
  assert.equal(first.response.data.rows.length, 200);
  assert.equal(second.response.data.rows.length, 5);
  assert.equal(second.response.data.total, 205, "每页都必须带同一个 total");
});

test("⛔ expected_pages 只作 diagnostics：页数与 ceil 不一致也必须成功", async () => {
  // 学校侧返回"半页"（每页 100 行），因此 300 行要 3 页，而 ceil(300/200)=2。
  const campuses = defaultCampuses([300, 1, 4, 2, 3]);
  const { collector } = loadShardedCollector({
    campuses,
    baselineTotals: [310, 310],
    pageRows: (rows, pageNo) => rows.slice((pageNo - 1) * 100, pageNo * 100),
  });

  const result = await collector.collectSharded({ semester: SEMESTER, maxPages: 3, delayMs: 30000 });

  const east = result.diagnostics.shards[0];
  assert.equal(east.page_count, 3);
  assert.equal(east.expected_pages, 2);
  assert.notEqual(east.page_count, east.expected_pages);
  assert.equal(east.accumulatedRows, 300);
  assert.equal(east.stoppedReason, "reached_total");
  assert.equal(result.diagnostics.baseline_after, 310);
});

// ---------------------------------------------------------------------------
// 3. 整体失败：baseline sandwich / 未取满 / 覆盖性
// ---------------------------------------------------------------------------

test("baseline 漂移（after 变大）：整体失败，且 diagnostics 记下两个 baseline", async () => {
  const { collector } = loadShardedCollector({
    baselineTotals: [TOTAL_ROWS, TOTAL_ROWS + 1],
  });

  const error = await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, delayMs: 30000 }),
  );

  assert.ok(error.message.includes("baseline_before"), `实际：${error.message}`);
  assert.ok(error.message.includes("baseline_after"), `实际：${error.message}`);
  assert.equal(error.diagnostics.baseline_before, TOTAL_ROWS);
  assert.equal(error.diagnostics.baseline_after, TOTAL_ROWS + 1);
  assert.equal(error.diagnostics.shards.length, 5);
});

test("baseline 漂移（after 变小）：同样整体失败", async () => {
  const { collector } = loadShardedCollector({
    baselineTotals: [TOTAL_ROWS, TOTAL_ROWS - 1],
  });

  const error = await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, delayMs: 30000 }),
  );

  assert.equal(error.diagnostics.baseline_before, TOTAL_ROWS);
  assert.equal(error.diagnostics.baseline_after, TOTAL_ROWS - 1);
});

test("shard 未取满：立即整体停止，⛔ 不再继续打其它校区", async () => {
  const { collector, calls } = loadShardedCollector({
    campuses: defaultCampuses([205, 1, 4, 2, 3]),
    baselineTotals: [215, 215],
  });

  const error = await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, maxPages: 1, delayMs: 30000 }),
  );

  assert.ok(error.message.includes("东校园"), `实际：${error.message}`);
  assert.ok(error.message.includes("未取满"), `实际：${error.message}`);

  // baseline + 仅东校园的第 1 页；其它校区**没有**被请求
  assert.deepEqual(
    calls.map((call) => call.campus),
    [undefined, "5063559"],
  );

  assert.equal(error.diagnostics.shards.length, 1);
  assert.equal(error.diagnostics.shards[0].stoppedReason, "max_pages");
  assert.equal(error.diagnostics.shards[0].accumulatedRows, 200);
  assert.equal(error.diagnostics.baseline_after, null, "失败前不应再发 baseline_after");
});

test("Σ shard total != baseline：baseline 稳定后报 coverage mismatch（after 必须已请求）", async () => {
  const { collector, calls } = loadShardedCollector({
    baselineTotals: [TOTAL_ROWS - 1, TOTAL_ROWS - 1],
  });

  const error = await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, delayMs: 30000 }),
  );

  assert.ok(error.message.includes("shard coverage mismatch"), `实际：${error.message}`);
  assert.ok(!error.message.includes("snapshot window unstable"), "⛔ baseline 稳定，不该报不稳定");

  // ⛔ 五个 shard 全部完整成功后，baseline_after **无条件**被请求
  assert.equal(calls.length, 7, "baseline + 五个 shard + baseline_after");
  assert.equal(calls[6].campus, undefined);
  assert.equal(error.diagnostics.baseline_after, TOTAL_ROWS - 1);
  assert.equal(error.diagnostics.shard_count, 5);
  assert.equal(error.diagnostics.shard_total_sum, TOTAL_ROWS);
});

// ---------------------------------------------------------------------------
// 3b. 判定顺序（Review Blocker）：先 baseline 稳定性，再 shard 覆盖性
// ---------------------------------------------------------------------------

/**
 * 按 Review 指定的场景总数造出五个校区的行数。
 *
 * ⚠️ 这里只把它当作**场景计数**（6880 / 6881 / 6879）喂给假 fetch；
 * 真实各校区人工 total（1071/405/…）⛔ 不进测试，也⛔ 不进任何 production 判定。
 */
function campusesForTotal(total) {
  const each = Math.floor(total / SHARDS.length);
  const sizes = SHARDS.map(() => each);
  sizes[0] += total - each * SHARDS.length;

  return SHARDS.map((shard, index) => ({
    openingSchoolNumber: shard.openingSchoolNumber,
    rows: shardRows(`SYN${index + 1}`, sizes[index]),
  }));
}

/** 五个校区都能在 maxPages 内取满（每校区 <= 1377 行 ⇒ <= 7 页）。 */
const REVIEW_SCENARIO_MAX_PAGES = 7;

test("顺序：before=6880, Σ shard=6881, after=6881 → snapshot window unstable", async () => {
  const { collector, calls } = loadShardedCollector({
    campuses: campusesForTotal(6881),
    baselineTotals: [6880, 6881],
  });

  const error = await captureRejection(() =>
    collector.collectSharded({
      semester: SEMESTER,
      maxPages: REVIEW_SCENARIO_MAX_PAGES,
      delayMs: 30000,
    }),
  );

  assert.ok(error.message.includes("snapshot window unstable"), `实际：${error.message}`);
  // ⛔ 覆盖性不得抢在 baseline 稳定性之前判定
  assert.ok(
    !error.message.includes("shard coverage mismatch"),
    "⛔ baseline 未稳定时不得报覆盖性",
  );

  // baseline_after **确实被请求**（且是最后一个请求）
  const baselineCalls = calls.filter((call) => call.campus === undefined);
  assert.equal(baselineCalls.length, 2, "baseline_before 与 baseline_after 都必须发出");
  assert.equal(calls[calls.length - 1].campus, undefined);

  // 五个 shard 都完整成功之后才发 baseline_after
  assert.equal(error.diagnostics.shard_count, 5);
  assert.equal(error.diagnostics.baseline_before, 6880);
  assert.equal(error.diagnostics.baseline_after, 6881);
  assert.equal(error.diagnostics.shard_total_sum, 6881);
  error.diagnostics.shards.forEach((record) => {
    assert.equal(record.stoppedReason, "reached_total");
    assert.equal(record.accumulatedRows, record.expectedTotal);
  });
});

test("顺序：before=6880, Σ shard=6879, after=6880 → shard coverage mismatch", async () => {
  const { collector, calls } = loadShardedCollector({
    campuses: campusesForTotal(6879),
    baselineTotals: [6880, 6880],
  });

  const error = await captureRejection(() =>
    collector.collectSharded({
      semester: SEMESTER,
      maxPages: REVIEW_SCENARIO_MAX_PAGES,
      delayMs: 30000,
    }),
  );

  assert.ok(error.message.includes("shard coverage mismatch"), `实际：${error.message}`);
  assert.ok(
    !error.message.includes("snapshot window unstable"),
    "⛔ baseline 稳定，不得报不稳定",
  );

  assert.equal(error.diagnostics.baseline_before, 6880);
  assert.equal(error.diagnostics.baseline_after, 6880);
  assert.equal(error.diagnostics.shard_total_sum, 6879);
  assert.equal(calls.filter((call) => call.campus === undefined).length, 2);
});

test("顺序：只要求 shard 失败才可跳过 baseline_after（否则必须请求）", async () => {
  // shard 未取满 → 允许 fail-fast：⛔ 不得发出 baseline_after
  const { collector, calls } = loadShardedCollector({
    campuses: defaultCampuses([205, 1, 4, 2, 3]),
    baselineTotals: [215, 215],
  });

  await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, maxPages: 1, delayMs: 30000 }),
  );

  assert.deepEqual(
    calls.map((call) => call.campus),
    [undefined, "5063559"],
    "⛔ shard 失败时不得继续请求其它校区，也不得请求 baseline_after",
  );
});

test("取消确认：不发出任何请求，也不产出 bundle / diagnostics", async () => {
  const { collector, calls } = loadShardedCollector({ confirmResult: false });

  const result = await collector.collectSharded({
    semester: SEMESTER,
    maxPages: 3,
    delayMs: 30000,
  });

  assert.equal(result.cancelled, true);
  assert.equal(result.shards.length, 0);
  assert.equal(result.diagnostics, null);
  assert.equal(calls.length, 0);
});

test("HTTP 600（真实证据）：fail closed，不重试 / 不跳页 / 不续采 / 不产出 bundle", async () => {
  const { collector, calls, timers } = loadShardedCollector({
    campuses: defaultCampuses([205, 1, 4, 2, 3]),
    baselineTotals: [215, 215],
    http600: { campus: "5063559", pageNo: 2 }, // 东校园第 2 页
  });

  const error = await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, maxPages: 2, delayMs: 30000 }),
  );

  assert.ok(error.message.includes("东校园"), `实际：${error.message}`);
  assert.ok(error.message.includes("600"), `实际：${error.message}`);

  // ⛔ 不重试 / 不 backoff 重试：失败的那一页**只请求过一次**
  const eastPages = calls.filter((call) => call.campus === "5063559").map((call) => call.pageNo);
  assert.deepEqual(eastPages, [1, 2]);

  // ⛔ 不跳页 / 不续采：不再请求其它校区，也不请求 baseline_after
  assert.deepEqual(
    calls.map((call) => call.campus),
    [undefined, "5063559", "5063559"],
  );
  assert.equal(error.diagnostics.baseline_after, null);

  // ⛔ 不产出任何 bundle / 该 shard 没有任何诊断记录
  assert.equal(error.diagnostics.shard_count, 0);
  assert.equal(error.diagnostics.shards.length, 0);

  // pacing 在失败之前同样成立
  assertBatchPacingInvariant(calls, timers);
});

// ---------------------------------------------------------------------------
// 4. 参数白名单 / 限速
// ---------------------------------------------------------------------------

for (const [label, options] of [
  ["pageSize 覆盖", { pageSize: 100 }],
  ["firstPageNo 覆盖", { firstPageNo: 2 }],
  ["自定义 shard 列表", { shardIds: ["东校园"] }],
  ["batch 大小覆盖", { maxRequestsPerBatch: 1 }],
  ["cooldown 覆盖", { batchCooldownMs: 0 }],
  ["未知参数", { foo: 1 }],
]) {
  test(`五校区：${label} 在发请求之前被拒绝`, async () => {
    const { collector, calls } = loadShardedCollector();

    const error = await captureRejection(() =>
      collector.collectSharded(Object.assign({ semester: SEMESTER }, options)),
    );

    assert.equal(calls.length, 0, "白名单校验必须早于任何请求");
    // ⛔ 不回显调用方给出的键名（错误信息只列允许项）
    for (const name of Object.keys(options)) {
      assert.ok(!error.message.includes(name), `⛔ 不得回显参数名：${name}`);
    }
    assert.ok(error.message.includes("参数名不予回显"), `实际：${error.message}`);
  });
}

for (const tooFast of [0, 1, 999, 1500, 9999, 29999]) {
  test(`五校区：delayMs=${tooFast}（< 30000）被拒绝，且不发请求`, async () => {
    const { collector, calls } = loadShardedCollector();

    const error = await captureRejection(() =>
      collector.collectSharded({ semester: SEMESTER, delayMs: tooFast }),
    );

    assert.equal(calls.length, 0, "⛔ 低于下限时不得发出任何请求");
    assert.ok(error.message.includes("30000"), `错误信息应说明下限，实际：${error.message}`);
  });
}

test("五校区：delayMs=30000（下限）被接受，且按 5+5min 策略 pacing", async () => {
  const { collector, calls, timers } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });

  assert.equal(calls.length, 7);
  assert.deepEqual(timers, [30000, 30000, 30000, 30000, 300000, 30000]);
  assertBatchPacingInvariant(calls, timers, { delayMs: 30000 });
});

test("五校区：delayMs 只允许调大，调大后仍按该值 pacing", async () => {
  const { collector, calls, timers } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER, delayMs: 45000 });

  assert.equal(calls.length, 7);
  assert.deepEqual(timers, [45000, 45000, 45000, 45000, 300000, 45000]);
  assertBatchPacingInvariant(calls, timers, { delayMs: 45000 });
});

test("五校区：delayMs 大于冷却时，批次边界取较大者（不缩短间隔）", async () => {
  const { collector, calls, timers } = loadShardedCollector();

  await collector.collectSharded({ semester: SEMESTER, delayMs: 600000 });

  assert.equal(calls.length, 7);
  assert.deepEqual(timers, [600000, 600000, 600000, 600000, 600000, 600000]);
  assertBatchPacingInvariant(calls, timers, { delayMs: 600000 });
});

test("五校区：semester 缺失 / 为空被拒绝", async () => {
  for (const bad of [undefined, "", "   "]) {
    const { collector, calls } = loadShardedCollector();

    await captureRejection(() => collector.collectSharded({ semester: bad }));

    assert.equal(calls.length, 0);
  }
});

// ---------------------------------------------------------------------------
// 5. 序列化边界：裸 bundle 与 diagnostics 严格分开
// ---------------------------------------------------------------------------

test("五校区：toShardJson 输出裸 bundle，toDiagnosticsJson 输出外层 diagnostics", async () => {
  const { collector } = loadShardedCollector();

  const result = await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });

  const east = JSON.parse(collector.toShardJson(result, "东校园"));
  assert.equal(Object.keys(east).sort().join(","), [...BUNDLE_KEYS].sort().join(","));
  assert.equal(east.semester, SEMESTER);

  const diagnostics = JSON.parse(collector.toDiagnosticsJson(result));
  assert.equal(diagnostics.baseline_before, TOTAL_ROWS);
  assert.equal(diagnostics.shards.length, 5);

  // ⛔ diagnostics 不得混进裸 bundle
  const bundleText = collector.toShardJson(result, "东校园");
  for (const forbidden of ["diagnostics", "expected_pages", "baseline_before", "stoppedReason"]) {
    assert.ok(!bundleText.includes(forbidden), `⛔ 裸 bundle 不得含 ${forbidden}`);
  }
});

test("五校区：shardBundle 只接受已批准校区名，且不回显其它名字", async () => {
  const { collector } = loadShardedCollector();

  const result = await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });

  for (const shard of SHARDS) {
    const bundle = collector.shardBundle(result, shard.shard_id);
    assert.equal(bundle.semester, SEMESTER);
    assert.equal(bundle.page_size, 200);
  }

  const error = await captureRejection(async () =>
    collector.shardBundle(result, "未批准校区哨兵"),
  );
  assert.ok(!error.message.includes("未批准校区哨兵"), "⛔ 不得回显调用方给出的名字");
});

test("五校区：toJson() 拒绝五校区结果（它不是单个裸 bundle）", async () => {
  const { collector } = loadShardedCollector();

  const result = await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });

  await assert.rejects(async () => collector.toJson(result), /伪 bundle/);
});

test("五校区：取消结果无法被任何序列化入口使用", async () => {
  const { collector } = loadShardedCollector({ confirmResult: false });

  const result = await collector.collectSharded({
    semester: SEMESTER,
    maxPages: 3,
    delayMs: 30000,
  });

  await assert.rejects(async () => collector.shardBundle(result, "东校园"));
  await assert.rejects(async () => collector.toShardJson(result, "东校园"));
  await assert.rejects(async () => collector.toDiagnosticsJson(result));
});

test("五校区：某个 shard 内解析失败 → 带 shard 名、单一前缀、并附 diagnostics", async () => {
  const campuses = defaultCampuses();
  // 北校园第 1 条：5 字段二义形态（既非明确 teacher 也非明确 location）→ fail closed
  campuses[1].rows[0] = Object.assign(
    rawRow(`1-8周/星期五/第5-6节/示例-教师A/${ACTIVITY}`),
    { classNumber: "SYN2-BAD" },
  );

  const { collector, calls } = loadShardedCollector({ campuses });

  const error = await captureRejection(() =>
    collector.collectSharded({ semester: SEMESTER, delayMs: 30000 }),
  );

  assert.ok(error.message.includes("北校园"), `实际：${error.message}`);
  assert.ok(error.message.includes("不猜语义"), `实际：${error.message}`);
  assert.equal(
    error.message.split("[学航采集器]").length - 1,
    1,
    "⛔ 包装后的错误信息不得出现两个前缀",
  );
  assert.ok(!error.message.includes("示例-教师A"), "⛔ 不得回显二义字段取值");

  // 已经完成的 shard 进度保留在 diagnostics 里；失败 shard 之后不再请求
  assert.equal(error.diagnostics.shard_count, 1);
  assert.equal(error.diagnostics.shards[0].shard_id, "东校园");
  assert.deepEqual(
    calls.map((call) => call.campus),
    [undefined, "5063559", "5062202"],
  );
});

// ---------------------------------------------------------------------------
// 6. 隐私：shard 路径仍走同一套最小化 / 脱敏
// ---------------------------------------------------------------------------

test("五校区：shard bundle 内的 teacher 仍被脱敏", async () => {
  const campuses = defaultCampuses();
  campuses[2].rows[0] = Object.assign(
    rawRow(`1-8周/星期五/第5-6节/${TEACHER}/${ACTIVITY}`),
    { classNumber: "SYN3-PRIVACY" },
  );

  const { collector } = loadShardedCollector({ campuses });

  const result = await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });
  const rows = result.shards[2].bundle.pages[0].response.data.rows;

  const redacted = rows.find((row) => row.classNumber === "SYN3-PRIVACY");
  assert.ok(redacted.teachingTimePlaceStr.includes("REDACTED"));
  assert.ok(!redacted.teachingTimePlaceStr.includes(TEACHER), "⛔ 真实 teacher 不得进入 shard bundle");

  const diagnosticsText = collector.toDiagnosticsJson(result);
  for (const forbidden of [TEACHER, "courseNum", "courseName", "classNumber", "teachingTimePlaceStr", "SYN3"]) {
    assert.ok(!diagnosticsText.includes(forbidden), `⛔ diagnostics 不得含 ${forbidden}`);
  }
});

test("五校区：diagnostics 只有结构化计数，没有任何 row / 课程取值", async () => {
  const { collector } = loadShardedCollector();

  const result = await collector.collectSharded({ semester: SEMESTER, delayMs: 30000 });

  const serialized = JSON.stringify(result.diagnostics);

  for (const forbidden of [
    "SYN1",
    "courseNum",
    "courseName",
    "classNumber",
    "teachingTimePlaceStr",
    "REDACTED",
    LOCATION,
    '"rows"',
    "raw_rows",
  ]) {
    assert.ok(!serialized.includes(forbidden), `⛔ diagnostics 不得含 ${forbidden}`);
  }
});
