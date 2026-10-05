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
// 5 字段：location/activity（无 teacher）
// ---------------------------------------------------------------------------

test("5 字段 location/activity：保留 location，且不插入 REDACTED", async () => {
  const text = `1-8周/星期五/第5-6节/${LOCATION}/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.equal(out, text, "5 字段 location 结构必须原样保留");
  assert.ok(out.includes(LOCATION), "⛔ location 不得被脱敏掉");
  assert.ok(!out.includes("REDACTED"), "⛔ 无 teacher 时不得插入 REDACTED");
});

// ---------------------------------------------------------------------------
// 5 字段：teacher/activity（有 teacher）
// ---------------------------------------------------------------------------

test("5 字段 teacher/activity：teacher 被替换为 REDACTED", async () => {
  const text = `1-8周/星期五/第5-6节/${TEACHER}/${ACTIVITY}`;

  const out = await collectSingle(text);

  assert.equal(out, `1-8周/星期五/第5-6节/REDACTED/${ACTIVITY}`);
  assert.ok(!out.includes(TEACHER), "⛔ 真实 teacher 不得出现在产物中");
});

// ---------------------------------------------------------------------------
// 6 字段：location/teacher/activity
// ---------------------------------------------------------------------------

test("6 字段：teacher 被替换为 REDACTED，location 保留", async () => {
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
// 未知字段数：继续 fail closed
// ---------------------------------------------------------------------------

for (const [label, text] of [
  ["3 字段", `1-8周/星期五/第5-6节`],
  ["7 字段", `1-8周/星期五/第5-6节/${LOCATION}/${TEACHER}/${ACTIVITY}/多出来`],
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
