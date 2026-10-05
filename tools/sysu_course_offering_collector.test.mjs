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
          error.message.includes("non-concrete"),
          `错误信息应说明 non-concrete grammar，实际：${error.message}`,
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
