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

// ---------------------------------------------------------------------------
// 一次性 Layout B 诊断（**零留存**）：只输出七个聚合计数
//
// 合成数据全部为人工虚构；断言只针对"计数是否正确"与"是否泄露输入取值"。
//
// ⚠️ 已确认 activity 集合的**来源**是"已确认 layout 的 activity 固定槽位"：
//    2 / 3 字段 non-concrete、4 字段 concrete、5 字段 concrete（location-or-teacher）、
//    5 字段 layout A、6 字段 concrete。语义角色**只**由 layout 结构确定，
//    ⛔ 不用"非空字符串 = activity"当角色证据（它只是语法检查）。
// ---------------------------------------------------------------------------

const LAYOUT_B_CAMPUS = "SYN-CAMPUS-LB";
const LAYOUT_B_TEACHER_OTHER = "示例教师B";
const LAYOUT_B_PROVIDER_TEACHER = "示例教师C";
const LAYOUT_B_RETURN_KEYS = [
  "candidate_count",
  "comparable_teaching_name_count",
  "f3_equals_teaching_name_count",
  "f4_equals_teaching_name_count",
  "f4_activity_count",
  "f3_in_confirmed_activity_set_count",
  "f4_in_confirmed_activity_set_count",
  "f3_matching_raw_fields",
];

/** 七个已确认 layout 的 provider activity 取值（人工虚构、互不相同）。 */
const PROVIDER_ACTIVITY = [
  "示例环节甲",
  "示例环节乙",
  "示例环节丙",
  "示例环节丁",
  "示例环节戊",
  "示例环节己",
  "示例环节庚",
];

/** 九个**未确认** layout 的槽位取值（人工虚构；⛔ 必须不得进入已确认集合）。 */
const EXCLUDED_ACTIVITY = [
  "示例排除一",
  "示例排除二",
  "示例排除三",
  "示例排除四",
  "示例排除五",
  "示例排除六",
  "示例排除七",
  "示例排除八",
  "示例排除九",
];

/** 合成一条 Layout B 形态的 row：4 字段 `weeks / location / f3 / f4`。 */
function layoutBRow(text, options = {}) {
  const row = Object.assign(rawRow(text), {
    classNumber: options.classNumber || "SYN-LB-0001",
  });
  if (options.hasTeachingName !== false) {
    row.teachingName =
      options.teachingName === undefined ? TEACHER : options.teachingName;
  }
  return row;
}

/**
 * 合成一条**已确认 layout** 的 provider row（其 activity 固定槽位的取值会进入集合）。
 * 行内只有这一段，且 `teachingName` 缺失（provider 不需要参与候选比较）。
 */
function providerRow(segment, classNumber) {
  return Object.assign(rawRow(segment), { classNumber: classNumber });
}

/** 七个已确认 layout 的 provider（每个 activity 槽位放一个**不同**的虚构 token）。 */
function confirmedProviderRows() {
  return [
    providerRow(`1-17周/${PROVIDER_ACTIVITY[0]}`, "SYN-PRV-2F"),
    providerRow(`1-17周/${LAYOUT_B_PROVIDER_TEACHER}/${PROVIDER_ACTIVITY[1]}`, "SYN-PRV-3F"),
    providerRow(`1-8周/星期五/第5-6节/${PROVIDER_ACTIVITY[2]}`, "SYN-PRV-4F"),
    providerRow(
      `1-8周/星期五/第5-6节/${LOCATION}/${PROVIDER_ACTIVITY[3]}`,
      "SYN-PRV-5F-LOC",
    ),
    providerRow(
      `1-8周/星期五/第5-6节/${LAYOUT_B_PROVIDER_TEACHER}/${PROVIDER_ACTIVITY[4]}`,
      "SYN-PRV-5F-TCH",
    ),
    providerRow(`1-8周/星期五/${LOCATION}/REDACTED/${PROVIDER_ACTIVITY[5]}`, "SYN-PRV-5F-A"),
    providerRow(
      `1-8周/星期五/第5-6节/${LOCATION}/${LAYOUT_B_PROVIDER_TEACHER}/${PROVIDER_ACTIVITY[6]}`,
      "SYN-PRV-6F",
    ),
  ];
}

/** 只有 2 字段 non-concrete 一个 provider（最小非空集合）。 */
function minimalProviderRow() {
  return providerRow(`1-17周/${ACTIVITY}`, "SYN-PRV-MIN");
}

function loadLayoutBCollector(rows, options = {}) {
  return loadShardedCollector({
    campuses: [{ openingSchoolNumber: LAYOUT_B_CAMPUS, rows }],
    confirmResult: options.confirmResult,
  });
}

async function runLayoutBDiagnostic(rows, options = {}) {
  const harness = loadLayoutBCollector(rows, options);
  const result = await harness.collector.diagnoseLayoutBCandidates({
    semester: SEMESTER,
    openingSchoolNumber: LAYOUT_B_CAMPUS,
    maxPages: options.maxPages === undefined ? 1 : options.maxPages,
  });
  return Object.assign({ result }, harness);
}

/**
 * 断言七个计数。
 *
 * ⚠️ 结果对象由 VM realm 创建，直接 `deepStrictEqual` 会因跨 realm 原型不同而失败；
 * 这里先摊平成宿主 realm 的对象（仍然严格比较**键集合**与取值）。
 */
function assertLayoutBCounts(result, expected) {
  assert.deepEqual({ ...result }, expected);
}

/**
 * 一批混合合成 row：4 个真候选 + 5 个 near-miss + 2 个已确认 provider。
 *
 * 集合 = { ACTIVITY }（来自 5 字段 layout A 与 6 字段 concrete 的 activity 槽位）。
 */
