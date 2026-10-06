# Real Artifact Acceptance CLI（campus-only）

> 内部工具：`tools/validate_course_data_artifact.py`
> ⛔ 零网络、⛔ 不读认证、⛔ 不修改 Capture Bundle 格式、⛔ 不实现第二套 parser / validator / store。

## 用途

把一个**本地** Capture Bundle 的 exact-byte SHA-256、现有 bundle validation、
snapshot normalization / completeness、**campus scope 绑定**与可选 SQLite import /
provenance read-back 串成**确定性、可复核**的 acceptance 流程。

## 使用

```bash
python tools/validate_course_data_artifact.py \
  --bundle ./east-campus.capture.json \
  --expected-semester 2026-1 \
  --scope-id 5063559 \
  --source capture://sysu/2026-1/campus/5063559 \
  [--expected-sha256 <64 位小写 hex>] \
  [--sqlite ./course-data.sqlite]
```

成功时 stdout 输出**一个** JSON 对象（只含聚合字段）；失败时 stderr 输出
**一个** JSON 对象（只含 `status` / `stage` / `category` / `exception_type` 与安全聚合计数），
并以非零退出码结束。

## 契约（Architecture Review Gate）

| 项 | 规则 |
| --- | --- |
| scope | **只允许 campus**：CLI **固定** `scope_kind = campus`、`scope_id = <openingSchoolNumber>`；⛔ **没有** `--scope-kind` 选项 |
| full_semester | ⛔ **本 CLI 不实现**（裸 Capture Bundle 不携带可验证 scope；`campus complete != full semester complete`）⇒ 由后续独立的 **five-shard / full-semester acceptance Gate** 承担 |
| source | 必须**精确**等于 `capture://sysu/<semester>/campus/<scope_id>`（semester 与 scope_id 双重一致）；`source` 只是 **audit label**，⛔ **不是** provenance proof |
| SHA-256 | 对**原始 bytes** 计算（`compute_artifact_sha256`），语义 = exact-byte identity / integrity；可选 `--expected-sha256` 必须一致，否则 fail closed |
| completeness | 只有 **complete** snapshot 才可能被导入；partial 与 **empty（0 offering）** 一律 fail closed |
| SQLite | 只有给出 `--sqlite` 且 snapshot complete 时才调用 store；导入后**逐项回读**并核对 |

## SQLite acceptance / read-back 检查

导入后必须**全部**成立（任一不满足 ⇒ 非零退出、`stage = sqlite_readback_validation` /
`sqlite_reconciliation`）：

```text
provenance.artifact_sha256 == 本次 raw bytes 的 SHA-256
provenance.semester        == --expected-semester
provenance.scope_kind      == campus
provenance.scope_id        == --scope-id
provenance.source          == --source
provenance.completeness    == complete
provenance.loaded_count    == snapshot.loaded_count
provenance.reported_total  == snapshot.reported_total
provenance.offering_count  == len(snapshot.offerings)
inserted + updated + unchanged == provenance.offering_count
```

⚠️ **输出字段语义区分**：

- `offering_count` = **本 artifact** 的 offering 数（语义标注 `this_artifact_only`）；
- `db_semester_offering_count` = **该学期当前库里**的 offering 总数
  （可能包含其它 artifact；语义标注
  `all_offerings_currently_stored_for_this_semester_not_this_artifact`）
  ⇒ ⛔ **不得**把它当成当前 artifact 的 offering count。

## ⚠️ 事务 caveat（必须明确）

SQLite **import commit** 与 **provenance read-back** **不是同一个事务**：

```text
⛔ 不得声称"CLI 非零退出 == SQLite 零变化"
```

失败发生在**任何 store 调用之前**（read/hash、bundle、semester、scope、source、
normalization、completeness、empty）时，只能说明**该次调用未发生**；
read-back 阶段的失败发生在 commit **之后**，数据库可能已经变化。

## 零泄露

- 错误只输出 `status` / `stage` / `category` / `exception_type` 与安全聚合计数；
- ⛔ 不打印异常消息（normalization 异常可能源自真实排课 row）、⛔ 不打印文件路径 /
  文件名 / raw token / row 取值；⛔ 无网络、⛔ 无认证材料。

## 当前状态

- PR #40 = **merged**；main = `d3a451b90ff84087901f8c8f3ee471d14f359da1`；
- 本 CLI 只做 **campus-scope** acceptance；**full_semester acceptance = 未实现**（后续独立 Gate）；
- PR #39 = **frozen / do not merge**；formal Real E2E = **LEVEL0**；
- ⛔ 尚未处理真实 East artifact（仅 synthetic / zero-network 测试）。