function layoutBScenario() {
  return [
    // 真候选 1：teachingName 与 f3 相同
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-0001",
      teachingName: TEACHER,
    }),
    // 真候选 2：teachingName 与 f3 不同
    layoutBRow(`1-8单周/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-0002",
      teachingName: LAYOUT_B_TEACHER_OTHER,
    }),
    // 真候选 3：raw row **没有** teachingName 属性
    layoutBRow(`3-4双周/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-0003",
      hasTeachingName: false,
    }),
    // 真候选 4：f4 为空 → 不计入 activity 语法检查
    layoutBRow(`1-8周校外/${LOCATION}/${TEACHER}/`, {
      classNumber: "SYN-LB-0004",
      teachingName: TEACHER,
    }),
    // near-miss：f2 只有 2 个 '-' 分段（不是已确认 location）
    layoutBRow(`1-8周/${CAMPUS}-2108/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-0005",
      teachingName: TEACHER,
    }),
    // near-miss：f3 是已确认 sections token
    layoutBRow(`1-8周/${LOCATION}/第5-6节/${ACTIVITY}`, {
      classNumber: "SYN-LB-0006",
      teachingName: TEACHER,
    }),
    // near-miss：f1 不是已批准 weeks
    layoutBRow(`第1-8周/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-0007",
      teachingName: TEACHER,
    }),
    // near-miss：5 字段（Layout A 形态）
    layoutBRow(`1-8周/星期五/第5-6节/REDACTED/${ACTIVITY}`, {
      classNumber: "SYN-LB-0008",
      teachingName: TEACHER,
    }),
    // near-miss：6 字段（concrete 形态）
    layoutBRow(`1-8周/星期五/第5-6节/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-0009",
      teachingName: TEACHER,
    }),
    ...confirmedProviderRows(),
  ];
}

test("Layout B 诊断：加载脚本不自动调用", async () => {
  const { calls } = loadLayoutBCollector(layoutBScenario());

  assert.equal(calls.length, 0, "⛔ 仅加载不得发出任何请求");
});

test("Layout B 诊断：4 个真候选 + 5 个 near-miss + provider → 七个计数 + 字段名映射", async () => {
  const { result } = await runLayoutBDiagnostic(layoutBScenario());

  assertLayoutBCounts(result, {
    candidate_count: 4,
    // 候选 3 所在 raw row **没有** teachingName → 不可比较
    comparable_teaching_name_count: 3,
    // 候选 1 与候选 4 的 f3 都等于本行 teachingName；候选 2 不等
    f3_equals_teaching_name_count: 2,
    // f4 是 activity（或空），**没有**任何候选的 f4 等于 teachingName
    f4_equals_teaching_name_count: 0,
    // 候选 4 的 f4 为空 → 不计入语法检查
    f4_activity_count: 3,
    // 候选的 f3 是 teacher，不在已确认 activity 集合里
    f3_in_confirmed_activity_set_count: 0,
    // 候选 1 / 2 / 3 的 f4 == ACTIVITY ∈ 集合
    f4_in_confirmed_activity_set_count: 3,
    // f3 在 raw row 字符串字段里的严格相等命中：只有 teachingName（与上面的 2 一致）
    f3_matching_raw_fields: { teachingName: 2 },
  });
});

test("Layout B 诊断：返回值只有七个计数 + 字段名映射，且不泄露任何输入取值", async () => {
  const rows = layoutBScenario();
  const { result } = await runLayoutBDiagnostic(rows);

  assert.deepEqual(Object.keys(result).sort(), [...LAYOUT_B_RETURN_KEYS].sort());

  const serialized = JSON.stringify(result);

  // ⛔ 任何**取值**都不得出现在输出里（字段名本身是映射的键，按本轮裁定允许输出）
  for (const forbidden of [
    TEACHER,
    LAYOUT_B_TEACHER_OTHER,
    LAYOUT_B_PROVIDER_TEACHER,
    ACTIVITY,
    ...PROVIDER_ACTIVITY,
    LOCATION,
    CAMPUS,
    CLASSROOM,
    "SYN-LB",
    "SYN-PRV",
    "00000000",
    '"rows"',
    '"fields"',
    '"segments"',
    '"tokens"',
    "REDACTED",
    "第5-6节",
  ]) {
    assert.ok(!serialized.includes(forbidden), `⛔ 诊断输出不得含 ${forbidden}`);
  }

  // 七个计数必须是数字；字段名映射必须是 "字符串键 → >= 1 的正整数"
  for (const [key, value] of Object.entries(result)) {
    if (key === "f3_matching_raw_fields") {
      continue;
    }
    assert.equal(typeof value, "number", `${key} 必须是数字计数`);
  }

  const matches = result.f3_matching_raw_fields;
  assert.equal(typeof matches, "object");
  for (const [fieldName, count] of Object.entries(matches)) {
    assert.equal(typeof fieldName, "string");
    assert.ok(Number.isInteger(count) && count >= 1, "⛔ 只返回 >= 1 次命中的字段名");
  }
});

test("Layout B 诊断：命中目标形态（f3 = activity、f4 = teacher）", async () => {
  // 期望的真实结论形态：f3 ∈ 已确认 activity 集合、f4 == teachingName
  const { result } = await runLayoutBDiagnostic([
    layoutBRow(`1-8周/${LOCATION}/${ACTIVITY}/${TEACHER}`, {
      classNumber: "SYN-LB-TARGET",
      teachingName: TEACHER,
    }),
    minimalProviderRow(),
  ]);

  assertLayoutBCounts(result, {
    candidate_count: 1,
    comparable_teaching_name_count: 1,
    f3_equals_teaching_name_count: 0,
    f4_equals_teaching_name_count: 1,
    f4_activity_count: 1,
    f3_in_confirmed_activity_set_count: 1,
    f4_in_confirmed_activity_set_count: 0,
    f3_matching_raw_fields: {},
  });
});

test("Layout B 诊断：不修改 raw row，也不产出任何 bundle", async () => {
  const rows = layoutBScenario();
  const before = JSON.stringify(rows);

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(JSON.stringify(rows), before, "⛔ 诊断不得修改 raw row");
  assert.equal(result.bundle, undefined, "⛔ 诊断不得产出 bundle");
  assert.equal(result.pages, undefined, "⛔ 诊断不得保留 pages");
  assert.equal(result.rows, undefined, "⛔ 诊断不得保留 rows");
});

test("Layout B 诊断：f3 命中字段名统计 —— 严格相等、只遍历字符串字段", async () => {
  const rows = [
    // f3 == courseName（字符串）→ 命中
    Object.assign(layoutBRow(`1-8周/${LOCATION}/示例课程/${ACTIVITY}`), {
      classNumber: "SYN-LB-FN-1",
      hasTeachingName: false,
    }),
    // f3 == yearTerm（字符串）→ 命中
    Object.assign(layoutBRow(`1-8周/${LOCATION}/2026-1/${ACTIVITY}`), {
      classNumber: "SYN-LB-FN-2",
      hasTeachingName: false,
    }),
    // f3 == score（字符串 "3"）→ 命中
    Object.assign(layoutBRow(`1-8周/${LOCATION}/3/${ACTIVITY}`), {
      classNumber: "SYN-LB-FN-3",
      hasTeachingName: false,
    }),
    // f3 == "90"：limitNumber 是**数字** 90 → 必须**不**命中（只遍历字符串字段）
    Object.assign(layoutBRow(`1-8周/${LOCATION}/90/${ACTIVITY}`), {
      classNumber: "SYN-LB-FN-4",
      hasTeachingName: false,
    }),
    // f3 什么都不命中 → 不产生条目
    Object.assign(layoutBRow(`1-8周/${LOCATION}/无任何命中/${ACTIVITY}`), {
      classNumber: "SYN-LB-FN-5",
      hasTeachingName: false,
    }),
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 5);
  assert.deepEqual({ ...result.f3_matching_raw_fields }, {
    courseName: 1,
    score: 1,
    yearTerm: 1,
  });
  // 字段名按码点排序 → 输出稳定
  assert.deepEqual(Object.keys(result.f3_matching_raw_fields), [
    "courseName",
    "score",
    "yearTerm",
  ]);
});

test("Layout B 诊断：f3 命中统计按候选累计，且多字段同时命中全部保留", async () => {
  const twoFields = Object.assign(rawRow(`1-8周/${LOCATION}/示例同名/${ACTIVITY}`), {
    classNumber: "SYN-LB-MULTI",
    examMode: "示例同名",
    examModeName: "示例同名",
  });

  const rows = [
    twoFields,
    Object.assign(layoutBRow(`1-8周/${LOCATION}/示例课程/${ACTIVITY}`), {
      classNumber: "SYN-LB-AGG-1",
      hasTeachingName: false,
    }),
    Object.assign(layoutBRow(`2-9周/${LOCATION}/示例课程/${ACTIVITY}`), {
      classNumber: "SYN-LB-AGG-2",
      hasTeachingName: false,
    }),
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 3);
  assert.deepEqual({ ...result.f3_matching_raw_fields }, {
    courseName: 2,
    examMode: 1,
    examModeName: 1,
  });
});

test("Layout B 诊断：f3 命中统计严格排除 courseNum / classNumber / 内部 ID / 排课字段", async () => {
  const idRow = Object.assign(rawRow(`1-8周/${LOCATION}/内部ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID",
    timePlaceId: "内部ID值",
  });
  const internalIdRow = Object.assign(rawRow(`1-8周/${LOCATION}/另一个ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID2",
    someInternalId: "另一个ID值",
  });
  const upperIdRow = Object.assign(rawRow(`1-8周/${LOCATION}/大写ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID3",
    internalID: "大写ID值",
  });
  const bareIdRow = Object.assign(rawRow(`1-8周/${LOCATION}/裸ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID4",
    id: "裸ID值",
  });
  // Architecture Review 清单里的内部 ID 字段
  const courseIdRow = Object.assign(rawRow(`1-8周/${LOCATION}/课程ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID5",
    courseId: "课程ID值",
  });
  const classUnderscoreIdRow = Object.assign(rawRow(`1-8周/${LOCATION}/下划线ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID6",
    class_ID: "下划线ID值",
  });
  const sumClassesIdRow = Object.assign(rawRow(`1-8周/${LOCATION}/汇总ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID7",
    sumClassesID: "汇总ID值",
  });
  const outLineIdRow = Object.assign(rawRow(`1-8周/${LOCATION}/大纲ID值/${ACTIVITY}`), {
    classNumber: "SYN-LB-ID8",
    outLineId: "大纲ID值",
  });

  const rows = [
    // f3 == courseNum → 排除
    Object.assign(layoutBRow(`1-8周/${LOCATION}/00000000/${ACTIVITY}`), {
      classNumber: "SYN-LB-EX-1",
      hasTeachingName: false,
    }),
    // f3 == classNumber → 排除
    Object.assign(layoutBRow(`1-8周/${LOCATION}/SYN-LB-EX-2/${ACTIVITY}`), {
      classNumber: "SYN-LB-EX-2",
      hasTeachingName: false,
    }),
    idRow,
    internalIdRow,
    upperIdRow,
    bareIdRow,
    courseIdRow,
    classUnderscoreIdRow,
    sumClassesIdRow,
    outLineIdRow,
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 10);
  assert.deepEqual({ ...result.f3_matching_raw_fields }, {}, "⛔ 被排除的字段名不得出现");
});

test("Layout B 诊断：内部 ID 判定必须有词法边界（valid / invalid / hybrid 必须命中）", async () => {
  // ⚠️ 本轮裁定：⛔ 不得用"任意以 id 两个字符结尾"的规则；
  //    `valid` / `invalid` / `hybrid` 只是普通单词 → 必须参与统计。
  const rows = [
    Object.assign(rawRow(`1-8周/${LOCATION}/普通词valid/${ACTIVITY}`), {
      classNumber: "SYN-LB-WORD-1",
      valid: "普通词valid",
    }),
    Object.assign(rawRow(`1-8周/${LOCATION}/普通词invalid/${ACTIVITY}`), {
      classNumber: "SYN-LB-WORD-2",
      invalid: "普通词invalid",
    }),
    Object.assign(rawRow(`1-8周/${LOCATION}/普通词hybrid/${ACTIVITY}`), {
      classNumber: "SYN-LB-WORD-3",
      hybrid: "普通词hybrid",
    }),
    // ⚠️ 按词法边界要求：全小写、无分隔符的 `courseid` **没有** ID 边界 ⇒ 不排除
    //    （若 Review 要覆盖该形态，需要给出明确规则）
    Object.assign(rawRow(`1-8周/${LOCATION}/无边界小写/${ACTIVITY}`), {
      classNumber: "SYN-LB-WORD-4",
      courseid: "无边界小写",
    }),
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 4);
  assert.deepEqual(
    { ...result.f3_matching_raw_fields },
    { courseid: 1, hybrid: 1, invalid: 1, valid: 1 },
    "⛔ 普通单词结尾的 id 不得被当成内部 ID 排除",
  );
});

test("Layout B 诊断：内部 ID 词法边界的正例（id / xxxId / xxxID / xxx_id 都要排除）", async () => {
  const rows = [
    Object.assign(rawRow(`1-8周/${LOCATION}/只有id/${ACTIVITY}`), {
      classNumber: "SYN-LB-BND-1",
      id: "只有id",
    }),
    Object.assign(rawRow(`1-8周/${LOCATION}/驼峰Id/${ACTIVITY}`), {
      classNumber: "SYN-LB-BND-2",
      lessonId: "驼峰Id",
    }),
    Object.assign(rawRow(`1-8周/${LOCATION}/全大写ID/${ACTIVITY}`), {
      classNumber: "SYN-LB-BND-3",
      lessonID: "全大写ID",
    }),
    Object.assign(rawRow(`1-8周/${LOCATION}/下划线id/${ACTIVITY}`), {
      classNumber: "SYN-LB-BND-4",
      lesson_id: "下划线id",
    }),
    Object.assign(rawRow(`1-8周/${LOCATION}/下划线上档ID/${ACTIVITY}`), {
      classNumber: "SYN-LB-BND-5",
      lesson_ID: "下划线上档ID",
    }),
    Object.assign(rawRow(`1-8周/${LOCATION}/整名ID大写/${ACTIVITY}`), {
      classNumber: "SYN-LB-BND-6",
      ID: "整名ID大写",
    }),
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 6);
  assert.deepEqual(
    { ...result.f3_matching_raw_fields },
    {},
    "⛔ 具有 ID 词法边界的字段名必须排除",
  );
});

test("Layout B 诊断：f3 命中统计只做严格相等（⛔ 无 substring / 无分词）", async () => {
  const rows = [
    // courseName 是 f3 的**超串** → 不命中
    Object.assign(layoutBRow(`1-8周/${LOCATION}/示例课程/${ACTIVITY}`), {
      classNumber: "SYN-LB-SUB-1",
      hasTeachingName: false,
      courseName: "示例课程（含后缀）",
    }),
    // courseName 是 f3 的**子串** → 不命中
    Object.assign(layoutBRow(`1-8周/${LOCATION}/示例课程/${ACTIVITY}`), {
      classNumber: "SYN-LB-SUB-2",
      hasTeachingName: false,
      courseName: "示例",
    }),
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 2);
  assert.deepEqual({ ...result.f3_matching_raw_fields }, {});
});

test("Layout B 诊断：f3 命中统计不泄露取值，且不污染对象原型", async () => {
  const protoRow = Object.assign(rawRow(`1-8周/${LOCATION}/原型键值/${ACTIVITY}`), {
    classNumber: "SYN-LB-PROTO",
  });
  Object.defineProperty(protoRow, "__proto__", {
    value: "原型键值",
    enumerable: true,
    configurable: true,
    writable: true,
  });

  const { result } = await runLayoutBDiagnostic([protoRow, minimalProviderRow()]);

  assert.equal(result.candidate_count, 1);
  assert.deepEqual(Object.keys(result.f3_matching_raw_fields), ["__proto__"]);
  assert.equal(result.f3_matching_raw_fields["__proto__"], 1);

  // ⛔ 不得污染原型：结果对象的原型仍是 Object.prototype
  assert.equal(Object.getPrototypeOf(result.f3_matching_raw_fields), Object.prototype);
  assert.equal({}.原型键值, undefined);
  assert.equal(JSON.parse(JSON.stringify(result.f3_matching_raw_fields))["__proto__"], 1);
  assert.ok(!JSON.stringify(result).includes("原型键值"), "⛔ 取值不得出现在输出中");
});

test("Layout B 诊断：f3 命中统计 —— 单个字段 10/10", async () => {
  const rows = [
    ...Array.from({ length: 10 }, (_, index) =>
      layoutBRow(`1-8周/${LOCATION}/示例课程/${ACTIVITY}`, {
        classNumber: `SYN-LB-TEN-${index}`,
        hasTeachingName: false,
      }),
    ),
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 10);
  assert.deepEqual({ ...result.f3_matching_raw_fields }, { courseName: 10 });
});

test("Layout B 诊断：f3 命中统计只看 f3（⛔ f4 不参与，候选自身不污染证据）", async () => {
  const rows = [
    // 该行 f4 == examMode 的取值，但 f3（= TEACHER）不命中任何字段 → 不得产生条目
    Object.assign(rawRow(`1-8周/${LOCATION}/${TEACHER}/示例环节丁`), {
      classNumber: "SYN-LB-F4ONLY",
      examMode: "示例环节丁",
    }),
    minimalProviderRow(),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 1);
  assert.deepEqual(
    { ...result.f3_matching_raw_fields },
    {},
    "⛔ 只统计 f3；f4 / 候选自身的其它字段不得产生命中",
  );
});

test("Layout B 诊断：f3 命中统计跨页累计（页序不影响）", async () => {
  const filler = Array.from({ length: 199 }, (_, index) =>
    Object.assign(rawRow(`1-8周/星期五/第5-6节/${ACTIVITY}`), {
      classNumber: `SYN-FILL-${String(index + 1).padStart(4, "0")}`,
    }),
  );

  const rows = [
    // 第 1 页
    layoutBRow(`1-8周/${LOCATION}/示例课程/${ACTIVITY}`, {
      classNumber: "SYN-LB-HIST-P1",
      hasTeachingName: false,
    }),
    ...filler,
    // 第 2 页
    layoutBRow(`2-9周/${LOCATION}/示例课程/${ACTIVITY}`, {
      classNumber: "SYN-LB-HIST-P2",
      hasTeachingName: false,
    }),
    minimalProviderRow(),
  ];

  const { result, calls } = await runLayoutBDiagnostic(rows, { maxPages: 2 });

  assert.deepEqual(
    calls.map((call) => call.pageNo),
    [1, 2],
    "⛔ 不得跳页",
  );
  assert.equal(result.candidate_count, 2);
  assert.deepEqual({ ...result.f3_matching_raw_fields }, { courseName: 2 });
});

test("Layout B 诊断：f3 命中统计的返回值与序列化中不出现任何输入取值", async () => {
  const values = {
    courseName: "示例唯一课程名",
    yearTerm: "2027-9",
    score: "4.5",
    examMode: "示例唯一考核方式",
    openingUnitName: "示例唯一开课单位",
  };

  const row = Object.assign(
    rawRow(`1-8周/${LOCATION}/示例唯一课程名/${ACTIVITY}`),
    Object.assign({ classNumber: "SYN-LB-LEAK" }, values),
  );

  const { result } = await runLayoutBDiagnostic([row, minimalProviderRow()]);

  assert.deepEqual({ ...result.f3_matching_raw_fields }, { courseName: 1 });

  const serialized = JSON.stringify(result);

  // ⛔ 任何**取值**都不得出现（字段名是映射的键，按本轮裁定允许输出）
  for (const value of Object.values(values)) {
    assert.ok(!serialized.includes(value), `⛔ 取值不得出现在输出中：${value}`);
  }
  for (const forbidden of [TEACHER, ACTIVITY, LOCATION, CAMPUS, "SYN-LB", "示例环节"]) {
    assert.ok(!serialized.includes(forbidden), `⛔ 输出不得含：${forbidden}`);
  }
  assert.ok(serialized.includes("courseName"), "字段名本身按裁定允许出现在映射键里");
});

test("Layout B 诊断：没有 teachingName 时可比计数不推进（不猜）", async () => {
  const { result } = await runLayoutBDiagnostic([
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      hasTeachingName: false,
    }),
    minimalProviderRow(),
  ]);

  assertLayoutBCounts(result, {
    candidate_count: 1,
    comparable_teaching_name_count: 0,
    f3_equals_teaching_name_count: 0,
    f4_equals_teaching_name_count: 0,
    f4_activity_count: 1,
    f3_in_confirmed_activity_set_count: 0,
    f4_in_confirmed_activity_set_count: 1,
    f3_matching_raw_fields: {},
  });
});

test("Layout B 诊断：teachingName 属性存在但非字符串 → 可比较但不等", async () => {
  const { result } = await runLayoutBDiagnostic([
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/${TEACHER}`, { teachingName: null }),
    minimalProviderRow(),
  ]);

  assertLayoutBCounts(result, {
    candidate_count: 1,
    comparable_teaching_name_count: 1,
    f3_equals_teaching_name_count: 0,
    f4_equals_teaching_name_count: 0,
    f4_activity_count: 1,
    f3_in_confirmed_activity_set_count: 0,
    f4_in_confirmed_activity_set_count: 0,
    f3_matching_raw_fields: {},
  });
});

test("Layout B 诊断：四种已批准 weeks 形态都计入候选", async () => {
  const { result } = await runLayoutBDiagnostic([
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/${ACTIVITY}`),
    layoutBRow(`1-8单周/${LOCATION}/${TEACHER}/${ACTIVITY}`),
    layoutBRow(`3-4双周/${LOCATION}/${TEACHER}/${ACTIVITY}`),
    layoutBRow(`1-8周校外/${LOCATION}/${TEACHER}/${ACTIVITY}`),
    layoutBRow(`1-8周校内(户外)/${LOCATION}/${TEACHER}/${ACTIVITY}`),
    minimalProviderRow(),
  ]);

  assert.equal(result.candidate_count, 5);
  assert.equal(result.f4_activity_count, 5);
});

test("Layout B 诊断：未批准 weeks（线上 / 前缀）不计入候选", async () => {
  const { result } = await runLayoutBDiagnostic([
    layoutBRow(`1-8周线上/${LOCATION}/${TEACHER}/${ACTIVITY}`),
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/${ACTIVITY}`, { classNumber: "X" }),
    minimalProviderRow(),
  ]);

  // 第一条不是已批准 weeks；第二条是 → 只应有 1 个候选
  assert.equal(result.candidate_count, 1);
});

test("Layout B 诊断：f4 非空规则只作语法检查（⛔ 非角色证据）", async () => {
  const { result } = await runLayoutBDiagnostic([
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/   `),
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/`, { classNumber: "SYN-LB-EMPTY" }),
    minimalProviderRow(),
  ]);

  assert.equal(result.candidate_count, 2);
  assert.equal(result.f4_activity_count, 0, "⛔ 空白 / 空 f4 不算 activity");
  assert.equal(result.f4_in_confirmed_activity_set_count, 0);
});

test("Layout B 诊断：七种已确认 layout 的 activity 槽位都进入集合", async () => {
  const rows = [
    ...confirmedProviderRows(),
    // 每个 provider 的 activity token 各作为一个候选的 f3
    ...PROVIDER_ACTIVITY.map((token, index) =>
      layoutBRow(`1-8周/${LOCATION}/${token}/${ACTIVITY}`, {
        classNumber: `SYN-LB-F3-${index}`,
        hasTeachingName: false,
      }),
    ),
    // 再各作为一个候选的 f4
    ...PROVIDER_ACTIVITY.map((token, index) =>
      layoutBRow(`2-9周/${LOCATION}/${TEACHER}/${token}`, {
        classNumber: `SYN-LB-F4-${index}`,
        hasTeachingName: false,
      }),
    ),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, 14);
  assert.equal(
    result.f3_in_confirmed_activity_set_count,
    PROVIDER_ACTIVITY.length,
    "七种已确认 layout 的 activity 槽位都必须进入集合",
  );
  assert.equal(result.f4_in_confirmed_activity_set_count, PROVIDER_ACTIVITY.length);
});

test("Layout B 诊断：候选自身**不会**污染已确认集合（非循环）", async () => {
  // 该 token 只出现在"未被确认的 4 字段 layout"里 → 集合里不应有它
  const { result } = await runLayoutBDiagnostic([
    layoutBRow(`1-8周/${LOCATION}/${PROVIDER_ACTIVITY[0]}/${PROVIDER_ACTIVITY[1]}`, {
      classNumber: "SYN-LB-CIRCULAR",
      hasTeachingName: false,
    }),
    minimalProviderRow(),
  ]);

  assert.equal(result.candidate_count, 1);
  assert.equal(result.f3_in_confirmed_activity_set_count, 0, "⛔ 候选自身不得进入集合");
  assert.equal(result.f4_in_confirmed_activity_set_count, 0, "⛔ 候选自身不得进入集合");
});

test("Layout B 诊断：顺序无关（候选在前、provider 在后仍能命中）", async () => {
  const filler = Array.from({ length: 200 }, (_, index) =>
    Object.assign(rawRow(`1-8周/星期五/第5-6节/${ACTIVITY}`), {
      classNumber: `SYN-FILL-${String(index + 1).padStart(4, "0")}`,
    }),
  );

  // 第 1 页：候选（provider 还没出现）；第 2 页：provider
  const rows = [
    layoutBRow(`1-8周/${LOCATION}/${PROVIDER_ACTIVITY[0]}/${ACTIVITY}`, {
      classNumber: "SYN-LB-FIRST-PAGE",
      hasTeachingName: false,
    }),
    ...filler.slice(0, 199),
    providerRow(`1-17周/${PROVIDER_ACTIVITY[0]}`, "SYN-PRV-LATE"),
  ];

  const { result, calls } = await runLayoutBDiagnostic(rows, { maxPages: 2 });

  assert.equal(calls.length, 2);
  assert.equal(
    result.f3_in_confirmed_activity_set_count,
    1,
    "⛔ 不得因为 provider 出现在候选**之后**就漏判",
  );
});

test("Layout B 诊断：未确认 layout 的槽位**不**进入集合", async () => {
  const excluded = [
    // 2 字段 parity（Python non-concrete 只认 plain / 已确认 qualifier）
    `3-3双周/${EXCLUDED_ACTIVITY[0]}`,
    // weeks 数值非法
    `0-3周/${EXCLUDED_ACTIVITY[1]}`,
    `5-3周/${EXCLUDED_ACTIVITY[2]}`,
    // 2 字段 parity（区间合法但形状未确认）
    `1-8单周/${EXCLUDED_ACTIVITY[3]}`,
    // weekday 不在白名单
    `1-8周/星期天/第5-6节/${EXCLUDED_ACTIVITY[4]}`,
    // sections suffix 未批准
    `1-8周/星期五/第5-6节校/${EXCLUDED_ACTIVITY[5]}`,
    // 5 字段 layout A 的 REDACTED 被"前缀通配"
    `1-8周/星期五/${LOCATION}/REDACTEDX/${EXCLUDED_ACTIVITY[6]}`,
    // 5 字段 f4 二义（两段 '-')
    `1-8周/星期五/第5-6节/示例园区-2108/${EXCLUDED_ACTIVITY[7]}`,
    // layout A 的 weeks 是"过滤后为空"的 parity 区间（Python `expand_weeks` 拒绝）
    `3-3双周/星期五/${LOCATION}/REDACTED/${EXCLUDED_ACTIVITY[8]}`,
  ];

  const rows = [
    minimalProviderRow(),
    ...excluded.map((segment, index) =>
      Object.assign(rawRow(segment), { classNumber: `SYN-EXC-${index}` }),
    ),
    ...EXCLUDED_ACTIVITY.map((token, index) =>
      layoutBRow(`1-8周/${LOCATION}/${token}/${ACTIVITY}`, {
        classNumber: `SYN-LB-EXC-${index}`,
        hasTeachingName: false,
      }),
    ),
  ];

  const { result } = await runLayoutBDiagnostic(rows);

  assert.equal(result.candidate_count, EXCLUDED_ACTIVITY.length);
  assert.equal(
    result.f3_in_confirmed_activity_set_count,
    0,
    "⛔ 未确认 layout 的槽位取值不得进入集合",
  );
});

test("Layout B 诊断：集合为空 → fail closed（不返回会被误读的计数）", async () => {
  // 只有候选、没有任何已确认 layout → 成员判定会退化为恒假
  const rows = [
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-NOSET",
      teachingName: TEACHER,
    }),
  ];

  await assert.rejects(
    () => runLayoutBDiagnostic(rows),
    /已确认 layout 的 activity 固定槽位取值/,
  );
});

test("Layout B 诊断：多页 → 跨页累计，且第二页仍受全局 pacing", async () => {
  const filler = Array.from({ length: 200 }, (_, index) =>
    Object.assign(rawRow(`1-8周/星期五/第5-6节/${ACTIVITY}`), {
      classNumber: `SYN-FILL-${String(index + 1).padStart(4, "0")}`,
    }),
  );
  const rows = [
    ...filler,
    layoutBRow(`1-8周/${LOCATION}/${TEACHER}/${ACTIVITY}`, {
      classNumber: "SYN-LB-PAGE2",
      teachingName: TEACHER,
    }),
  ];

  const { result, calls, timers } = await runLayoutBDiagnostic(rows, { maxPages: 2 });

  assert.equal(calls.length, 2, "应当恰好请求 2 页");
  assert.deepEqual(
    calls.map((call) => call.pageNo),
    [1, 2],
    "⛔ 不得跳页",
  );
  assertLayoutBCounts(result, {
    candidate_count: 1,
    comparable_teaching_name_count: 1,
    // 本候选的 f3 == TEACHER == 本行 teachingName
    f3_equals_teaching_name_count: 1,
    f4_equals_teaching_name_count: 0,
    f4_activity_count: 1,
    f3_in_confirmed_activity_set_count: 0,
    f4_in_confirmed_activity_set_count: 1,
    // 该候选的 f3 == 本行 teachingName
    f3_matching_raw_fields: { teachingName: 1 },
  });

  assert.ok(timers.length >= 1, "第二个请求必须先等待");
  for (const ms of timers) {
    assert.ok(ms >= 30000, `⛔ 诊断不得绕过 pacing 下限：${ms}`);
  }
});

test("Layout B 诊断：未批准参数在任何请求之前被拒绝", async () => {
  const { collector, calls } = loadLayoutBCollector(layoutBScenario());

  for (const bad of [{ pageSize: 50 }, { delayMs: 1000 }, { firstPageNo: 2 }, { scope: "x" }]) {
    await assert.rejects(
      () =>
        collector.diagnoseLayoutBCandidates(
          Object.assign(
            { semester: SEMESTER, openingSchoolNumber: LAYOUT_B_CAMPUS, maxPages: 1 },
            bad,
          ),
        ),
      /Layout B 诊断只接受/,
    );
  }

  assert.equal(calls.length, 0, "⛔ 参数校验必须发生在任何取页调用之前");
});

test("Layout B 诊断：缺少 semester 被拒绝，且不发出请求", async () => {
  const { collector, calls } = loadLayoutBCollector(layoutBScenario());

  await assert.rejects(
    () => collector.diagnoseLayoutBCandidates({ openingSchoolNumber: LAYOUT_B_CAMPUS }),
    /semester/,
  );

  assert.equal(calls.length, 0);
});

test("Layout B 诊断：maxPages 超过 smoke 上限时先确认；取消 → 不请求也不返回伪计数", async () => {
  const cancelled = loadLayoutBCollector(layoutBScenario(), { confirmResult: false });

  await assert.rejects(
    () =>
      cancelled.collector.diagnoseLayoutBCandidates({
        semester: SEMESTER,
        openingSchoolNumber: LAYOUT_B_CAMPUS,
        maxPages: 3,
      }),
    /取消/,
  );

  assert.equal(cancelled.calls.length, 0, "⛔ 取消后不得发出任何请求");
  assert.equal(cancelled.confirms.length, 1);

  const accepted = loadLayoutBCollector(layoutBScenario(), { confirmResult: true });
  const result = await accepted.collector.diagnoseLayoutBCandidates({
    semester: SEMESTER,
    openingSchoolNumber: LAYOUT_B_CAMPUS,
    maxPages: 3,
  });

  assert.equal(accepted.confirms.length, 1);
  assert.equal(result.candidate_count, 4);
});

test("Layout B 诊断：maxPages 在 smoke 上限内不弹确认框", async () => {
  const { confirms, result } = await runLayoutBDiagnostic(layoutBScenario(), { maxPages: 2 });

  assert.equal(confirms.length, 0);
  assert.equal(result.candidate_count, 4);
});

test("Layout B 诊断：data.total 中途变化 → 整体 fail closed", async () => {
  const rows = layoutBScenario();
  const calls = [];
  let reads = 0;

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
    setTimeout: (callback) => {
      queueMicrotask(callback);
      return 1;
    },
    fetch: async (url, init) => {
      const body = JSON.parse(init.body);
      calls.push(body.pageNo);
      reads += 1;
      // 第 1 页：只回 5 行但 total=9（未取满 → 继续下一页）；
      // 第 2 页：total 变成 10 → 诊断期间数据集合变化 → 整体 fail closed。
      return fakeResponse({
        code: 200,
        data: { total: reads === 1 ? rows.length : rows.length + 1, rows: rows.slice(0, 5) },
      });
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

  await assert.rejects(
    () =>
      sandbox.window.XuehangSysuCollector.diagnoseLayoutBCandidates({
        semester: SEMESTER,
        openingSchoolNumber: LAYOUT_B_CAMPUS,
        maxPages: 2,
      }),
    /data\.total/,
  );

  assert.deepEqual(calls, [1, 2], "⛔ 失败发生在第 2 页，且不得重试 / 跳页");
});



// ---------------------------------------------------------------------------
// 分段式 f3 字段来源诊断（Architecture Review 方案 D）
//
// 契约：**恰好六个**输出（⛔ 不含 activity-membership 计数）；
// checkpoint 零敏感（只有数值计数 + 字段名 → 计数 + 安全分页元数据）。
// ---------------------------------------------------------------------------

const FS_CAMPUS = "SYN-CAMPUS-FS";
const FS_PAGE_SIZE = 200;
const FS_LAST_PAGE_ROWS = 71;
const FS_PAGE_COUNT = 6;
const FS_TOTAL = (FS_PAGE_COUNT - 1) * FS_PAGE_SIZE + FS_LAST_PAGE_ROWS; // 1071
const FS_RESULT_KEYS = [
  "candidate_count",
  "comparable_teaching_name_count",
  "f3_equals_teaching_name_count",
  "f4_equals_teaching_name_count",
  "f4_activity_count",
  "f3_matching_raw_fields",
];

/** 分段诊断的合成 row（默认是 4 字段 concrete provider）。 */
function fsProviderRow(activity, classNumber) {
  return Object.assign(rawRow(`1-8周/星期五/第5-6节/${activity}`), {
    classNumber: classNumber,
  });
}

/** Layout B 候选 row。 */
function fsCandidateRow(third, fourth, options = {}) {
  const row = Object.assign(
    rawRow(`1-8周/${LOCATION}/${third}/${fourth}`),
    { classNumber: options.classNumber || "SYN-FS-CAND" },
  );
  if (options.hasTeachingName !== false) {
    row.teachingName = options.teachingName === undefined ? TEACHER : options.teachingName;
  }
  if (options.extraFields) {
    Object.assign(row, options.extraFields);
  }
  return row;
}

/** 构造 6 页语料；`injections` 的键形如 `"1-0"` = 第 1 页第 0 行。 */
function fsCorpus(injections = {}) {
  const pages = [];
  for (let pageNo = 1; pageNo <= FS_PAGE_COUNT; pageNo += 1) {
    const count = pageNo === FS_PAGE_COUNT ? FS_LAST_PAGE_ROWS : FS_PAGE_SIZE;
    const rows = [];
    for (let index = 0; index < count; index += 1) {
      rows.push(
        fsProviderRow(ACTIVITY, `SYN-FS-${pageNo}-${String(index + 1).padStart(3, "0")}`),
      );
    }
    pages.push(rows);
  }
  for (const [key, row] of Object.entries(injections)) {
    const [pageNo, index] = key.split("-").map(Number);
    pages[pageNo - 1][index] = row;
  }
  return pages;
}

function loadFieldSourceCollector(pages, options = {}) {
  const calls = [];
  const confirms = [];
  const timers = [];
  const totals = options.totals || {};
  const statusForPage = options.statusForPage || (() => 0);

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
    Set,
    Map,
    clearTimeout: () => {},
    setTimeout: (callback, ms) => {
      timers.push(ms);
      queueMicrotask(callback);
      return timers.length;
    },
    fetch: async (url, init) => {
      const body = JSON.parse(init.body);
      calls.push(body.pageNo);

      const forcedStatus = statusForPage(body.pageNo);
      if (forcedStatus !== 0) {
        return {
          status: forcedStatus,
          ok: false,
          headers: { get: () => "application/json;charset=UTF-8" },
          json: async () => ({ code: 50015000, message: "系统异常" }),
        };
      }

      const rows = pages[body.pageNo - 1] || [];
      const total = totals[body.pageNo] === undefined ? FS_TOTAL : totals[body.pageNo];
      return fakeResponse({ code: 200, data: { total, rows } });
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

  return { collector: sandbox.window.XuehangSysuCollector, calls, confirms, timers };
}

function newFieldSourceHarness(pages, options = {}) {
  const harness = loadFieldSourceCollector(pages, options);
  return Object.assign(harness, {
    part: (partOptions) =>
      harness.collector.diagnoseLayoutBFieldSourcePart(
        Object.assign(
          {
            semester: SEMESTER,
            openingSchoolNumber: FS_CAMPUS,
          },
          partOptions,
        ),
      ),
    finalize: (state) => harness.collector.finalizeLayoutBFieldSource(state),
  });
}

function assertFieldSourceResult(result, expected) {
  assert.deepEqual({ ...result }, expected);
}

/** 跨 realm 安全：把 VM 生成的对象/数组摊平成宿主 realm 的普通值。 */
function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

test("分段诊断：1..5 + 6 == one-shot 1..6（六个字段完全相等）", async () => {
  const pages = fsCorpus({
    "1-0": fsCandidateRow(TEACHER, ACTIVITY, { classNumber: "SYN-FS-A" }),
    "6-0": fsCandidateRow(LAYOUT_B_TEACHER_OTHER, ACTIVITY, {
      classNumber: "SYN-FS-B",
      teachingName: LAYOUT_B_TEACHER_OTHER,
    }),
  });

  const oneShot = newFieldSourceHarness(pages);
  const oneShotState = await oneShot.part({ startPage: 1, endPage: 6 });
  const oneShotResult = oneShot.finalize(oneShotState);

  const segmented = newFieldSourceHarness(pages);
  const part1 = await segmented.part({ startPage: 1, endPage: 5 });
  const part2 = await segmented.part({ startPage: 6, endPage: 6, previousState: part1 });
  const merged = segmented.finalize(part2);

  assert.deepEqual(plain(merged), plain(oneShotResult));
  assert.equal(oneShotResult.candidate_count, 2);
  assert.deepEqual(segmented.calls, [1, 2, 3, 4, 5, 6]);
});

test("分段诊断：1..3 + 4..6 与 逐页 1+2+3+4+5+6 都与 one-shot 相等", async () => {
  const pages = fsCorpus({
    "2-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-C" }),
    "5-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-D" }),
  });

  const baseline = newFieldSourceHarness(pages);
  const expected = baseline.finalize(await baseline.part({ startPage: 1, endPage: 6 }));

  const split3 = newFieldSourceHarness(pages);
  const a = await split3.part({ startPage: 1, endPage: 3 });
  const b = await split3.part({ startPage: 4, endPage: 6, previousState: a });
  assert.deepEqual(plain(split3.finalize(b)), plain(expected));

  const perPage = newFieldSourceHarness(pages);
  let state = null;
  for (let pageNo = 1; pageNo <= 6; pageNo += 1) {
    state = await perPage.part({
      startPage: pageNo,
      endPage: pageNo,
      previousState: state === null ? undefined : state,
    });
  }
  assert.deepEqual(plain(perPage.finalize(state)), plain(expected));
  assert.deepEqual(expected.f3_matching_raw_fields, { courseName: 2 });
});

test("分段诊断：排除字段不参与命中统计（courseNum / 内部 ID）", async () => {
  const pages = fsCorpus({
    // f3 == courseNum → 排除
    "1-0": Object.assign(fsCandidateRow("00000000", ACTIVITY), {
      classNumber: "SYN-FS-EX-1",
    }),
    // f3 == 内部 ID 字段（timePlaceId）→ 排除
    "2-0": Object.assign(rawRow(`1-8周/${LOCATION}/内部ID值/${ACTIVITY}`), {
      classNumber: "SYN-FS-EX-2",
      timePlaceId: "内部ID值",
    }),
  });

  const harness = newFieldSourceHarness(pages);
  const state = await harness.part({ startPage: 1, endPage: 6 });
  const result = harness.finalize(state);

  assert.equal(result.candidate_count, 2);
  assert.deepEqual(result.f3_matching_raw_fields, {}, "⛔ 被排除的字段名不得出现");
});

test("分段诊断：命中统计只做严格相等（⛔ 无 substring / 无分词）", async () => {
  const pages = fsCorpus({
    // courseName 是 f3 的**超串** → 不命中
    "1-0": fsCandidateRow("示例课程", ACTIVITY, {
      classNumber: "SYN-FS-SUB-1",
      extraFields: { courseName: "示例课程（含后缀）" },
    }),
    // courseName 是 f3 的**子串** → 不命中
    "2-0": fsCandidateRow("示例课程", ACTIVITY, {
      classNumber: "SYN-FS-SUB-2",
      extraFields: { courseName: "示例" },
    }),
  });

  const harness = newFieldSourceHarness(pages);
  const state = await harness.part({ startPage: 1, endPage: 6 });

  assert.deepEqual(harness.finalize(state).f3_matching_raw_fields, {});
});

test("分段诊断：无序合并（6 + 1..5 与 4..6 + 1..3）同样成立", async () => {
  const pages = fsCorpus({
    "1-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-E" }),
    "4-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-F" }),
  });

  const baseline = newFieldSourceHarness(pages);
  const expected = baseline.finalize(await baseline.part({ startPage: 1, endPage: 6 }));

  const late = newFieldSourceHarness(pages);
  const page6 = await late.part({ startPage: 6, endPage: 6 });
  const first5 = await late.part({ startPage: 1, endPage: 5, previousState: page6 });
  assert.deepEqual(plain(late.finalize(first5)), plain(expected));

  const middle = newFieldSourceHarness(pages);
  const tail = await middle.part({ startPage: 4, endPage: 6 });
  const head = await middle.part({ startPage: 1, endPage: 3, previousState: tail });
  assert.deepEqual(plain(middle.finalize(head)), plain(expected));
});

test("分段诊断：candidate 与 fieldName 命中跨页累计", async () => {
  const pages = fsCorpus({
    "1-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-G" }),
    "6-0": fsCandidateRow("示例课程", ACTIVITY, {
      classNumber: "SYN-FS-H",
      hasTeachingName: false,
    }),
  });

  const harness = newFieldSourceHarness(pages);
  const part1 = await harness.part({ startPage: 1, endPage: 5 });
  assert.equal(part1.candidate_count, 1);
  assert.deepEqual(part1.f3_matching_raw_fields, { courseName: 1 });

  const part2 = await harness.part({ startPage: 6, endPage: 6, previousState: part1 });
  const result = harness.finalize(part2);

  assert.equal(result.candidate_count, 2, "candidate_count 必须跨 part 累计");
  assert.equal(result.comparable_teaching_name_count, 1, "comparable 必须跨 part 累计");
  assert.deepEqual(result.f3_matching_raw_fields, { courseName: 2 });
});

test("分段诊断：多字段同时命中 / 部分命中 / 空 mapping", async () => {
  const pages = fsCorpus({
    "1-0": fsCandidateRow("示例同名", ACTIVITY, {
      classNumber: "SYN-FS-I",
      extraFields: { examMode: "示例同名", examModeName: "示例同名" },
    }),
    "2-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-J" }),
    "3-0": fsCandidateRow("无任何命中", ACTIVITY, { classNumber: "SYN-FS-K" }),
  });

  const harness = newFieldSourceHarness(pages);
  const state = await harness.part({ startPage: 1, endPage: 6 });
  const result = harness.finalize(state);

  assert.equal(result.candidate_count, 3);
  assert.deepEqual(result.f3_matching_raw_fields, {
    courseName: 1,
    examMode: 1,
    examModeName: 1,
  });

  const emptyHarness = newFieldSourceHarness(fsCorpus());
  const emptyState = await emptyHarness.part({ startPage: 1, endPage: 6 });
  assert.deepEqual(emptyHarness.finalize(emptyState).f3_matching_raw_fields, {});
});

test("分段诊断：契约恰好六个字段（⛔ 无 activity-membership 计数 / 无占位）", async () => {
  const harness = newFieldSourceHarness(fsCorpus());
  const state = await harness.part({ startPage: 1, endPage: 6 });
  const result = harness.finalize(state);

  assert.deepEqual(Object.keys(result).sort(), [...FS_RESULT_KEYS].sort());
  assert.ok(!("f3_in_confirmed_activity_set_count" in result));
  assert.ok(!("f4_in_confirmed_activity_set_count" in result));
  for (const [key, value] of Object.entries(result)) {
    if (key === "f3_matching_raw_fields") {
      continue;
    }
    assert.equal(typeof value, "number", `${key} 必须是数字计数`);
  }
});

test("分段诊断：与完整诊断的六个重叠字段完全一致（防口径漂移）", async () => {
  const pages = fsCorpus({
    "1-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-L" }),
    "4-0": fsCandidateRow(TEACHER, "示例环节乙", {
      classNumber: "SYN-FS-M",
      teachingName: TEACHER,
      extraFields: { examMode: "示例环节乙" },
    }),
  });

  const harness = newFieldSourceHarness(pages);
  const state = await harness.part({ startPage: 1, endPage: 6 });
  const fieldSource = harness.finalize(state);

  const full = newFieldSourceHarness(pages);
  const fullResult = await full.collector.diagnoseLayoutBCandidates({
    semester: SEMESTER,
    openingSchoolNumber: FS_CAMPUS,
    maxPages: 6,
  });

  for (const key of FS_RESULT_KEYS) {
    assert.deepEqual(fieldSource[key], fullResult[key], `六个重叠字段必须一致：${key}`);
  }
});

test("分段诊断：重复页 / 重叠页 reject（⛔ 不静默覆盖）", async () => {
  const harness = newFieldSourceHarness(fsCorpus());
  const part1 = await harness.part({ startPage: 1, endPage: 5 });

  await assert.rejects(
    () => harness.part({ startPage: 5, endPage: 6, previousState: part1 }),
    /重复 \/ 重叠页/,
  );
  await assert.rejects(
    () => harness.part({ startPage: 3, endPage: 4, previousState: part1 }),
    /重复 \/ 重叠页/,
  );
  assert.deepEqual(harness.calls, [1, 2, 3, 4, 5], "⛔ 被拒绝的 part 不得发出请求");
});

test("分段诊断：缺页 / 未取满 → finalize reject", async () => {
  const harness = newFieldSourceHarness(fsCorpus());
  const part1 = await harness.part({ startPage: 1, endPage: 5 });

  assert.throws(() => harness.finalize(part1), /只覆盖 1000 \/ 1071 行/);

  // 有洞：跳过第 3 页（伪造 state）
  const holed = JSON.parse(JSON.stringify(part1));
  holed.processed_pages = holed.processed_pages.filter((entry) => entry.page_no !== 3);
  holed.expected_total = 900;
  assert.throws(() => harness.finalize(holed), /缺少第 3 页/);

  // 篡改 expected_total 变小 → 页数与 total 不自洽 → reject
  const shrunk = JSON.parse(JSON.stringify(part1));
  shrunk.expected_total = 800;
  assert.throws(() => harness.finalize(shrunk), /页数与 expected_total 不自洽/);
});

test("分段诊断：total 漂移 reject", async () => {
  const harness = newFieldSourceHarness(fsCorpus(), {
    totals: { 6: FS_TOTAL + 1 },
  });

  await assert.rejects(
    () => harness.part({ startPage: 1, endPage: 6 }),
    /expected_total 不一致/,
  );
});

test("分段诊断：semester / shard / page_size 绑定不一致 reject", async () => {
  const harness = newFieldSourceHarness(fsCorpus());
  const part1 = await harness.part({ startPage: 1, endPage: 5 });

  await assert.rejects(
    () =>
      harness.part({
        semester: "2026-2",
        startPage: 6,
        endPage: 6,
        previousState: part1,
      }),
    /semester 与本次 semester 不一致/,
  );
  await assert.rejects(
    () =>
      harness.part({
        openingSchoolNumber: "5062202",
        startPage: 6,
        endPage: 6,
        previousState: part1,
      }),
    /shard 与本次 openingSchoolNumber 不一致/,
  );

  const wrongSize = JSON.parse(JSON.stringify(part1));
  wrongSize.page_size = 50;
  await assert.rejects(
    () => harness.part({ startPage: 6, endPage: 6, previousState: wrongSize }),
    /page_size 与已验证口径不一致/,
  );
});

test("分段诊断：checkpoint 篡改 reject（版本 / 键集合 / 计数 / 映射 / 页码元素）", async () => {
  const harness = newFieldSourceHarness(fsCorpus());
  const part1 = await harness.part({ startPage: 1, endPage: 5 });
  const clone = () => JSON.parse(JSON.stringify(part1));

  const bumped = clone();
  bumped.version = 2;
  assert.throws(() => harness.finalize(bumped), /version 不受支持/);

  const extra = clone();
  extra.raw_rows = [];
  assert.throws(() => harness.finalize(extra), /键数量与契约不一致|键集合与契约不一致/);

  const negative = clone();
  negative.candidate_count = -1;
  assert.throws(() => harness.finalize(negative), /candidate_count 必须是非负整数/);

  const zeroCount = clone();
  zeroCount.f3_matching_raw_fields = { courseName: 0 };
  assert.throws(() => harness.finalize(zeroCount), /计数必须是 >= 1 的整数/);

  const badPage = clone();
  badPage.processed_pages = [{ page_no: 1, row_count: 200, extra: 1 }];
  assert.throws(() => harness.finalize(badPage), /键数量不符|只允许 page_no \/ row_count/);

  const duplicate = clone();
  duplicate.processed_pages = [
    { page_no: 1, row_count: 200 },
    { page_no: 1, row_count: 200 },
  ];
  assert.throws(() => harness.finalize(duplicate), /出现重复页/);
});

test("分段诊断：checkpoint 可 JSON 往返（用户复制/粘贴流程）", async () => {
  const pages = fsCorpus({
    "1-0": fsCandidateRow("示例课程", ACTIVITY, { classNumber: "SYN-FS-N" }),
  });

  const harness = newFieldSourceHarness(pages);
  const part1 = await harness.part({ startPage: 1, endPage: 5 });

  const pasted = JSON.parse(JSON.stringify(part1));
  assert.equal(JSON.stringify(pasted), JSON.stringify(part1));

  const part2 = await harness.part({ startPage: 6, endPage: 6, previousState: pasted });
  const result = harness.finalize(JSON.parse(JSON.stringify(part2)));

  assert.equal(result.candidate_count, 1);
  assert.deepEqual(result.f3_matching_raw_fields, { courseName: 1 });
});

test("分段诊断：checkpoint 与序列化结果都不含任何 synthetic secret", async () => {
  const secrets = {
    teacher: "SECRET-TEACHER-ALPHA",
    activity: "SECRET-ACTIVITY-BETA",
    f3: "SECRET-F3-GAMMA",
    f4: "SECRET-F4-DELTA",
    courseId: "SECRET-COURSE-ID",
    classId: "SECRET-CLASS-ID",
  };

  const pages = fsCorpus({
    "1-0": fsCandidateRow(secrets.f3, secrets.f4, {
      classNumber: secrets.classId,
      teachingName: secrets.teacher,
      extraFields: { courseId: secrets.courseId },
    }),
    "1-1": fsProviderRow(secrets.activity, "SYN-FS-SECRET-PROVIDER"),
  });

  const harness = newFieldSourceHarness(pages);
  const part1 = await harness.part({ startPage: 1, endPage: 5 });
  const part2 = await harness.part({ startPage: 6, endPage: 6, previousState: part1 });
  const result = harness.finalize(part2);

  const checkpointText = JSON.stringify(part1) + JSON.stringify(part2);
  const resultText = JSON.stringify(result);

  for (const [label, value] of Object.entries(secrets)) {
    assert.ok(!checkpointText.includes(value), `⛔ checkpoint 不得含 ${label}`);
    assert.ok(!resultText.includes(value), `⛔ 结果不得含 ${label}`);
  }
  // raw segment 原文也不得出现
  assert.ok(!checkpointText.includes("1-8周/"), "⛔ checkpoint 不得含 raw segment");
  assert.ok(!checkpointText.includes(LOCATION), "⛔ checkpoint 不得含 location 原文");
  // checkpoint 只允许契约里的键（逐 part 校验）
  const stateKeys = [
    "candidate_count",
    "comparable_teaching_name_count",
    "expected_total",
    "f3_equals_teaching_name_count",
    "f3_matching_raw_fields",
    "f4_activity_count",
    "f4_equals_teaching_name_count",
    "openingSchoolNumber",
    "page_size",
    "processed_pages",
    "semester",
    "version",
  ];
  assert.deepEqual(Object.keys(part1).sort(), stateKeys);
  assert.deepEqual(Object.keys(part2).sort(), stateKeys);
  for (const entry of part2.processed_pages) {
    assert.deepEqual(Object.keys(entry).sort(), ["page_no", "row_count"]);
  }
});

test("分段诊断：401 / 403 / 600 立即整体停止（⛔ 不 retry / 不读认证）", async () => {
  for (const status of [401, 403, 600]) {
    const harness = newFieldSourceHarness(fsCorpus(), {
      statusForPage: (pageNo) => (pageNo === 6 ? status : 0),
    });

    await assert.rejects(() => harness.part({ startPage: 6, endPage: 6 }));
    assert.deepEqual(harness.calls, [6], `HTTP ${status} 只允许请求 1 次`);
  }
});

test("分段诊断：参数白名单与范围校验（⛔ 校验先于任何请求）", async () => {
  const harness = newFieldSourceHarness(fsCorpus());

  for (const bad of [{ pageSize: 50 }, { delayMs: 1000 }, { maxPages: 6 }, { scope: "x" }]) {
    await assert.rejects(
      () => harness.part(Object.assign({ startPage: 1, endPage: 1 }, bad)),
      /分段诊断只接受/,
    );
  }
  await assert.rejects(() => harness.part({ startPage: 3, endPage: 2 }), /startPage <= endPage/);
  await assert.rejects(() => harness.part({ startPage: 0, endPage: 2 }), /startPage <= endPage/);
  await assert.rejects(() => harness.part({ startPage: 1, endPage: 51 }), /endPage 不得超过/);
  await assert.rejects(
    () => harness.part({ startPage: undefined, endPage: undefined }),
    /startPage/,
  );
  assert.deepEqual(harness.calls, [], "⛔ 校验必须发生在任何取页调用之前");
});

test("分段诊断：取满即停（与 one-shot 相同的停止规则）", async () => {
  const pages = fsCorpus();
  const harness = newFieldSourceHarness(pages, { totals: { 1: 450, 2: 450, 3: 450 } });
  pages[2] = pages[2].slice(0, 50);

  const state = await harness.part({ startPage: 1, endPage: 5 });
  assert.deepEqual(harness.calls, [1, 2, 3], "累加到 expected_total 后必须停止");
  assert.deepEqual(
    [...state.processed_pages].map((entry) => entry.page_no),
    [1, 2, 3],
  );
});

test("分段诊断：超过 smoke 上限的 part 先确认；取消 → 不发请求也不产生 state", async () => {
  const cancelled = newFieldSourceHarness(fsCorpus(), { confirmResult: false });

  await assert.rejects(
    () => cancelled.part({ startPage: 1, endPage: 5 }),
    /取消了分段诊断/,
  );
  assert.deepEqual(cancelled.calls, []);
  assert.equal(cancelled.confirms.length, 1);
});

// ---------------------------------------------------------------------------
// Single-approved-campus capture（Architecture Review 裁定）
//
// ✅ 只采一个**已批准**校区，产出**标准裸 Capture Bundle**
// ⛔ 调用方不能传 openingSchoolNumber、⛔ 不改五校区编排、⛔ 不新增 wrapper schema
// ⛔ 北校园 suspended ⇒ fail closed（⛔ 不绕过）
// ---------------------------------------------------------------------------

const CAMPUS_PAGE_SIZE = 200;

/** 单校区语料：`rows` 行（默认 3 页 + 尾页）。 */
function campusRows(total) {
  return Array.from({ length: total }, (_, index) =>
    Object.assign(rawRow(`1-8周/星期五/第5-6节/${ACTIVITY}`), {
      classNumber: `SYN-CAMPUS-${String(index + 1).padStart(4, "0")}`,
    }),
  );
}

function loadCampusCollector(rows, options = {}) {
  return loadShardedCollector({
    campuses: [
      { openingSchoolNumber: "5063559", rows: rows },
      { openingSchoolNumber: "5062202", rows: rows },
    ],
    confirmResult: options.confirmResult,
  });
}

test("单校区采集：产出标准裸 bundle，且 source label / 校区号不写入 bundle", async () => {
  const rows = campusRows(450);
  const { collector, calls, confirms } = loadCampusCollector(rows);

  const result = await collector.collectApprovedShard({
    semester: SEMESTER,
    shardId: "east-campus",
    maxPages: 10,
  });

  assert.equal(result.cancelled, false);
  assert.equal(result.shard.capture_shard_id, "east-campus");
  assert.equal(result.shard.shard_id, "东校园");
  assert.equal(result.shard.openingSchoolNumber, "5063559");
  assert.equal(result.shard.source_label, "sysu-2026-1-east-campus");
  assert.equal(result.shard.operational, true);

  assert.deepEqual(Object.keys(result.bundle).sort(), [
    "first_page_no",
    "format",
    "page_size",
    "pages",
    "semester",
  ]);
  const serialized = collector.toJson(result);
  assert.ok(!serialized.includes("sysu-2026-1-east-campus"), "⛔ source label 不得进 bundle");
  assert.ok(!serialized.includes("5063559"), "⛔ 校区号不得进 bundle");
  assert.ok(!serialized.includes("capture_shard_id"), "⛔ 审计元数据不得进 bundle");

  // 页码是该校区真实页码（⛔ 不做 fake global renumbering）
  assert.deepEqual(
    plain(result.bundle.pages.map((page) => page.page_no)),
    [1, 2, 3],
  );
  assert.equal(result.bundle.semester, SEMESTER);
  assert.equal(result.bundle.first_page_no, 1);
  assert.equal(result.bundle.page_size, CAMPUS_PAGE_SIZE);
  assert.deepEqual(calls.map((call) => call.campus), ["5063559", "5063559", "5063559"]);
  assert.equal(confirms.length, 1, "超过 smoke 上限必须先确认");
});

test("单校区采集：⛔ 不接受调用方指定 openingSchoolNumber（冒充已批准 shard）", async () => {
  const { collector, calls } = loadCampusCollector(campusRows(10));

  for (const bad of [
    { openingSchoolNumber: "5063559" },
    { openingSchoolNumber: "9999999" },
    { shard_id: "东校园" },
    { pageSize: 50 },
    { firstPageNo: 2 },
  ]) {
    await assert.rejects(
      () =>
        collector.collectApprovedShard(
          Object.assign({ semester: SEMESTER, shardId: "east-campus" }, bad),
        ),
      /single-approved-campus 采集只接受/,
    );
  }
  assert.equal(calls.length, 0, "⛔ 参数校验必须发生在任何取页调用之前");
});

test("单校区采集：未知 shardId 被拒绝且不回显名字", async () => {
  const { collector, calls } = loadCampusCollector(campusRows(10));

  for (const badShardId of ["east", "东校园", "5063559", "SOUTH-CAMPUS", ""]) {
    await assert.rejects(
      () => collector.collectApprovedShard({ semester: SEMESTER, shardId: badShardId }),
      /不在已批准校区白名单内/,
    );
  }
  assert.equal(calls.length, 0);
});

test("单校区采集：北校园 suspended ⇒ fail closed（⛔ 不绕过、不发请求）", async () => {
  const { collector, calls } = loadCampusCollector(campusRows(10));

  await assert.rejects(
    () =>
      collector.collectApprovedShard({
        semester: SEMESTER,
        shardId: "north-campus",
        maxPages: 10,
      }),
    /suspended/,
  );
  assert.equal(calls.length, 0, "⛔ suspended 校区不得发出任何请求");

  // 白名单仍然保留北校园（仅 operational=false）
  const north = collector.APPROVED_CAMPUS_CAPTURE_SHARDS.find(
    (entry) => entry.capture_shard_id === "north-campus",
  );
  assert.ok(north, "⛔ 北校园必须仍在白名单中");
  assert.equal(north.operational, false);
  assert.equal(collector.APPROVED_CAMPUS_CAPTURE_SHARDS.length, 5);
});

test("单校区采集：未取满 ⇒ fail closed，不产出 bundle", async () => {
  const { collector } = loadCampusCollector(campusRows(450));

  await assert.rejects(
    () =>
      collector.collectApprovedShard({
        semester: SEMESTER,
        shardId: "east-campus",
        maxPages: 2,
      }),
    /单校区采集未取满|增加 maxPages|提高 maxPages/,
  );
});

test("单校区采集：semester 缺失 / 非法被拒绝（⛔ 不猜学期）", async () => {
  const { collector, calls } = loadCampusCollector(campusRows(10));

  await assert.rejects(
    () => collector.collectApprovedShard({ shardId: "east-campus" }),
    /semester/,
  );
  await assert.rejects(
    () => collector.collectApprovedShard({ semester: "  ", shardId: "east-campus" }),
    /semester/,
  );
  assert.equal(calls.length, 0);
});

test("单校区采集：pacing = 30s 间隔 + 每 7 个成功请求一次批次冷却", async () => {
  // 7 页 + 1 行 ⇒ 8 个请求：第 2..7 个各等 30 s，第 8 个等批次冷却
  const rows = campusRows(7 * CAMPUS_PAGE_SIZE + 1);
  const { collector, calls, timers } = loadCampusCollector(rows);

  const result = await collector.collectApprovedShard({
    semester: SEMESTER,
    shardId: "east-campus",
    maxPages: 20,
  });

  assert.equal(result.requests, 8);
  assert.equal(calls.length, 8);
  assert.deepEqual(
    timers,
    [30000, 30000, 30000, 30000, 30000, 30000, 300000],
    "前 6 个间隔 30 s；第 7 个成功请求之后（第 8 个请求之前）进入批次冷却",
  );
});

test("单校区采集：普通（五校区）路径的批次上限仍是 5（⛔ 未被改动）", async () => {
  const rows = campusRows(5 * CAMPUS_PAGE_SIZE + 1);
  const shardTotal = rows.length; // 每个校区 1001 行
  const { collector, timers } = loadShardedCollector({
    // ⚠️ 五校区编排会**遍历全部五个**已批准校区，因此假 fetch 必须覆盖五个；
    //    baseline 也必须等于五个 shard 的 total 之和（否则 coverage mismatch，fail closed）。
    campuses: SHARDS.map((shard) => ({
      openingSchoolNumber: shard.openingSchoolNumber,
      rows: rows,
    })),
    baselineTotals: [shardTotal * SHARDS.length, shardTotal * SHARDS.length],
  });

  const result = await collector.collectSharded({
    semester: SEMESTER,
    maxPages: 20,
    delayMs: 30000,
  });

  assert.ok(result.requests >= 7);
  assert.equal(
    timers[4],
    300000,
    "⛔ 五校区路径不得因为单校区口径而改变：第 5 个成功请求后（第 6 个请求前）必须冷却",
  );
  assert.equal(timers[0], 30000);
  assert.equal(timers[3], 30000);
});

test("单校区采集：401 / 403 / 600 立即整体停止（⛔ 不 retry / 不读认证）", async () => {
  for (const status of [401, 403, 600]) {
    const rows = campusRows(10);
    const harness = loadShardedCollector({
      campuses: [{ openingSchoolNumber: "5063559", rows: rows }],
      http600: { campus: "5063559", pageNo: 1 },
    });

    await assert.rejects(() =>
      harness.collector.collectApprovedShard({
        semester: SEMESTER,
        shardId: "east-campus",
        maxPages: 10,
      }),
    );
    assert.equal(harness.calls.length, 1, `HTTP ${status} 只允许请求 1 次`);
  }
});

// ---------------------------------------------------------------------------
// Layout B：4 字段 non-concrete（weeks | location | opaque | activity）
//
// Architecture Review 裁定：opaque 槽位**语义未知** ⇒ 只做**结构性**脱敏
// REDACTED_OPAQUE（⛔ 不解释成 teacher / 地点 / 活动 / 其它业务字段，
// ⛔ 不做姓名 / CJK / 长度启发式），且**只**对精确 Layout B 生效。
// ---------------------------------------------------------------------------

const REDACTED_OPAQUE = "REDACTED_OPAQUE";
const OPAQUE_RAW = "SECRET-OPAQUE-OMEGA";

test("Layout B：opaque 槽位替换为 REDACTED_OPAQUE，其余字段原样保留", async () => {
  const text = `1-5周/${LOCATION}/${OPAQUE_RAW}/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.equal(out, `1-5周/${LOCATION}/${REDACTED_OPAQUE}/${ACTIVITY}`);
  assert.ok(!out.includes(OPAQUE_RAW), "⛔ 原始 opaque 取值不得进入 Capture Bundle");
  assert.ok(!out.split("/").includes("REDACTED"), "⛔ 不得误用 teacher 占位符（两者独立）");
});

test("Layout B：只有精确 Layout B 被脱敏（concrete / 未归类 4 字段不变）", async () => {
  const concrete = `1-8周/星期五/第5-6节/${ACTIVITY}`;
  // f2 只有两个 '-' 分段 ⇒ 不是严格 location ⇒ 不视为 Layout B（保持既有行为）
  const unclassified = `1-8周/${CAMPUS}-2108/${TEACHER}/${ACTIVITY}`;

  for (const text of [concrete, unclassified]) {
    const out = await collectSingle(text);
    assert.equal(out, text, "⛔ 只允许对精确 Layout B 脱敏");
    assert.ok(!out.includes(REDACTED_OPAQUE));
  }
});

test("Layout B：与 concrete segment 混排时逐段正确处理", async () => {
  const text = `1-8周/星期三/第1-2节/${ACTIVITY},1-5周/${LOCATION}/${OPAQUE_RAW}/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.ok(out.includes(REDACTED_OPAQUE));
  assert.ok(!out.includes(OPAQUE_RAW));
  assert.ok(out.startsWith("1-8周/星期三/第1-2节/"), "concrete 段必须原样保留");
});

test("Layout B：opaque 槽位为空 → fail closed（⛔ 不用占位符掩盖）", async () => {
  const { collector } = loadCollector([rawRow(`1-5周/${LOCATION}//${ACTIVITY}`)]);

  await assert.rejects(() => collector.collect({ semester: SEMESTER }), /opaque 槽位为空/);
});

test("Layout B：synthetic opaque secret 不得出现在序列化 bundle 中", async () => {
  const { collector } = loadCollector([
    rawRow(`1-5周/${LOCATION}/${OPAQUE_RAW}/${ACTIVITY}`),
  ]);

  const result = await collector.collect({ semester: SEMESTER });
  const serialized = collector.toJson(result);

  assert.ok(!serialized.includes(OPAQUE_RAW), "⛔ 原始 opaque 取值不得进入 bundle");
  assert.ok(serialized.includes(REDACTED_OPAQUE));
});

test("分段诊断：加载脚本不自动调用新接口", async () => {
  const harness = newFieldSourceHarness(fsCorpus());
  assert.deepEqual(harness.calls, []);
  assert.equal(typeof harness.collector.diagnoseLayoutBFieldSourcePart, "function");
  assert.equal(typeof harness.collector.finalizeLayoutBFieldSource, "function");
});
// ---------------------------------------------------------------------------
// PR #40 BLOCK 修复回归（Architecture Review P1 + 3 项）
//
// ① Layout B 精确准入（与 parser 四条一致）⇒ 不满足 fail closed、且不产出 bundle
// ② 401 / 403 / 600 **各自真实覆盖**
// ③ production 错误不反射任意 `payload.code` / `error.message`
// ④ development-only 分段 state **多键拒绝**（含"排序靠后"的额外键）
// ---------------------------------------------------------------------------

const BLOCK_LOCATION = LOCATION;
const BLOCK_ACTIVITY = ACTIVITY;
const FAKE_CODE = "SECRET-CODE-ALPHA";
const FAKE_NET_MESSAGE = "SECRET-NET-ALPHA";

/** 一个可逐页指定 HTTP 状态的假 fetch（用于真实覆盖 401 / 403 / 600）。 */
function loadStatusCollector(rows, status) {
  const calls = [];
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
    Set,
    Map,
    clearTimeout: () => {},
    setTimeout: (callback) => {
      queueMicrotask(callback);
      return 1;
    },
    fetch: async (url, init) => {
      const body = JSON.parse(init.body);
      calls.push(body.pageNo);
      return {
        status: status,
        ok: false,
        headers: { get: () => "application/json;charset=UTF-8" },
        json: async () => ({ code: 50015000, message: "系统异常" }),
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

test("Layout B 精确准入：f1 非法 weeks ⇒ fail closed（不得 redact、不得产出 bundle）", async () => {
  const text = `NOT-WEEKS/${BLOCK_LOCATION}/SECRET-OPAQUE-X/${BLOCK_ACTIVITY}`;
  const { collector } = loadCollector([rawRow(text)]);

  await assert.rejects(
    () => collector.collect({ semester: SEMESTER }),
    (error) => {
      assert.ok(!error.message.includes("SECRET-OPAQUE-X"), "⛔ 不得回显 opaque 取值");
      assert.ok(!error.message.includes("NOT-WEEKS"), "⛔ 不得回显 raw token");
      return true;
    },
  );
});

test("Layout B 精确准入：f4 activity 为空 ⇒ fail closed（不得 redact、不得产出 bundle）", async () => {
  const text = `1-5周/${BLOCK_LOCATION}/SECRET-OPAQUE-Y/`;
  const { collector } = loadCollector([rawRow(text)]);

  await assert.rejects(
    () => collector.collect({ semester: SEMESTER }),
    (error) => {
      assert.ok(!error.message.includes("SECRET-OPAQUE-Y"), "⛔ 不得回显 opaque 取值");
      return true;
    },
  );
});

test("Layout B 精确准入：已批准 parity weeks（单/双周）仍必须被 redact", async () => {
  for (const weeks of ["1-17单周", "3-4双周", "1-5周校外", "1-5周校内(户外)"]) {
    const text = `${weeks}/${BLOCK_LOCATION}/SECRET-OPAQUE-Z/${BLOCK_ACTIVITY}`;
    const out = await collectSingle(text);

    assert.equal(out, `${weeks}/${BLOCK_LOCATION}/REDACTED_OPAQUE/${BLOCK_ACTIVITY}`);
    assert.ok(!out.includes("SECRET-OPAQUE-Z"), `⛔ ${weeks} 必须脱敏`);
  }
});

test("production 错误不反射任意 payload.code", async () => {
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
    Set,
    Map,
    clearTimeout: () => {},
    setTimeout: (callback) => {
      queueMicrotask(callback);
      return 1;
    },
    fetch: async () => ({
      status: 200,
      ok: true,
      headers: { get: () => "application/json;charset=UTF-8" },
      json: async () => ({ code: FAKE_CODE, data: { total: 0, rows: [] } }),
    }),
  };
  sandbox.window = {
    location: { hostname: "jwxt.sysu.edu.cn" },
    confirm: () => true,
    XuehangSysuCollector: undefined,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox, { filename: "sysu_course_offering_collector.js" });

  await assert.rejects(
    () => sandbox.window.XuehangSysuCollector.collect({ semester: SEMESTER }),
    (error) => {
      assert.ok(!error.message.includes(FAKE_CODE), "⛔ 不得反射任意 code 取值");
      assert.ok(error.message.includes("code_not_200"), "必须给出稳定安全分类");
      return true;
    },
  );
});

test("production 错误不反射任意 fetch error.message", async () => {
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
    Set,
    Map,
    clearTimeout: () => {},
    setTimeout: (callback) => {
      queueMicrotask(callback);
      return 1;
    },
    fetch: async () => {
      throw new Error(FAKE_NET_MESSAGE);
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

  await assert.rejects(
    () => sandbox.window.XuehangSysuCollector.collect({ semester: SEMESTER }),
    (error) => {
      assert.ok(!error.message.includes(FAKE_NET_MESSAGE), "⛔ 不得反射原始 error.message");
      assert.ok(error.message.includes("network_error"), "必须给出稳定安全分类");
      return true;
    },
  );
});

test("单校区采集：401 / 403 / 600 **各自**真实覆盖且立即停止", async () => {
  for (const status of [401, 403, 600]) {
    const rows = campusRows(10);
    const harness = loadStatusCollector(rows, status);

    await assert.rejects(
      () =>
        harness.collector.collectApprovedShard({
          semester: SEMESTER,
          shardId: "east-campus",
          maxPages: 10,
        }),
      new RegExp(String(status)),
      `HTTP ${status} 必须按该状态真实失败`,
    );
    assert.equal(harness.calls.length, 1, `HTTP ${status} 只允许请求 1 次`);
  }
});

test("分段诊断 state：多余的键（排序靠后）必须被拒绝", async () => {
  const harness = newFieldSourceHarness(fsCorpus());
  const part1 = await harness.part({ startPage: 1, endPage: 6 });

  const extraState = plain(part1);
  extraState.zzz_extra = 1; // 排序后位于所有已批准键之后
  assert.throws(() => harness.finalize(extraState), /键数量与契约不一致|键集合与契约不一致/);

  const extraEntry = plain(part1);
  extraEntry.processed_pages[0].zzz = "x";
  assert.throws(() => harness.finalize(extraEntry), /键数量不符|只允许 page_no/);
});
// ---------------------------------------------------------------------------
// PR #40 Blocker Fix Round — 追加 adversarial 覆盖
//
// ① 401 / 403 / 600：**每个状态**真实触发 + 恰好一次失败请求 + 无重试 / 无下一页 /
//    无后续 shard 请求 + 不产出 bundle
// ② weeks admission 的 adversarial：malformed range / start<1 / 未批准 qualifier
//    ⇒ collector 侧 fail closed（⛔ 不依赖 Python parser 事后拒绝）
// ---------------------------------------------------------------------------

test("单校区采集：401/403/600 各自真实触发（含无重试/无下一页/不产出 bundle）", async () => {
  for (const status of [401, 403, 600]) {
    const rows = campusRows(3 * CAMPUS_PAGE_SIZE);
    const harness = loadStatusCollector(rows, status);

    let failure = null;
    try {
      await harness.collector.collectApprovedShard({
        semester: SEMESTER,
        shardId: "east-campus",
        maxPages: 10,
      });
    } catch (error) {
      failure = error;
    }

    assert.ok(failure, `HTTP ${status} 必须失败`);
    // ① 对应 status 确实被触发（错误文案里带该状态码）
    assert.ok(
      failure.message.includes(String(status)),
      `HTTP ${status} 的错误必须体现该状态：${failure.message}`,
    );
    // ② 恰好一次失败请求；③ 无重试；④ 无下一页；⑤ 无后续 shard / 请求
    assert.deepEqual(plain(harness.calls), [1], `HTTP ${status} 只允许请求 1 页且不重试`);
    // ⑥ 不产出 bundle：函数抛出即无返回值
    assert.equal(failure.message.includes("REDACTED"), false, "错误文案不得含脱敏占位符内容");
  }
});

test("Layout B adversarial：malformed / 非法 weeks 区间 ⇒ collector fail closed", async () => {
  for (const weeks of ["5-3周", "0-3周", "1-5", "第1-5周", "abc周", "1-5周单周", "1-5周线上"]) {
    const text = `${weeks}/${BLOCK_LOCATION}/SECRET-OPAQUE-W/${BLOCK_ACTIVITY}`;
    const { collector } = loadCollector([rawRow(text)]);

    await assert.rejects(
      () => collector.collect({ semester: SEMESTER }),
      (error) => {
        assert.ok(!error.message.includes("SECRET-OPAQUE-W"), `⛔ 不得回显 opaque 取值（${weeks}）`);
        assert.ok(!error.message.includes(weeks), `⛔ 不得回显 raw weeks token（${weeks}）`);
        return true;
      },
      `未批准/非法 weeks 形态必须 fail closed：${weeks}`,
    );
  }
});

test("Layout B adversarial：严格 location 之外的 4 字段近邻不得被 redact", async () => {
  // f2 只有两段 '-'（不是严格 location）⇒ 不是 Layout B：原样保留（⛔ 不误 redact）
  const nearNeighbor = `1-5周/${CAMPUS}-2108/${TEACHER}/${ACTIVITY}`;
  const out = await collectSingle(nearNeighbor);

  assert.equal(out, nearNeighbor);
  assert.ok(!out.includes("REDACTED_OPAQUE"));
});
